from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


class CandidateCvRepository:
    """The candidate's single whole-CV row (global, no RLS).

    One row per candidate (UNIQUE candidate_id); re-uploading replaces it via
    an upsert. Embedding is a single pgvector(1536) for the whole CV (not chunked).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def exists(self, candidate_id: str) -> bool:
        result = await self._session.execute(
            sa.text("SELECT 1 FROM candidate_cvs WHERE candidate_id = :cid"),
            {"cid": str(candidate_id)},
        )
        return result.first() is not None

    async def get(self, candidate_id: str) -> dict | None:
        result = await self._session.execute(
            sa.text(
                "SELECT id, candidate_id, cv_blob_key, cv_text, cv_extraction_method, "
                "skills, embedding_truncated, created_at, updated_at "
                "FROM candidate_cvs WHERE candidate_id = :cid"
            ),
            {"cid": str(candidate_id)},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def upsert(
        self,
        *,
        candidate_id: str,
        cv_blob_key: str,
        cv_text: str,
        cv_extraction_method: str | None,
        embedding: list[float],
        embedding_truncated: bool,
        skills: list | None = None,
    ) -> None:
        import json

        vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
        await self._session.execute(
            sa.text(
                """
                INSERT INTO candidate_cvs
                    (id, candidate_id, cv_blob_key, cv_text, cv_extraction_method,
                     embedding, tsv, embedding_truncated, skills)
                VALUES
                    (:id, :cid, :blob, :text, :method,
                     CAST(:embedding AS vector), to_tsvector('english', :text),
                     :truncated, CAST(:skills AS jsonb))
                ON CONFLICT (candidate_id) DO UPDATE SET
                    cv_blob_key = EXCLUDED.cv_blob_key,
                    cv_text = EXCLUDED.cv_text,
                    cv_extraction_method = EXCLUDED.cv_extraction_method,
                    embedding = EXCLUDED.embedding,
                    tsv = EXCLUDED.tsv,
                    embedding_truncated = EXCLUDED.embedding_truncated,
                    skills = EXCLUDED.skills,
                    updated_at = now()
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "cid": str(candidate_id),
                "blob": cv_blob_key,
                "text": cv_text,
                "method": cv_extraction_method,
                "embedding": vec_str,
                "truncated": embedding_truncated,
                "skills": json.dumps(skills if skills is not None else []),
            },
        )

    async def update_skills(self, *, candidate_id: str, skills: list) -> None:
        import json

        await self._session.execute(
            sa.text(
                "UPDATE candidate_cvs SET skills = CAST(:skills AS jsonb), updated_at = now() "
                "WHERE candidate_id = :cid"
            ),
            {"skills": json.dumps(skills), "cid": str(candidate_id)},
        )
