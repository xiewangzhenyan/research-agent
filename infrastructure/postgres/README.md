# PostgreSQL with pgvector

This image preserves the exact deployed PostgreSQL 16.14 Alpine base digest and adds pgvector 0.8.0. Build with `docker build -t agent-postgres:16.14-vector0.8.0 infrastructure/postgres`. No PostgreSQL major or minor version change is included.

The source archive is vendored from https://github.com/pgvector/pgvector/releases/tag/v0.8.0 and verified by SHA-256 in the Dockerfile. PostgreSQL License: [LICENSE.pgvector](LICENSE.pgvector). The extension is built without architecture-specific optimization flags or LLVM, then copied into a clean copy of the same base image.

Before replacing a database container: stop writers, save a restricted database dump and the old image digest, restore into a disposable database using the new image, apply migrations, and verify retrieval and account isolation. Preserve the production data volume. Never run `docker compose down -v`.

Application read selection is controlled by `RAG_SEARCH_BACKEND=legacy|postgres`. `legacy` keeps the old array-vector path; new ingestion dual-writes both indexes in one transaction. `postgres` requires all ready chunks in the authorized query scope to have matching model-file fingerprint, tokenizer version, document generation and content hash. Missing/stale rows fail closed. Do not activate it until this coverage is complete.

Unknown historical vectors are not copied just because they have 512 dimensions. Rebuild each owned document with `python -m cli.commands cmd rebuild-search --user-id UUID --document-id UUID`, which re-embeds source text and checks the document generation before atomically publishing the shadow rows. Original chunks and citation snapshots stay in place. A concurrent edit invalidates the rebuild.

The first read implementation performs exact pgvector cosine search in the authorized scope. No HNSW/ANN index is enabled. Chinese BM25 uses pinned jieba search tokenization (HMM disabled), per-selected-base corpus statistics, JSONB term frequencies and a GIN term-list index. Query doc filters narrow that corpus. Only bounded candidate IDs, scores and selected source text return to the application.

Rollback the application by selecting `legacy` and using the previous application images. Keep the new database image and additive schema so new data remains readable and writes continue to invalidate stale index rows. Returning to the old PostgreSQL image requires removing extension-dependent objects in a separate planned procedure; never remove vector.so while the database still contains vector objects.
