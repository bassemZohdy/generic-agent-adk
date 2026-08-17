FROM ghcr.io/astral-sh/uv:0.7.5 AS uv
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY --from=uv /uv /uvx /usr/local/bin/

# Harden the base image: remove the bundled pip/ensurepip and any pre-existing
# setuptools/wheel packages so scanners only see the freshly installed versions.
RUN rm -rf \
      /usr/local/bin/pip* \
      /usr/local/lib/python3.13/ensurepip \
      /usr/local/lib/python3.13/site-packages/pip \
      /usr/local/lib/python3.13/site-packages/pip-*.dist-info \
      /usr/local/lib/python3.13/site-packages/setuptools \
      /usr/local/lib/python3.13/site-packages/setuptools-*.dist-info \
      /usr/local/lib/python3.13/site-packages/_distutils_hack \
      /usr/local/lib/python3.13/site-packages/distutils-precedence.pth \
      /usr/local/lib/python3.13/site-packages/wheel \
      /usr/local/lib/python3.13/site-packages/wheel-*.dist-info \
    && uv pip install --system --force-reinstall "setuptools>=78.1.1"

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./

RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev \
    && mkdir -p /app/.adk/artifacts \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app \
    && uv cache clean

USER appuser

EXPOSE 8002

CMD ["sh", "-c", "uvicorn basic_agent.interfaces.rest:app --host 0.0.0.0 --port ${PORT:-8002} --limit-concurrency 100"]
