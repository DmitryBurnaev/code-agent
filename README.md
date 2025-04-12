# System Info API

A simple FastAPI application that provides system information and health check endpoints.

## Prerequisites

- Docker and Docker Compose
- Python 3.13 (for local development)
- uv package manager

## Service Installation

### Upload config files
```shell
TARGET_SERVER="remote-server-ip"
TARGET_DIR="/opt/code-agent"
ssh ${TARGET_SERVER} -C  "mkdir -P ${TARGET_DIR}"
scp etc/* ${TARGET_SERVER}:${TARGET_DIR}
```

### Prepare service
```shell
TARGET_SERVER="remote-server-ip"
TARGET_DIR="/opt/code-agent"

ssh ${TARGET_SERVER}

# on the remote server
sudo su

# prepare user and group (NOTE: ID 1005 is imported ID for group)
groupadd --system code-agent-srv --gid 1005
useradd --no-log-init --system --gid code-agent-srv --uid 1005 code-agent-srv

chown code-agent-srv:code-agent-srv -R /opt/code-agent/
usermod -G docker code-agent-srv

# copy config to systemd
ln -s ${TARGET_DIR}/code-agent.service /etc/systemd/system/code-agent.service
systemctl daemon-reload
systemctl enable code-agent.service
systemctl start code-agent.service

# see logs
journalctl -u code-agent
```

## Development

1. Install venv
    ```shell
    make install
    ```
2. Format changes
   ```shell
   make format
   ```
3. Lint changes 
   ```shell
   make lint
   ```
4. Run tests 
   ```shell
   make test
   ```

## Swagger Documentation

When enabled, the Swagger documentation is available at `/docs` and ReDoc at `/redoc`.

## Environment Variables

| Variable Name   | Description                                | Default Value          |
|-----------------|--------------------------------------------|------------------------|
| LOG_LEVEL       | Sets the logging level for the application | INFO                   |
| AUTH_API_TOKEN  | API token for authentication               | (required, no default) |
| PROVIDERS       | List of providers in JSON format           | []                     |
| SWAGGER_ENABLED | Enables/disables Swagger documentation     | true                   |
| APP_HOST        | Host address for the application           | localhost              |
| APP_PORT        | Port number for the application            | 8003                   |
