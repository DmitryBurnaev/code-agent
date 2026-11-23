# copy source code
FROM scratch AS code-layer
WORKDIR /usr/src

COPY src ./src
COPY alembic.ini .
COPY etc/docker-entrypoint .

# copy source code
FROM python:3.14-slim-trixie AS requirements-layer
WORKDIR /usr/src
ARG DEV_DEPS="false"
ARG UV_VERSION=0.12.19

COPY pyproject.toml .
COPY uv.lock .

RUN pip install uv==${UV_VERSION} && \
	  if [ "${DEV_DEPS}" = "true" ]; then \
      uv export --format requirements-txt --locked --output-file requirements.txt; \
    else \
      uv export --format requirements-txt --locked --no-dev --output-file requirements.txt; \
    fi


FROM python:3.14-slim-trixie AS base
ARG PIP_DEFAULT_TIMEOUT=300
ARG PIP_VERSION=26.3
WORKDIR /app

COPY --from=requirements-layer /usr/src/requirements.txt .

RUN pip install --upgrade pip==${PIP_VERSION} && \
    pip install --timeout "${PIP_DEFAULT_TIMEOUT}" --no-cache-dir --require-hashes -r requirements.txt

RUN groupadd --gid 1007 code-agent && \
    useradd --uid 1007 --gid 1007 --no-create-home code-agent

USER code-agent

COPY --from=code-layer --chown=code-agent:code-agent /usr/src .
COPY --chown=code-agent:code-agent agents/__init__.py agents/protocol.py ./agents/

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV APP_PORT=8000

FROM base AS service

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import http.client, os; c = http.client.HTTPConnection('127.0.0.1', int(os.environ.get('APP_PORT', '8000')), timeout=3); c.request('GET', '/api/system/health/'); exit(0 if c.getresponse().status in (200, 401) else 1)"

ENTRYPOINT ["/bin/sh", "/app/docker-entrypoint"]

FROM base AS tests

COPY pyproject.toml .
COPY agents/app.py ./agents/

ENTRYPOINT ["/bin/sh", "/app/docker-entrypoint"]
