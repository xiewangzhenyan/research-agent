FROM postgres:16-alpine@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777 AS builder
COPY vendor/pgvector-0.8.0.tar.gz /tmp/pgvector.tar.gz
RUN echo '867a2c328d4928a5a9d6f052cd3bc78c7d60228a9b914ad32aa3db88e9de27b0  /tmp/pgvector.tar.gz' | sha256sum -c - \
 && apk add --no-cache build-base \
 && tar -xzf /tmp/pgvector.tar.gz -C /tmp \
 && cd /tmp/pgvector-0.8.0 && make OPTFLAGS='' with_llvm=no && make install with_llvm=no
FROM postgres:16-alpine@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777
COPY --from=builder /usr/local/lib/postgresql/vector.so /usr/local/lib/postgresql/
COPY --from=builder /usr/local/share/postgresql/extension/vector* /usr/local/share/postgresql/extension/
