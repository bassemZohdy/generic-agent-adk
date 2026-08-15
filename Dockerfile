FROM ghcr.io/astral-sh/uv:0.7.5 AS uv
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY --from=uv /uv /uvx /usr/local/bin/

# Upgrade system setuptools to avoid base-image CVEs before installing the project.
RUN uv pip install --system "setuptools>=78.1.1"

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./

RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev \
    && mkdir -p /app/.adk/artifacts \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8002

CMD ["sh", "-c", "uvicorn basic_agent.api_server:app --host 0.0.0.0 --port ${PORT:-8002} --limit-concurrency 100"]
