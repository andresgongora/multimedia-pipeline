# syntax=docker/dockerfile:1
# -----------------------------------------------------------------------------
# silence-remover — auto-editor in Docker
#
# Build:   docker build -t silence-remover .
# Run:     docker run --rm -v "$(pwd)":/data silence-remover input.mp4 output.mp4
# -----------------------------------------------------------------------------
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && pip install --no-cache-dir auto-editor \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

COPY --chmod=755 entrypoint.sh /app/entrypoint.sh

WORKDIR /data
ENTRYPOINT ["/app/entrypoint.sh"]
