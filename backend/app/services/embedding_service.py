from __future__ import annotations

import tiktoken

_CHUNK_SIZE_TOKENS = 512
_CHUNK_OVERLAP_TOKENS = 64
_MODEL = "text-embedding-3-small"
_TOKENIZER = "cl100k_base"


class EmbeddingService:
    def __init__(self) -> None:
        from app.config import get_settings
        self._settings = get_settings()
        self._enc = tiktoken.get_encoding(_TOKENIZER)

    async def embed_text(self, text: str) -> list[float]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._settings.OPENAI_API_KEY)
        response = await client.embeddings.create(input=text, model=_MODEL)
        return response.data[0].embedding

    def chunk_cv(self, cv_text: str) -> list[str]:
        """Split cv_text into overlapping token-bounded chunks."""
        tokens = self._enc.encode(cv_text)
        chunks: list[str] = []
        start = 0
        while start < len(tokens):
            end = min(start + _CHUNK_SIZE_TOKENS, len(tokens))
            chunk_tokens = tokens[start:end]
            chunks.append(self._enc.decode(chunk_tokens))
            if end == len(tokens):
                break
            start += _CHUNK_SIZE_TOKENS - _CHUNK_OVERLAP_TOKENS
        return chunks

    async def embed_chunks(self, cv_text: str) -> list[tuple[str, list[float]]]:
        """Returns list of (chunk_text, embedding) tuples."""
        chunks = self.chunk_cv(cv_text)
        result = []
        for chunk in chunks:
            embedding = await self.embed_text(chunk)
            result.append((chunk, embedding))
        return result
