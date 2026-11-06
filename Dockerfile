# Self-hosting the whole thing: the container refreshes the index and serves the
# dashboard. Pass GEMINI_API_KEY (free tier) at runtime, never bake it in.
#
#   docker build -t ai-free-index .
#   docker run --rm -p 8000:8000 -e GEMINI_API_KEY=... ai-free-index
#
# For a refresh schedule add the compose file, or point a cron at
# `docker exec <container> python -m aiindex build`.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY config ./config
COPY src ./src
COPY web ./web
COPY docs ./docs

RUN python -m pip install --no-cache-dir -e .

EXPOSE 8000

# Build once on start (cheap without a key), then serve on all interfaces.
CMD ["python", "-m", "aiindex", "serve", "--build", "--host", "0.0.0.0", "--port", "8000"]
