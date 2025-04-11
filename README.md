# System Info API

A simple FastAPI application that provides system information and health check endpoints.

## Features

- System information endpoint (requires authentication)
- Health check endpoint
- Swagger documentation (optional)
- Docker support
- Environment-based configuration

## Prerequisites

- Docker and Docker Compose
- Python 3.13 (for local development)
- uv package manager

## Environment Variables

- `API_TOKEN`: Token required for accessing protected endpoints
- `SERVICE_TOKENS`: JSON object containing service tokens
- `ENABLE_SWAGGER`: Enable/disable Swagger documentation (default: false)

## Running with Docker

1. Build and start the service:
```bash
docker-compose up --build
```

2. The API will be available at `http://localhost:8000`

## Local Development

1. Create and activate a virtual environment:
```bash
python3.13 -m venv venv
source venv/bin/activate
```

2. Install dependencies using uv:
```bash
uv pip install .
```

3. Install test dependencies (optional):
```bash
uv pip install ".[test]"
```

4. Run the application:
```bash
uvicorn src.main:src --reload
```

## Testing

Run tests using pytest:
```bash
pytest
```

## API Endpoints

### GET /health
Health check endpoint that returns the current status and timestamp.

### GET /system-info
Returns current system information (requires authentication).
Headers:
- `Authorization: Bearer <API_TOKEN>`

## Swagger Documentation

When enabled, the Swagger documentation is available at `/docs` and ReDoc at `/redoc`.
