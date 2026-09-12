"""Account-scoped database candidates; never transfer corpus vectors to the API."""

import json
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import defer

from app.db.models.knowledge import KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from app.db.models.knowledge_search import KnowledgeSearchChunk

SCOPE = """
    SELECT s.*, d.knowledge_base_id
    FROM knowledge_search_chunks s
    JOIN knowledge_chunks c ON c.id = s.chunk_id
    JOIN knowledge_documents d ON d.id = c.document_id
    JOIN knowledge_bases b ON b.id = d.knowledge_base_id
    WHERE b.user_id = :user_id AND b.id = ANY(CAST(:base_ids AS uuid[]))
      AND (:all_documents OR d.id = ANY(CAST(:document_ids AS uuid[])))
      AND d.status = 'ready' AND d.embedding_model = :model
      AND s.generation_id = d.job_id AND s.source_hash = md5(c.content)
      AND s.model_fingerprint = :fingerprint AND s.tokenizer_version = :tokenizer
"""


class KnowledgeSearchRepository:
    def __init__(self, db, user_id):
        self.db, self.user_id = db, user_id

    async def coverage(self, params):
        row = (
            (
                await self.db.execute(
                    text("""
            SELECT count(*) AS total, count(s.chunk_id) AS indexed
            FROM knowledge_chunks c
            JOIN knowledge_documents d ON d.id = c.document_id
            JOIN knowledge_bases b ON b.id = d.knowledge_base_id
            LEFT JOIN knowledge_search_chunks s ON s.chunk_id = c.id
              AND s.generation_id = d.job_id AND s.source_hash = md5(c.content)
              AND s.model_fingerprint = :fingerprint AND s.tokenizer_version = :tokenizer
            WHERE b.user_id = :user_id AND b.id = ANY(CAST(:base_ids AS uuid[]))
              AND (:all_documents OR d.id = ANY(CAST(:document_ids AS uuid[])))
              AND d.status = 'ready' AND d.embedding_model = :model
        """),
                    params,
                )
            )
            .mappings()
            .one()
        )
        return dict(row)

    async def semantic(self, params, vector, config):
        result = await self.db.execute(
            text(
                "WITH scope AS NOT MATERIALIZED ("
                + SCOPE
                + """),
            scores AS (SELECT chunk_id, 1 - (embedding <=> CAST(:vector AS vector)) AS score FROM scope)
            SELECT chunk_id, score, count(*) OVER () AS eligible FROM scores
            WHERE score >= :threshold ORDER BY score DESC, chunk_id LIMIT :limit
        """
            ),
            {
                **params,
                "vector": json.dumps(vector),
                "threshold": config.semantic_threshold,
                "limit": config.candidate_limit,
            },
        )
        return [dict(row) for row in result.mappings()]

    async def keyword(self, params, weights, config):
        if not weights:
            return []
        result = await self.db.execute(
            text(
                "WITH scope AS NOT MATERIALIZED ("
                + SCOPE
                + """),
            corpus AS (SELECT knowledge_base_id, count(*)::float8 AS n,
                greatest(avg(token_count), 1)::float8 AS avgdl FROM scope GROUP BY knowledge_base_id),
            query_terms AS (SELECT key AS term, value::float8 AS weight FROM jsonb_each_text(CAST(:weights AS jsonb))),
            matches AS (SELECT s.chunk_id, s.knowledge_base_id, s.token_count, t.term, t.weight,
                (s.terms->>t.term)::float8 AS tf
                FROM scope s JOIN query_terms t ON s.terms ? t.term
                WHERE s.term_list && CAST(:words AS varchar[])),
            df AS (SELECT knowledge_base_id, term, count(*)::float8 AS df FROM matches GROUP BY knowledge_base_id, term),
            scores AS (SELECT m.chunk_id, sum(m.weight * ln(1 + (c.n - df.df + 0.5)/(df.df + 0.5)) *
                m.tf * 2.2 / (m.tf + 1.2 * (0.25 + 0.75 * m.token_count / c.avgdl))) AS score
                FROM matches m JOIN corpus c USING (knowledge_base_id) JOIN df USING (knowledge_base_id, term)
                GROUP BY m.chunk_id)
            SELECT chunk_id, score, count(*) OVER () AS eligible FROM scores
            WHERE score > 0 AND score >= :threshold ORDER BY score DESC, chunk_id LIMIT :limit
        """
            ),
            {
                **params,
                "weights": json.dumps(weights),
                "words": list(weights),
                "threshold": config.keyword_threshold,
                "limit": config.candidate_limit,
            },
        )
        return [dict(row) for row in result.mappings()]

    async def metadata(self, params, ids):
        if not ids:
            return []
        stmt = (
            select(KnowledgeChunk, KnowledgeDocument, KnowledgeBase.name)
            .options(defer(KnowledgeChunk.embedding))
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .join(KnowledgeBase, KnowledgeDocument.knowledge_base_id == KnowledgeBase.id)
            .join(KnowledgeSearchChunk, KnowledgeSearchChunk.chunk_id == KnowledgeChunk.id)
            .where(
                KnowledgeBase.user_id == self.user_id,
                KnowledgeBase.id.in_(params["base_ids"]),
                KnowledgeChunk.id.in_(ids),
                KnowledgeDocument.status == "ready",
                KnowledgeDocument.embedding_model == params["model"],
                KnowledgeSearchChunk.generation_id == KnowledgeDocument.job_id,
                KnowledgeSearchChunk.model_fingerprint == params["fingerprint"],
                KnowledgeSearchChunk.tokenizer_version == params["tokenizer"],
            )
        )
        if not params["all_documents"]:
            stmt = stmt.where(KnowledgeDocument.id.in_(params["document_ids"]))
        return (await self.db.execute(stmt)).all()

    async def neighbors(self, params, seeds, window):
        if not seeds:
            return []
        from sqlalchemy import or_

        stmt = select(KnowledgeChunk.id).where(
            or_(
                *[
                    (KnowledgeChunk.document_id == UUID(seed["document_id"]))
                    & KnowledgeChunk.position.between(
                        seed["position"] - window, seed["position"] + window
                    )
                    for seed in seeds
                ]
            )
        )
        ids = list(await self.db.scalars(stmt))
        # Metadata rechecks account, source state and fingerprint; generation too.
        generations = {s["document_id"]: s["index_generation"] for s in seeds}
        return [
            row
            for row in await self.metadata(params, ids)
            if str(row[1].job_id) == generations.get(str(row[1].id))
        ]

    async def add(self, rows):
        self.db.add_all(rows)
        await self.db.flush()
