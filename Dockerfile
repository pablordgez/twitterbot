# Builder stage
FROM python:3.12-slim AS builder

WORKDIR /build

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -r requirements.txt

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=twitterbot.settings \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Create a non-root user and set up directories
RUN groupadd -r appgroup && useradd -r -g appgroup appuser && \
    mkdir -p /app/data /app/staticfiles /ms-playwright && \
    chown -R appuser:appgroup /app/data /app/staticfiles /ms-playwright

# Install the wheels from the builder stage
COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache /wheels/* && \
    python -m playwright install --with-deps chromium && \
    rm -rf /wheels

# Copy application code
COPY --chown=appuser:appgroup . .

# Collect static files
RUN APP_SECRET_KEY=dummy ENCRYPTION_KEY=EmjUgOkbw1cbh3eHw3fuhLBggg_tVsZZRbDqDDnzowk= python manage.py collectstatic --noinput

# Switch to the non-root user
USER appuser

# Expose port
EXPOSE 8080

# Set entrypoint
CMD ["python", "entrypoint.py"]
