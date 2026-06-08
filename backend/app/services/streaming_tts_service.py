from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import structlog

from app.config import get_settings

logger = structlog.get_logger()


class StreamingTtsService:
    """
    Streaming text-to-speech via the Azure Speech SDK (free F0 tier).

    `stream(text)` is an async generator that yields mp3 audio chunks as Azure synthesizes
    them, so the client can begin playback before synthesis completes (FR-004 / SC-002).
    The SDK's `synthesizing` callback fires on an SDK thread and enqueues chunks onto an
    `asyncio.Queue` via `loop.call_soon_threadsafe` — no event-loop blocking (Constitution II).
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        import azure.cognitiveservices.speech as speechsdk

        self._speechsdk = speechsdk

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        speechsdk = self._speechsdk
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()

        speech_config = speechsdk.SpeechConfig(
            subscription=self._settings.AZURE_SPEECH_KEY,
            region=self._settings.AZURE_SPEECH_REGION,
        )
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
        )
        # audio_config=None → we receive audio via the synthesizing callback, not a speaker.
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)

        def _on_synthesizing(evt) -> None:
            data = bytes(evt.result.audio_data or b"")
            if data:
                loop.call_soon_threadsafe(queue.put_nowait, data)

        def _on_done(evt) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, None)

        synthesizer.synthesizing.connect(_on_synthesizing)
        synthesizer.synthesis_completed.connect(_on_done)
        synthesizer.synthesis_canceled.connect(_on_done)

        # Fire-and-forget; chunks arrive via callbacks. Keep `synthesizer` referenced for the
        # lifetime of this generator so it is not garbage-collected mid-synthesis.
        synthesizer.speak_text_async(text)

        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk
