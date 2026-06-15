from __future__ import annotations

import io


class TtsService:
    async def synthesize(self, text: str) -> bytes:
        """Returns MP3 bytes. Falls back to Azure AI Speech on OpenAI TTS failure."""
        try:
            return await self._openai_tts(text)
        except Exception:
            return await self._azure_tts(text)

    async def _openai_tts(self, text: str) -> bytes:
        from openai import AsyncOpenAI

        from app.config import get_settings

        settings = get_settings()
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        response = await client.audio.speech.create(
            model="tts-1",
            voice="nova",  # Sila's voice on the OpenAI path
            input=text,
            response_format="mp3",
        )
        buf = io.BytesIO()
        async for chunk in response.iter_bytes(chunk_size=4096):
            buf.write(chunk)
        return buf.getvalue()

    async def _azure_tts(self, text: str) -> bytes:
        import azure.cognitiveservices.speech as speechsdk

        from app.config import get_settings

        settings = get_settings()
        speech_config = speechsdk.SpeechConfig(
            subscription=settings.AZURE_SPEECH_KEY,
            region=settings.AZURE_SPEECH_REGION,
        )
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
        )
        # Sila's voice — keep in sync with StreamingTtsService.
        speech_config.speech_synthesis_voice_name = "en-US-JennyNeural"
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
        result = synthesizer.speak_text_async(text).get()
        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            raise RuntimeError("Azure TTS synthesis failed")
        return result.audio_data
