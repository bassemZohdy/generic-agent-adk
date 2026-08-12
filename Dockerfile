FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY basic_agent ./basic_agent

RUN pip install --upgrade pip \
    && pip install . \
    && mkdir -p /app/.adk/artifacts

EXPOSE 8000

CMD ["adk", "web", "--host", "0.0.0.0", "--port", "8000", "/app/basic_agent"]
