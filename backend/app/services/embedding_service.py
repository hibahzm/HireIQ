from __future__ import annotations

import tiktoken

from app.services.usage_service import estimate_usage_cost

_CHUNK_SIZE_TOKENS = 512
_CHUNK_OVERLAP_TOKENS = 64
_MODEL = "text-embedding-3-small"
_TOKENIZER = "cl100k_base"
# text-embedding-3-small accepts up to 8191 input tokens; leave headroom.
_MAX_CV_EMBED_TOKENS = 8000


class EmbeddingService:
    def __init__(self) -> None:
        from app.config import get_settings

        self._settings = get_settings()
        self._enc = tiktoken.get_encoding(_TOKENIZER)

    async def embed_text(self, text: str) -> tuple[list[float], dict]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._settings.OPENAI_API_KEY)
        response = await client.embeddings.create(input=text, model=_MODEL)
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or len(self._enc.encode(text)))
        usage_event = {
            "agent_type": "embedding",
            "model": _MODEL,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": 0,
            "estimated_cost_usd": float(
                estimate_usage_cost(model=_MODEL, prompt_tokens=prompt_tokens)
            ),
            "metadata": {"operation": "cv_chunk_embedding"},
        }
        return response.data[0].embedding, usage_event

    async def embed_whole_cv(self, cv_text: str) -> tuple[list[float], bool, dict]:
        """Embed the entire CV as a SINGLE vector (for cross-company sourcing).

        Returns (embedding, truncated, usage_event). When the CV exceeds the model's
        token cap, the OLDEST content (trailing tokens — CVs are reverse-chronological,
        so most-recent experience sits at the top) is dropped and `truncated=True` is
        returned so the caller can audit-log it. Content is never silently lost without
        signalling truncation.
        """
        tokens = self._enc.encode(cv_text)
        truncated = len(tokens) > _MAX_CV_EMBED_TOKENS
        text_to_embed = self._enc.decode(tokens[:_MAX_CV_EMBED_TOKENS]) if truncated else cv_text
        embedding, usage_event = await self.embed_text(text_to_embed)
        usage_event["metadata"] = {
            "operation": "candidate_cv_embedding",
            "truncated": truncated,
            "original_tokens": len(tokens),
        }
        return embedding, truncated, usage_event

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

    async def embed_chunks(self, cv_text: str) -> tuple[list[tuple[str, list[float]]], list[dict]]:
        """Returns list of (chunk_text, embedding) tuples."""
        chunks = self.chunk_cv(cv_text)
        result = []
        usage_events = []
        for chunk in chunks:
            embedding, usage_event = await self.embed_text(chunk)
            result.append((chunk, embedding))
            usage_events.append(usage_event)
        return result, usage_events
