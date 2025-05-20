# agent/openai_agent.py

import asyncio
import logging
import uuid
from dotenv import load_dotenv

from livekit import rtc
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli
from livekit.agents.stt import SpeechEventType
from livekit.plugins import openai
from livekit.rtc.transcription import Transcription, TranscriptionSegment

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("openai-transcriber")


async def entrypoint(ctx: JobContext):
    # Initialize OpenAI STT
    stt_impl = openai.STT(
        model="gpt-4o-transcribe",  # or "whisper-1"
        language="en",
    )

    @ctx.room.on("track_subscribed")
    def on_track(track: rtc.Track, _: rtc.TrackPublication, participant: rtc.RemoteParticipant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            asyncio.create_task(handle_audio_track(participant, track))

    async def handle_audio_track(participant: rtc.RemoteParticipant, track: rtc.Track):
        audio_stream = rtc.AudioStream(track)
        stt_stream = stt_impl.stream()

        await asyncio.gather(
            feed_audio(audio_stream, stt_stream),
            drain_transcripts(participant, track.sid, stt_stream),
        )

    async def feed_audio(audio_stream: rtc.AudioStream, stt_stream):
        async for pkt in audio_stream:
            stt_stream.push_frame(pkt.frame)
        stt_stream.end_input()

    async def drain_transcripts(participant, track_sid, stt_stream):
        async for ev in stt_stream:
            segments = []
            for alt in ev.alternatives or []:
                seg = TranscriptionSegment(
                    id=str(uuid.uuid4()),
                    text=alt.text,
                    start_time=int(alt.start_time * 1000),
                    end_time=int(alt.end_time * 1000),
                    final=getattr(alt, "final", False),
                    language=getattr(alt, "language", "en"),
                )
                segments.append(seg)

            if segments:
                transcription = Transcription(
                    participant_identity=participant.identity,
                    track_sid=track_sid,
                    segments=segments,
                )
                await ctx.room.local_participant.publish_transcription(transcription)

                if ev.type == SpeechEventType.FINAL_TRANSCRIPT:
                    logger.info(f"[{participant.identity}] → {segments[-1].text}")

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
