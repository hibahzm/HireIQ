from __future__ import annotations

import asyncio

import structlog

from app.config import get_settings

logger = structlog.get_logger()


class StreamingSttService:
    """
    Streaming speech-to-text via the Azure Speech SDK (free F0 tier).

    Audio frames (PCM 16 kHz, 16-bit, mono) are pushed into a `PushAudioInputStream`;
    the SDK's `recognizing` (partial) and `recognized` (final) callbacks fire on SDK
    threads and are bridged to the asyncio world via `loop.call_soon_threadsafe`, so the
    event loop is never blocked (Constitution II / research Decision 4).

    Lifecycle per utterance:
        svc = StreamingSttService(); svc.start()
        svc.push(frame) ...            # while the client VAD reports speech
        text = await svc.finalize()    # on end_of_speech
    """

    SAMPLE_RATE = 16000

    def __init__(self) -> None:
        self._settings = get_settings()
        import azure.cognitiveservices.speech as speechsdk

        self._speechsdk = speechsdk
        self._loop: asyncio.AbstractEventLoop | None = None
        self._partials: asyncio.Queue[str] = asyncio.Queue()
        self._finals: list[str] = []
        self._started = False

        speech_config = speechsdk.SpeechConfig(
            subscription=self._settings.AZURE_SPEECH_KEY,
            region=self._settings.AZURE_SPEECH_REGION,
        )
        speech_config.speech_recognition_language = "en-US"
        audio_format = speechsdk.audio.AudioStreamFormat(
            samples_per_second=self.SAMPLE_RATE, bits_per_sample=16, channels=1
        )
        self._push_stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)
        audio_config = speechsdk.audio.AudioConfig(stream=self._push_stream)
        self._recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config, audio_config=audio_config
        )
        self._recognizer.recognizing.connect(self._on_recognizing)
        self._recognizer.recognized.connect(self._on_recognized)

    def _on_recognizing(self, evt) -> None:
        text = getattr(evt.result, "text", "") or ""
        if text and self._loop is not None:
            self._loop.call_soon_threadsafe(self._partials.put_nowait, text)

    def _on_recognized(self, evt) -> None:
        speechsdk = self._speechsdk
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech and evt.result.text:
            self._finals.append(evt.result.text)

    def start(self) -> None:
        if self._started:
            return
        self._loop = asyncio.get_running_loop()
        self._recognizer.start_continuous_recognition_async().get()
        self._started = True

    def push(self, frame: bytes) -> None:
        """Push one raw PCM16 frame into the recognizer."""
        self._push_stream.write(frame)

    async def next_partial(self) -> str | None:
        try:
            return self._partials.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def finalize(self) -> str:
        """End-of-speech: close the input, stop recognition, return the joined transcript."""
        self._push_stream.close()
        # stop_continuous_recognition blocks until the SDK drains — run off the loop.
        await asyncio.to_thread(self._recognizer.stop_continuous_recognition)
        self._started = False
        return " ".join(self._finals).strip()
