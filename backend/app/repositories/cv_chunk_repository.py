from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


class CvChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_insert(
        self,
        application_id: str,
        company_id: str,
        chunks: list[tuple[str, list[float]]],
    ) -> None:
        for idx, (chunk_text, embedding) in enumerate(chunks):
            vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
            tsv_query = sa.text(
                """
                INSERT INTO cv_chunks (id, application_id, company_id, chunk_index, chunk_text, embedding, tsv)
                VALUES (:id, :app_id, :company_id, :chunk_index, :chunk_text,
                        CAST(:embedding AS vector), to_tsvector('english', :chunk_text))
                """
            )
            await self._session.execute(
                tsv_query,
                {
                    "id": str(uuid.uuid4()),
                    "app_id": application_id,
                    "company_id": company_id,
                    "chunk_index": idx,
                    "chunk_text": chunk_text,
                    "embedding": vec_str,
                },
            )

    async def hybrid_search(
        self,
        job_id: str,
        query_embedding: list[float],
        query_text: str,
        top_k: int = 10,
    ) -> list[dict]:
        """RRF fusion of dense cosine + sparse tsvector results."""
        vec_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        dense_q = sa.text(
            """
            SELECT cv.id, cv.application_id, cv.chunk_text,
                   1 - (cv.embedding <=> CAST(:embedding AS vector)) AS score
            FROM cv_chunks cv
            JOIN applications a ON a.id = cv.application_id
            WHERE a.job_id = :job_id
            ORDER BY score DESC
            LIMIT 20
            """
        )
        sparse_q = sa.text(
            """
            SELECT cv.id, cv.application_id, cv.chunk_text,
                   ts_rank(cv.tsv, plainto_tsquery('english', :query)) AS score
            FROM cv_chunks cv
            JOIN applications a ON a.id = cv.application_id
            WHERE a.job_id = :job_id
              AND cv.tsv @@ plainto_tsquery('english', :query)
            ORDER BY score DESC
            LIMIT 20
            """
        )

        dense_res, sparse_res = await asyncio.gather(
            self._session.execute(dense_q, {"embedding": vec_str, "job_id": job_id}),
            self._session.execute(sparse_q, {"query": query_text, "job_id": job_id}),
        )

        dense_rows = list(dense_res.mappings().all())
        sparse_rows = list(sparse_res.mappings().all())

        # RRF with k=60
        k = 60
        scores: dict[str, float] = {}
        for rank, row in enumerate(dense_rows):
            scores[row["id"]] = scores.get(row["id"], 0) + 1 / (k + rank + 1)
        for rank, row in enumerate(sparse_rows):
            scores[row["id"]] = scores.get(row["id"], 0) + 1 / (k + rank + 1)

        # Merge and return top_k
        all_rows = {r["id"]: dict(r) for r in dense_rows}
        all_rows.update({r["id"]: dict(r) for r in sparse_rows})

        sorted_ids = sorted(scores, key=lambda i: scores[i], reverse=True)[:top_k]
        return [all_rows[i] for i in sorted_ids if i in all_rows]


class JobChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_insert(
        self,
        job_id: str,
        company_id: str,
        chunks: list[tuple[str, list[float]]],
    ) -> None:
        for idx, (chunk_text, embedding) in enumerate(chunks):
            vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
            await self._session.execute(
                sa.text(
                    """
                    INSERT INTO job_chunks (id, job_id, company_id, chunk_index, chunk_text, embedding)
                    VALUES (:id, :job_id, :company_id, :chunk_index, :chunk_text, CAST(:embedding AS vector))
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "job_id": job_id,
                    "company_id": company_id,
                    "chunk_index": idx,
                    "chunk_text": chunk_text,
                    "embedding": vec_str,
                },
            )
