#!/usr/bin/env python3
"""
LiveKit STT agent using a configurable Hugging Face ASR model (non-streaming),
with Silero VAD, enhanced noise cancellation (BVC), and StreamAdapter.
"""

import asyncio
import io
import wave
import uuid
import logging
import os

# dotenv fallback to avoid circular-import bug
try:
    from dotenv import load_dotenv
except ImportError:
    from dotenv.main import load_dotenv

import torch
from transformers import pipeline
from pydub import AudioSegment

from livekit import rtc
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
    stt as agents_stt,
)
from livekit.agents.stt import (
    SpeechEventType,
    SpeechEvent,
    SpeechData,
    STTCapabilities,
    StreamAdapter,
)
from livekit.agents.utils import merge_frames
from livekit.plugins import silero, noise_cancellation
from livekit.rtc.transcription import Transcription, TranscriptionSegment

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("hf-transcriber")
logging.getLogger("livekit.agents").setLevel(logging.DEBUG)


class HFAudioSTT(agents_stt.STT):
    """
    Non-streaming STT that sends complete utterances to a Hugging Face ASR model.
    """
    def __init__(self, model_name: str, hf_token: str = None):
        super().__init__(capabilities=STTCapabilities(streaming=False, interim_results=False))
        self.asr = pipeline(
            "automatic-speech-recognition",
            model=model_name,
            token=hf_token,
            torch_dtype=torch.float16,
            device="cuda" if torch.cuda.is_available() else "cpu",
            chunk_length_s=30,
        )

    async def _recognize_impl(self, frames, *, language: str | None = None, **kwargs) -> SpeechEvent:
        # 1) merge raw RTC audio frames
        buffer = merge_frames(frames)

        # 2) write to WAV in-memory
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wav_file:
            wav_file.setnchannels(buffer.num_channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(buffer.sample_rate)
            wav_file.writeframes(buffer.data)
        wav_io.seek(0)

        # 3) convert to MP3 for the HF pipeline
        audio = AudioSegment.from_wav(wav_io)
        mp3_io = io.BytesIO()
        audio.export(mp3_io, format="mp3")
        mp3_io.seek(0)

        # 4) call Hugging Face ASR
        result = self.asr(mp3_io.read())
        text = result.get("text", "")

        logger.info(f"🗣️ HF ASR result: {text!r}")

        # 5) wrap in SpeechEvent
        return SpeechEvent(
            type=SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[SpeechData(text=text, language=language or "kk")],
        )


async def entrypoint(ctx: JobContext):
    # Connect to the room, audio-only
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    room = ctx.room
    logger.info(f"✅ Agent joined room: {room.name!r}")

    # Load Silero VAD
    vad = silero.VAD.load(min_speech_duration=0.1, min_silence_duration=0.5)

    # Read model name from env (fallback to whisper-turbo-kazasr)
    hf_model = os.getenv("HF_MODEL", "erzhanbakanbayev/whisper-turbo-kazasr")
    hf_token = os.getenv("HF_TOKEN", None)

    hf_stt = HFAudioSTT(
        model_name=hf_model,
        hf_token=hf_token,
    )

    # Wrap non-streaming STT in VAD-backed StreamAdapter
    stt_adapter = StreamAdapter(stt=hf_stt, vad=vad)

    @room.on("track_subscribed")
    def on_track(track: rtc.Track, _pub, participant: rtc.RemoteParticipant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            logger.info(f"▶️ Audio from {participant.identity!r}")
            # Apply enhanced noise cancellation (BVC) per-stream
            noise_stream = rtc.AudioStream.from_track(
                track=track,
                noise_cancellation=noise_cancellation.BVC()
            )
            # Pass track.sid along with the noise-cancelled stream
            asyncio.create_task(handle_track(
                room,
                participant.identity,
                track.sid,
                noise_stream,
                stt_adapter
            ))


async def handle_track(
    room,
    identity: str,
    track_sid: str,
    audio_stream: rtc.AudioStream,
    stt_impl
):
    stt_stream = stt_impl.stream()

    async def pump_audio():
        async for ev in audio_stream:
            stt_stream.push_frame(ev.frame)
        stt_stream.end_input()

    async def pump_transcripts():
        async for ev in stt_stream:
            segments: list[TranscriptionSegment] = []
            for alt in ev.alternatives or []:
                segments.append(TranscriptionSegment(
                    id=str(uuid.uuid4()),
                    text=alt.text,
                    start_time=int(alt.start_time * 1000),
                    end_time=int(alt.end_time * 1000),
                    final=getattr(alt, "final", False),
                    language=getattr(alt, "language", "kk"),
                ))

            if segments:
                # Publish transcription track
                await room.local_participant.publish_transcription(
                    Transcription(
                        participant_identity=identity,
                        track_sid=track_sid,
                        segments=segments,
                    )
                )
                # Also send final text as a chat message
                if ev.type == SpeechEventType.FINAL_TRANSCRIPT:
                    final_text = segments[-1].text
                    logger.info(f"✅ Final (kk): {final_text!r}")
                    await room.local_participant.publish_data(
                        final_text,
                        reliable=True,
                        topic="stt"
                    )

    await asyncio.gather(pump_audio(), pump_transcripts())


if __name__ == "__main__":
    opts = WorkerOptions(entrypoint_fnc=entrypoint)
    cli.run_app(opts)
