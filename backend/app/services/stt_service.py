from __future__ import annotations

import io


class SttService:
    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        from openai import AsyncOpenAI

        from app.config import get_settings

        settings = get_settings()
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = filename

        response = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
        text = response.text.strip()
        if not text:
            raise ValueError("empty_transcript")
        return text
