# Multi-stage build for AWS App Runner - Alpine Linux (minimal, secure)
FROM python:3.11-alpine AS builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install build dependencies and apply all security updates
RUN apk upgrade --no-cache && \
    apk add --no-cache \
    gcc \
    musl-dev \
    postgresql-dev \
    python3-dev \
    libffi-dev \
    openssl-dev

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir --upgrade pip && \
    pip install --user --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-alpine

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/home/app/.local/bin:$PATH

# Upgrade all packages and install runtime dependencies only
RUN apk upgrade --no-cache && \
    apk add --no-cache \
    libpq \
    curl \
    ca-certificates \
    libffi \
    && rm -rf /var/cache/apk/*

# Create non-root user (Alpine syntax)
RUN adduser -D -s /bin/sh app

# Copy Python packages from builder
COPY --from=builder /root/.local /home/app/.local

# Set work directory and copy app
WORKDIR /app
COPY --chown=app:app app ./app
COPY --chown=app:app start.sh .

# Prepare log directory for production file logging
RUN mkdir -p /var/log/refocused \
    && chown -R app:app /var/log/refocused

# Switch to non-root user
USER app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the production application directly with proxy headers for App Runner
CMD ["uvicorn", "app.main_production:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
