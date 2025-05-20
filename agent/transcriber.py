#!/usr/bin/env python3
"""
LiveKit STT agent using OpenAI Whisper for Kazakh via dispatch.

Purely dispatch-based: no hard-coded room/url in WorkerOptions.
"""

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

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("transcriber")
logging.getLogger("livekit.agents").setLevel(logging.DEBUG)


async def entrypoint(ctx: JobContext):
    logger.info("📨 Job dispatch received — calling ctx.connect()…")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    room = ctx.room
    logger.info(f"✅ Agent joined room: {room.name!r}")

    stt_impl = openai.STT(model="whisper-1", language="kk")
    logger.debug("Initialized OpenAI Whisper STT (kk)")

    @room.on("track_subscribed")
    def on_track(track: rtc.Track, _pub, participant: rtc.RemoteParticipant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            logger.info(f"▶️ Audio from {participant.identity!r}")
            asyncio.create_task(handle_track(room, participant.identity, track, stt_impl))


async def handle_track(room, identity: str, track: rtc.Track, stt_impl):
    audio_stream = rtc.AudioStream(track)
    stt_stream   = stt_impl.stream()

    async def pump_audio():
        logger.debug("▷ pump_audio start")
        async for ev in audio_stream:
            stt_stream.push_frame(ev.frame)
        stt_stream.end_input()
        logger.debug("▷ pump_audio end (end_input)")

    async def pump_transcripts():
        logger.debug("▷ pump_transcripts start")
        async for ev in stt_stream:
            logger.debug(f"    📝 SpeechEvent: type={ev.type}, alts={len(ev.alternatives or [])}")
            segments = []
            for alt in ev.alternatives or []:
                logger.debug(f"      • alt={alt.text!r} final={getattr(alt,'final',False)}")
                segments.append(TranscriptionSegment(
                    id=str(uuid.uuid4()),
                    text=alt.text,
                    start_time=int(alt.start_time * 1000),
                    end_time=int(alt.end_time   * 1000),
                    final=getattr(alt, "final", False),
                    language=getattr(alt, "language", "kk"),
                ))

            if segments:
                await room.local_participant.publish_transcription(
                    Transcription(
                        participant_identity=identity,
                        track_sid=track.sid,
                        segments=segments,
                    )
                )
                if ev.type == SpeechEventType.FINAL_TRANSCRIPT:
                    text = segments[-1].text
                    logger.info(f"✅ Final (kk): {text!r}")
                    await room.local_participant.publish_data(
                        text, reliable=True, topic="stt"
                    )

    await asyncio.gather(pump_audio(), pump_transcripts())


if __name__ == "__main__":
    opts = WorkerOptions(entrypoint_fnc=entrypoint)
    cli.run_app(opts)
