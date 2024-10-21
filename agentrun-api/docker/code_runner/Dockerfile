FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Security best practices
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

# Create a non-root user with its home directory
RUN useradd --create-home pythonuser
USER pythonuser
WORKDIR /code

# Optional: Only if you have specific dependencies
COPY requirements.txt .
RUN uv venv && \
    . .venv/bin/activate && \
    uv pip install -r requirements.txt 