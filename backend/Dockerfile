
# Build stage
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Copy application
COPY . /app

# Install project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


# Runtime stage
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# Create the user before copying files: a later recursive chown duplicates
# the entire dependency tree in another image layer.
RUN adduser --disabled-password --gecos "" appuser && \
    install -d -o appuser -g appuser /app /app/media /app/data /app/chroma_data /app/models_cache

# Keep dependencies and source in separate layers. The context excludes .venv
# and runtime data; copying /app from the builder again would include both.
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --chown=appuser:appuser . /app

# Add venv to path
ENV PATH="/app/.venv/bin:$PATH"

USER appuser

EXPOSE 38001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:38001/api/v1/health')" || exit 1

CMD ["python", "-m", "cli.commands", "server", "run", "--host", "0.0.0.0", "--port", "38001"]
