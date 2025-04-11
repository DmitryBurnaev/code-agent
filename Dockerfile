# copy source code
FROM alpine:3.21 AS code-layer
WORKDIR /usr/src

COPY src ./src
COPY etc/docker-entrypoint .

FROM python:3.13-slim-bookworm AS service
ARG DEV_DEPS="false"
ARG UV_VERSION=0.6.14
WORKDIR /app

COPY pyproject.toml .
COPY uv.lock .

RUN apt-get update \
  && apt-get install -y --no-install-recommends python3-dev \
  && pip install uv==${UV_VERSION} \
  && uv sync \
	&& if [ "${DEV_DEPS}" = "true" ]; then \
	     echo "=== Install DEV dependencies ===" && \
	     uv sync --no-progress; \
     else \
       echo "=== Install PROD dependencies ===" && \
       uv sync --no-dev --no-progress; \
     fi \
  && apt-get remove python3-dev build-essential -y \
  && apt-get clean \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/* \
  && rm -rf /root/.cache/* && rm -rf /root/.config/* && rm -rf /root/.local/*

RUN groupadd --system code-agent --gid 1005 && \
    useradd --no-log-init --system --gid code-agent --uid 1005 code-agent

# Crontab: pre-setup
USER code-agent

COPY --from=code-layer --chown=code-agent:code-agent /usr/src .

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

ENTRYPOINT ["/bin/sh", "/app/docker-entrypoint"]
