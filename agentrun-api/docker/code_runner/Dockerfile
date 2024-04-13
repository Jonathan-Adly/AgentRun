FROM python:3.12.2-slim-bullseye

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
# COPY --chown=appuser:appuser requirements.txt .
# RUN pip install --user -r requirements.txt
