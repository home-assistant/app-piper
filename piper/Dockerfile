# Base image updated by Renovate, update versionCompatibility on Alpine base bump
ARG BUILD_FROM=ghcr.io/home-assistant/base-debian:trixie-2026.11.0@sha256:d996c8f8ef0096a1ac3756766149b31b8171afc663068cc192f2bcab20f1b8c9
FROM ${BUILD_FROM}

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install Piper
WORKDIR /usr/src
ARG WYOMING_PIPER_VERSION=2.5.3
ARG UV_VERSION=0.13.7

ENV WYOMING_PIPER_VERSION=${WYOMING_PIPER_VERSION}

# There is no virtual environment in this image
ENV UV_SYSTEM_PYTHON=true

# A unique approach is taken in this image to dependency management. Different
# voices (th, ja) and backends (omnivoice) require large Python dependencies.
# Rather than making everyone pay the disk space for them, a new "pack" s6
# dependency installs them on startup when enabled.
#
# Importantly, the uv cache is stored in /data and because uv caches wheels
# uncompressed already, the relevant files can be symlinked into the container's
# filesystem with virtually no overhead. This only works if we target the system
# Python because the build time and runtime dependencies need to be layered.
# Hence, there is no virtual environment anymore.

RUN \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
    \
    # Install into the system interpreter rather than a venv
    && rm -f /usr/lib/python3*/EXTERNALLY-MANAGED \
    # pip is only here to bootstrap uv
    && pip3 install --no-cache-dir "uv==${UV_VERSION}" \
    \
    # --no-cache: the runtime cache lives in /data and must not be seeded with
    # build-time downloads baked into the image.
    && uv pip install --no-cache \
        "wyoming-piper[zeroconf,zh,web] @ https://github.com/rhasspy/wyoming-piper/archive/refs/tags/v${WYOMING_PIPER_VERSION}.tar.gz" \
    \
    && rm -rf /var/lib/apt/lists/*

ENV ORT_DISABLE_TELEMETRY=1
WORKDIR /
COPY rootfs /

# A Describe/Info round trip rather than a bare port check
HEALTHCHECK --start-period=30m --interval=30s --timeout=20s --retries=3 \
    CMD /usr/bin/python3 -m wyoming_piper.health_check \
        --uri tcp://127.0.0.1:10200 \
        || exit 1

LABEL \
    org.opencontainers.image.title="Home Assistant App: Piper" \
    org.opencontainers.image.description="Text-to-speech with Piper" \
    org.opencontainers.image.source="https://github.com/home-assistant/app-piper" \
    org.opencontainers.image.licenses="Apache License 2.0"
