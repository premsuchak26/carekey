# CareKey - Production Dockerfile
# Base: Python 3.12 Slim Linux image
FROM python:3.12-slim AS runtime

# Prevent Python from writing .pyc files and enable unbuffered streaming
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# Set working directory
WORKDIR /app

# Create a dedicated non-root application user and group
RUN groupadd --gid 10001 appgroup && \
    useradd --uid 10001 --gid appgroup --shell /bin/bash --create-home appuser

# Install production dependencies first to leverage layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY --chown=appuser:appgroup app/ ./app/
COPY --chown=appuser:appgroup scripts/ ./scripts/
COPY --chown=appuser:appgroup pyproject.toml .

# Switch to non-root user
USER appuser

# Expose standard Cloud Run application port
EXPOSE 8080

# Health check without external dependencies (pure Python urllib)
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import os, urllib.request; port = os.environ.get('PORT', '8080'); urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz')" || exit 1

# Launch ASGI server via uvicorn listening on PORT environment variable, non-root user, no reload
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
