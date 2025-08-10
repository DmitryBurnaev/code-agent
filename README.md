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
scp -r etc/* ${TARGET_SERVER}:${TARGET_DIR}
```

### Prepare service
```shell
ssh ${TARGET_SERVER}

# on the remote server
sudo su

export TARGET_SERVER="remote-server-ip"
export TARGET_DIR="/opt/code-agent"

# prepare user and group (NOTE: ID 1005 is imported ID for group)
groupadd --system code-agent-srv --gid 1007
useradd --no-log-init --system --gid code-agent-srv --uid 1007 code-agent-srv

chown code-agent-srv:code-agent-srv -R /opt/code-agent/
usermod -a -G docker code-agent-srv
chmod -R 660 /opt/code-agent # all files can be rewritable by code-agent-srv group
chmod -R ug+x /opt/code-agent/bin # code-agent-srv group can execute bin files (for service running)
chmod ug+x /opt/code-agent # code-agent-srv group can execute bin files (for service running)

# copy config to systemd
ln -s ${TARGET_DIR}/code-agent.service /etc/systemd/system/code-agent.service
systemctl daemon-reload
systemctl enable code-agent.service
systemctl start code-agent.service

# see status and logs
systemctl status code-agent.service
journalctl -u code-agent
```
### Prepare for deployment
1. Prepare "deploy" user
2. Allow access to service's group (to make changes in specific directories)
   ```shell
   usermod -a -G code-agent-srv deploy
   ```
3. Allow "deploy" user manipulate with code-agent's service
   ```shell
   visudo -f /etc/sudoers.d/deploy
   # add these lines:
   deploy ALL = NOPASSWD: /bin/systemctl restart code-agent.service
   deploy ALL = NOPASSWD: /bin/systemctl show -p ActiveState --value code-agent
   ```

### Nginx Configuration

The service requires Nginx as a reverse proxy to handle:
- Domain-based routing (code.example.com)
- Security layer (authorization header check)
- API endpoint protection (only /api/* endpoints are accessible)

To configure Nginx:

1. Copy the configuration file from `etc/nginx.conf` to your Nginx configuration directory:
   ```bash
   sudo cp etc/nginx.conf /etc/nginx/sites-available/code-agent.conf
   ```

2. Create a symbolic link to enable the site:
   ```bash
   sudo ln -s /etc/nginx/sites-available/code-agent.conf /etc/nginx/sites-enabled/
   ```

3. Update the configuration:
   - Replace `code.example.com` with your domain
   - Update the port in `proxy_pass` directive to match your application port
   - Ensure the `Authorization` header is properly set in all API requests

4. Test and reload Nginx:
   ```bash
   sudo nginx -t
   sudo nginx -s reload
   ```

5. Set up HTTPS with Certbot (recommended):
   ```bash
   # Install Certbot and Nginx plugin
   sudo apt update
   sudo apt install certbot python3-certbot-nginx
   
   # Obtain and install SSL certificate
   sudo certbot --nginx -d code.example.com
   
   # Verify auto-renewal is enabled
   sudo systemctl status certbot.timer
   ```

After running Certbot, it will:
- Automatically modify your Nginx configuration to handle HTTPS
- Set up automatic certificate renewal (every 90 days)
- Configure secure SSL settings
- Optionally redirect all HTTP traffic to HTTPS (recommended)

Note: Make sure your domain's DNS records are properly configured and pointing to your server before running Certbot.

## Development

1. Install venv
    ```shell
    make install
    ```
2. Generate secrets for environment setup
   ```shell
   make secrets
   ```
3. Format changes
   ```shell
   make format
   ```
4. Lint changes 
   ```shell
   make lint
   ```
5. Run tests 
   ```shell
   make test
   ```


## CLI usages

1. Simple AI Client
   ```bash   
   usage: simple_ai_client.py [-h] [--vendor VENDOR] [--vendor-url VENDOR_URL] [--model MODEL] [--token TOKEN] [--stream] [--prompt PROMPT]

   CLI for interacting with AI models (DeepSeek/OpenAI compatible API)

   options:
   -h, --help            show this help message and exit
   --vendor VENDOR       AI vendor (deepseek, ...)
   --vendor-url VENDOR_URL
                           AI vendor URL (https://api.deepseek.com/v1, ...)
   --model MODEL         Model name (e.g. deepseek-chat)
   --token TOKEN         Authorization token (or environment variable)
   --stream              Stream mode
   --prompt PROMPT       Prompt text

   # Example of running simple_ai_client via CLI
   python -m src.cli.simple_ai_client --vendor openai --prompt "Hi, how are you?" --user-id 1

   # Example with additional parameters
   python -m src.cli.simple_ai_client --vendor openai --prompt "Tell me a joke" \
     --user-id 1 --model gpt-3.5-turbo --temperature 0.7

   # To get help on all available options
   python -m src.cli.simple_ai_client --help
   ```


## Swagger Documentation

When enabled, the Swagger documentation is available at `/docs` and ReDoc at `/redoc`.

## Vendor API Key Encryption

The application now supports encrypted storage of vendor API keys using AES-256-GCM encryption. This ensures that sensitive API credentials are not stored in plaintext in the database.

### Setup Encryption

The encryption key is now automatically generated along with other secrets using the `make secrets` command. See the [Environment Setup](#environment-setup) section above for detailed instructions.

Alternatively, you can generate only the encryption key manually:
   ```bash
   python -m src.cli.generate_encryption_key
   ```

3. API keys will be automatically encrypted when:
   - Creating new vendors through the admin interface
   - Updating existing vendor API keys

## Environment Setup

### Quick Start

1. Copy the environment template:
   ```bash
   cp .env.template .env
   ```

2. Generate secure secrets for your environment:
   ```bash
   make secrets
   ```

3. Copy the generated secrets to your `.env` file. The command will output something like:
   ```bash
   SECRET_KEY=your-generated-secret-key
   VENDOR_ENCRYPTION_KEY=your-generated-encryption-key
   DB_PASSWORD=your-generated-db-password
   ADMIN_PASSWORD=your-generated-admin-password
   ```

4. Update your `.env` file with these generated values and other required settings.

### Environment Variables

| Variable                      | Type   | Default | Required | Description                                        |
|-------------------------------|--------|--------:|:--------:|----------------------------------------------------|
| DOCS_ENABLED                  | bool   |   false |          | Enable FastAPI docs (Swagger/ReDoc)                |
| SECRET_KEY                    | string |       - |   yes    | Secret key                                         |
| APP_HOST                      | string | 0.0.0.0 |          | Host address for the application                   |
| APP_PORT                      | int    |    8003 |          | Port for the application                           |
| LOG_LEVEL                     | string |    INFO |          | One of DEBUG / INFO / WARNING / ERROR / CRITICAL   |
| JWT_ALGORITHM                 | string |   HS256 |          | JWT algorithm                                      |
| HTTP_PROXY_URL                | string |       - |          | Socks5 Proxy URL                                   |
| VENDOR_DEFAULT_TIMEOUT        | int    |      30 |          | Default HTTP timeout for vendor requests (seconds) |
| VENDOR_DEFAULT_RETRIES        | int    |       3 |          | Default HTTP retry attempts for vendor requests    |
| VENDOR_CUSTOM_URL             | string |       - |          | API URL for 'custom' vendor                        |
| ADMIN_USERNAME                | string |   admin |          | Default admin username                             |
| ADMIN_PASSWORD                | string |       - |   yes    | Default admin password                             |
| ADMIN_SESSION_EXPIRATION_TIME | int    |  172800 |          | Admin session expiration time (seconds)            |
| OFFLINE_TEST_MODE             | bool   |   false |          | Enable offline test mode                           |
| VENDOR_ENCRYPTION_KEY         | string |       - |   yes    | Secret key for vendor API key encryption           |

### Database (DBSettings, env prefix `DB_`)

| Variable         | Type   |            Default | Required | Description       |
|------------------|--------|-------------------:|:--------:|-------------------|
| DB_DRIVER        | string | postgresql+asyncpg |          | SQLAlchemy driver |
| DB_HOST          | string |          localhost |          | Database host     |
| DB_PORT          | int    |               5432 |          | Database port     |
| DB_USERNAME      | string |           postgres |          | Database username |
| DB_PASSWORD      | string |           postgres |          | Database password |
| DB_DATABASE      | string |         code_agent |          | Database name     |
| DB_POOL_MIN_SIZE | int    |                  - |          | Pool min size     |
| DB_POOL_MAX_SIZE | int    |                  - |          | Pool max size     |
| DB_ECHO          | bool   |              false |          | SQLAlchemy echo   |

### CLI utilities

These are used by `src/cli/simple_ai_client.py`.

| Variable           | Type   | Default | Required | Description                                                             |
|--------------------|--------|--------:|:--------:|-------------------------------------------------------------------------|
| CLI_AI_API_TOKEN   | string |       - |   yes*   | Authorization token for the CLI (required unless `--token` is provided) |
| CLI_AI_TEMPERATURE | float  |     0.7 |          | Sampling temperature                                                    |
| CLI_AI_MAX_TOKENS  | int    |    1000 |          | Max tokens in completion                                                |
| CLI_AI_TIMEOUT     | int    |    3600 |          | HTTP timeout (seconds)                                                  |

### Container / Infra

| Variable     | Type   | Default |         Required         | Description                                                                     |
|--------------|--------|--------:|:------------------------:|---------------------------------------------------------------------------------|
| APP_SERVICE  | string |       - | yes (container)          | Selects entrypoint behavior: `web` / `test` / `lint`                            | 
| DOCKER_IMAGE | string |       - | yes (docker-compose) | Image tag used by `docker-compose.yml`                                      |
| APP_PORT     | int    |       - | yes (docker-compose) | Port mapping for `docker-compose.yml` (should match application `APP_PORT`) |


## In the Future
1. Use DB storage for
   1. AI credentials (encrypted) and user settings
      - [x] Create SQLAlchemy models for vendors and their settings
      - [x] Implement symmetric encryption for sensitive data (tokens)
      - [x] Create repository pattern for vendor data access
      - [x] Add migration system for database schema
      - [x] Implement vendor settings management API
      - [x] Add validation for vendor settings
      - [ ] Create backup/restore mechanism for vendor data
   2. request-response history (by completion-id)
   3. models usages 
2. Use redis-based cache instead of in-memory one
