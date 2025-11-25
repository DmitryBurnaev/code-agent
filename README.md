# Code Agent Application

A configurable proxy application designed to route and manage requests across multiple LLM (Large Language Model) vendors.

## Installation

For detailed server installation instructions, see [INSTALL.md](INSTALL.md).

## Development

### Prerequisites

- Docker and Docker Compose
- Python 3.13 (for local development)
- uv package manager

### Useful commands

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

### CLI usages

1. Generate Secrets
   ```bash
   # Generate secure secrets and write them to .env file
   uv run python -m src.cli.generate_secrets
   
   # This will automatically:
   # - Generate random secrets for APP_SECRET_KEY, VENDOR_ENCRYPTION_KEY, DB_PASSWORD, ADMIN_PASSWORD
   # - Append them to .env file with "# Generated secrets" comment
   # - Set file permissions to 600 for security
   ```

2. Simple AI Client
   ```bash   
   # usage: simple_ai_client.py [-h] [--vendor VENDOR] [--vendor-url VENDOR_URL] [--model MODEL] [--token TOKEN] [--stream] [--prompt PROMPT]
   #
   # CLI for interacting with AI models (DeepSeek/OpenAI compatible API)
   #
   # options:
   #    -h, --help            show this help message and exit
   #    --vendor VENDOR       AI vendor (deepseek, ...)
   #    --vendor-url VENDOR_URL
   #                         AI vendor URL (https://api.deepseek.com/v1, ...)
   #    --model MODEL         Model name (e.g. deepseek-chat)
   #    --token TOKEN         Authorization token (or environment variable)
   #    --stream              Stream mode
   #    --prompt PROMPT       Prompt text

   # Example of running simple_ai_client via CLI
   uv run python -m src.cli.simple_ai_client --vendor openai --prompt "Hi, how are you?" --user-id 1

   # Example with additional parameters
   uv run python -m src.cli.simple_ai_client --vendor openai --prompt "Tell me a joke" \
     --user-id 1 --model gpt-3.5-turbo --temperature 0.7

   # To get help on all available options
   uv run python -m src.cli.simple_ai_client --help
   ```
3. User management (change password)
   ```bash
   # Usage: python -m src.modules.cli.management [OPTIONS]
   # Change the admin password.   
   # Options:
   #   --help                           Show this help message
   #   --username TEXT                  Admin username
   #   --random-password                Generate a random password.
   #   --random-password-length INTEGER Set length of generated random password.

   # Example: change password for admin to auto-generated password with length 32 symbols
   uv run python -m src.modules.cli.management --username admin --random-password --random-password-length 32

   # Example: change password for my-user to password from stdin
   uv run python -m src.modules.cli.management --username my-user
   # ===
   # Changing admin password...
   # Set a new password for my-user
   # New Password: <INPUT>
   # Repeat for confirmation: <INPUT>
   ```

## Swagger Documentation

When enabled, the Swagger documentation is available at `/docs` and ReDoc at `/redoc`.

## Vendor API Key Encryption

The application now supports encrypted storage of vendor API keys using AES-256-GCM encryption. This ensures that sensitive API credentials are not stored in plaintext in the database.

### Encryption Setup

The encryption key is now automatically generated along with other secrets using the `make secrets` command. See the [Environment Setup](#environment-setup) section above for detailed instructions.

The encryption key (`VENDOR_ENCRYPTION_KEY`) is automatically:
- Generated with 32 characters of secure random data
- Written to your `.env` file
- Protected with proper file permissions (600)

API keys will be automatically encrypted when:
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
   
   This command will automatically:
   - Generate secure random secrets for your application
   - Write them directly to your `.env` file with a "# Generated secrets" comment
   - Set proper file permissions (600) for security
   - Display success messages in the console

   The generated secrets include:
   - `APP_SECRET_KEY` - Secret key for the application
   - `VENDOR_ENCRYPTION_KEY` - Key for encrypting vendor API keys
   - `DB_PASSWORD` - Database password
   - `ADMIN_PASSWORD` - Default admin password

3. Review and update your `.env` file with any additional required settings.

### Environment Variables

| Variable                      | Type   |     Default | Required | Description                                        |
|-------------------------------|--------|------------:|:--------:|----------------------------------------------------|
| API_DOCS_ENABLED              | bool   |       false |          | Enable FastAPI docs (Swagger/ReDoc)                |
| APP_SECRET_KEY                | string |           - |   yes    | Secret key                                         |
| APP_HOST                      | string |   localhost |          | Host address for the application                   |
| APP_PORT                      | int    |        8003 |          | Port for the application                           |
| JWT_ALGORITHM                 | string |       HS256 |          | JWT algorithm                                      |
| HTTP_PROXY_URL                | string |           - |          | Socks5 Proxy URL                                   |
| VENDOR_DEFAULT_TIMEOUT        | int    |          30 |          | Default HTTP timeout for vendor requests (seconds) |
| VENDOR_DEFAULT_RETRIES        | int    |           3 |          | Default HTTP retry attempts for vendor requests    |
| VENDOR_ENCRYPTION_KEY         | string |           - |   yes    | Secret key for vendor API key encryption           |

### Admin Settings (AdminSettings, env prefix `ADMIN_`)

| Variable                      | Type   |         Default | Required | Description                             |
|-------------------------------|--------|----------------:|:--------:|-----------------------------------------|
| ADMIN_USERNAME                | string |           admin |          | Default admin username                  |
| ADMIN_PASSWORD                | string |     code-admin! |          | Default (initial) admin password        |
| ADMIN_SESSION_EXPIRATION_TIME | int    |          172800 |          | Admin session expiration time (seconds) |
| ADMIN_BASE_URL                | string |           /cadm |          | Admin panel base URL                    |
| ADMIN_TITLE                   | string | CodeAgent Admin |          | Admin panel title                       |

### Logging Settings (LogSettings, env prefix `LOG_`)

| Variable               | Type   |                                                           Default | Required | Description                                      |
|------------------------|--------|------------------------------------------------------------------:|:--------:|--------------------------------------------------|
| LOG_LEVEL              | string |                                                              INFO |          | One of DEBUG / INFO / WARNING / ERROR / CRITICAL |
| LOG_SKIP_STATIC_ACCESS | bool   |                                                             false |          | Skip logging access to static files              |
| LOG_FORMAT             | string | [%(asctime)s] %(levelname)s [%(filename)s:%(lineno)s] %(message)s |          | Log message format                               |
| LOG_DATEFMT            | string |                                                 %d.%m.%Y %H:%M:%S |          | Date format for log timestamps                   |

### Feature Flags (FlagsSettings, env prefix `FLAG_`)

| Variable          | Type | Default | Required | Description         |
|-------------------|------|--------:|:--------:|---------------------|
| FLAG_OFFLINE_MODE | bool |   false |          | Enable offline mode |

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

| Variable     | Type   | Default |       Required       | Description                                                                 |
|--------------|--------|--------:|:--------------------:|-----------------------------------------------------------------------------|
| APP_SERVICE  | string |       - |   yes (container)    | Selects entrypoint behavior: `web` / `test` / `lint`                        | 
| DOCKER_IMAGE | string |       - | yes (docker-compose) | Image tag used by `docker-compose.yml`                                      |
| APP_PORT     | int    |       - | yes (docker-compose) | Port mapping for `docker-compose.yml` (should match application `APP_PORT`) |
