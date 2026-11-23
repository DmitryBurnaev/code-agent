# syntax=docker/dockerfile:1
FROM --platform=$BUILDPLATFORM buildpack-deps:trixie-curl AS cursor-cli
ARG TARGETARCH
ARG CURSOR_CLI_VERSION=2026.11.19-f005e9d

RUN set -eu; \
    case "$TARGETARCH" in \
        amd64) cursor_arch=x64 ;; \
        arm64) cursor_arch=arm64 ;; \
        *) echo "Unsupported Cursor CLI architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
        "https://downloads.cursor.com/lab/${CURSOR_CLI_VERSION}/linux/${cursor_arch}/agent-cli-package.tar.gz" \
        --output /tmp/cursor-cli.tar.gz; \
    mkdir -p /opt/cursor; \
    tar -xzf /tmp/cursor-cli.tar.gz -C /opt/cursor --no-same-owner; \
    test -x /opt/cursor/dist-package/cursor-agent; \
    rm /tmp/cursor-cli.tar.gz

FROM python:3.14-slim-trixie
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes -r requirements.txt \
    && groupadd --gid 1008 cursor-agent \
    && useradd --uid 1008 --gid 1008 --no-create-home cursor-agent \
    && mkdir -p /var/lib/cursor-agent

COPY --from=cursor-cli /opt/cursor /opt/cursor
COPY __init__.py app.py protocol.py ./agents/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
RUN python -c 'from agents.app import app_factory; app_factory()' \
    && /opt/cursor/dist-package/cursor-agent --version
CMD ["uvicorn", "agents.app:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
