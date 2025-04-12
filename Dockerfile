# copy source code
FROM alpine:3.21 AS code-layer
WORKDIR /usr/src

COPY src ./src
COPY etc/docker-entrypoint .

# copy source code
FROM python:3.13-alpine AS requirements-layer
WORKDIR /usr/src
ARG DEV_DEPS="false"
ARG UV_VERSION=0.6.14

COPY pyproject.toml .
COPY uv.lock .

RUN pip install uv==${UV_VERSION} && \
	  if [ "${DEV_DEPS}" = "true" ]; then \
      uv export --format requirements-txt --frozen --output-file requirements.txt; \
    else \
      uv export --format requirements-txt --frozen --no-dev --output-file requirements.txt; \
    fi


FROM python:3.13-alpine AS service
ARG PIP_DEFAULT_TIMEOUT=300
WORKDIR /app

COPY --from=requirements-layer /usr/src/requirements.txt .

RUN pip install --timeout "${PIP_DEFAULT_TIMEOUT}" \
      --no-cache-dir --require-hashes \
      -r requirements.txt

RUN addgroup -S code-agent -g 1005 && \
    adduser -S -G code-agent -u 1005 -H code-agent

USER code-agent

COPY --from=code-layer --chown=code-agent:code-agent /usr/src .

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

ENTRYPOINT ["/bin/sh", "/app/docker-entrypoint"]
