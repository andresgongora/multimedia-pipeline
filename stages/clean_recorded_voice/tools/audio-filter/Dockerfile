# syntax=docker/dockerfile:1
# -----------------------------------------------------------------------------
# Audio post-processing image — DeepFilterNet + ffmpeg chain + 2-pass loudnorm
# Base: Alpine (musl libc is safe — deep-filter binary is statically linked)
#
# Build (from project root):
#   docker build -t audio-filter .
#
# Run via host wrapper:
#   ./run.sh input.m4a outputs/out.m4a
#
# Run directly:
#   docker run --rm -v "$(pwd)":/data audio-filter input.m4a output.m4a
#   docker run --rm -v "$(pwd)":/data audio-filter input.m4a output.m4a --dfn-atten-db=30
# -----------------------------------------------------------------------------
FROM alpine:3.21

# ffmpeg — pulls libavcodec/libavfilter stack
# coreutils — provides GNU mktemp (BusyBox mktemp lacks --suffix support)
# curl — downloads the pinned DeepFilterNet release binary during image build
RUN apk add --no-cache \
      bash \
      coreutils \
      curl \
      ffmpeg

# Pinned x86_64 musl release binary; compatible with Alpine.
# Checksum recorded from the official v0.5.6 release asset (2026-07-15).
ARG DEEP_FILTER_VERSION=0.5.6
ARG DEEP_FILTER_SHA256=70775e251eee44c0f2451a1e833326cf8bcbbe304d3e7cd12851e6fce72ef7da
RUN mkdir -p /app/tools \
 && curl --fail --location --silent --show-error \
      --output /app/tools/deep-filter \
      "https://github.com/Rikorose/DeepFilterNet/releases/download/v${DEEP_FILTER_VERSION}/deep-filter-${DEEP_FILTER_VERSION}-x86_64-unknown-linux-musl" \
 && echo "${DEEP_FILTER_SHA256}  /app/tools/deep-filter" | sha256sum -c - \
 && chmod 755 /app/tools/deep-filter

# Copy processing script and entrypoint
COPY --chmod=755 scripts/filter.sh  /app/filter.sh
COPY --chmod=755 scripts/docker-entrypoint.sh   /app/run.sh

# Working directory; /tmp/audio_processing is created at runtime by the script
WORKDIR /app

ENTRYPOINT ["/app/run.sh"]
