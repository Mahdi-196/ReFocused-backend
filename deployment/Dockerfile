# Multi-stage build for Lambda-ready deployment using AWS Lambda base image
FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.11 as builder

# Install build dependencies for Lambda x86_64 (using AWS Lambda environment)
RUN yum update -y && yum install -y \
    gcc \
    gcc-c++ \
    make \
    postgresql-devel \
    libffi-devel \
    openssl-devel \
    zip \
    && yum clean all

# Copy requirements and install dependencies for x86_64
COPY requirements.txt .
RUN pip install --target /lambda-packages --no-cache-dir --upgrade pip && \
    pip install --target /lambda-packages --no-cache-dir -r requirements.txt

# Lambda packaging stage
FROM --platform=linux/amd64 python:3.11-slim as lambda-package

# Install zip utility
RUN apt-get update && apt-get install -y zip && rm -rf /var/lib/apt/lists/*

# Copy Lambda packages
COPY --from=builder /lambda-packages /lambda-packages

# Copy application code
WORKDIR /lambda-packages
COPY app ./app
COPY lambda_function.py .
COPY alembic.ini .

# Create deployment package (ensure no stale zip remains)
RUN rm -f /refocused-production-lambda.zip && \
    zip -r9 /refocused-production-lambda.zip . -x "*.pyc" "*__pycache__*" "*.git*"

# Production Docker stage for local development
FROM --platform=linux/amd64 python:3.11-slim

# Set environment variables for Docker execution
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DOCKER_ENV=true

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install Python dependencies
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Set work directory and copy app
WORKDIR /app
COPY app ./app
COPY alembic.ini ./
COPY requirements.txt ./

# Prepare log directory for production file logging
RUN mkdir -p /var/log/refocused

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Lambda deployment package extraction (for build output)
FROM scratch AS lambda-output
COPY --from=lambda-package /refocused-production-lambda.zip /

# Run the production application
CMD ["sh", "-c", "python3 -m uvicorn app.main_production:app --host 0.0.0.0 --port 8000"]