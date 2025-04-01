FROM debian:bookworm-slim

# Install Python 3.13 and required system dependencies
RUN apt-get update && apt-get install -y \
    python3.13 \
    python3.13-venv \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Create and activate virtual environment
RUN python3.13 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install uv
RUN pip install uv

# Set working directory
WORKDIR /app

# Copy project files and install dependencies
COPY pyproject.toml .
RUN uv pip install .

# Copy application code
COPY app/ app/

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"] 