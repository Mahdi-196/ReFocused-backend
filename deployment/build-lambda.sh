#!/bin/bash

# ReFocused Lambda Deployment Package Builder
# This script creates a deployment package for AWS Lambda with all dependencies

set -e  # Exit on any error

echo "🚀 Building ReFocused Lambda deployment package..."

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Clean up any previous builds
echo "🧹 Cleaning up previous builds..."
rm -rf "$SCRIPT_DIR/package"
rm -f "$SCRIPT_DIR/refocused-production-lambda.zip"

# Create package directory
mkdir -p "$SCRIPT_DIR/package"

# Copy application code
echo "📦 Copying application code..."
cp -r "$PROJECT_ROOT/app" "$SCRIPT_DIR/package/"
cp "$SCRIPT_DIR/lambda_function.py" "$SCRIPT_DIR/package/"
cp "$SCRIPT_DIR/alembic.ini" "$SCRIPT_DIR/package/"

# Create alembic directory structure if it doesn't exist
if [ ! -d "$PROJECT_ROOT/alembic" ]; then
    echo "⚠️  Warning: alembic directory not found in project root"
else
    cp -r "$PROJECT_ROOT/alembic" "$SCRIPT_DIR/package/"
fi

# Install dependencies using Docker for Lambda compatibility
echo "📚 Installing Python dependencies using Docker..."
cd "$SCRIPT_DIR"

# Use Docker to install dependencies in a Lambda-compatible environment (x86_64)
docker run --platform linux/amd64 --rm -v "$PWD":/workspace \
  --entrypoint "" \
  public.ecr.aws/lambda/python:3.11 \
  bash -c "cd /workspace/package && pip install -r /workspace/requirements.txt -t ."

# Remove unnecessary files to reduce package size
echo "🗑️  Removing unnecessary files..."
cd "$SCRIPT_DIR/package"
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
find . -name "*.pyo" -delete 2>/dev/null || true

# Create the deployment zip
echo "🗜️  Creating deployment package..."
zip -r "../refocused-production-lambda.zip" . -x "*.git*" "*.DS_Store*"

cd "$SCRIPT_DIR"

cd "$SCRIPT_DIR"

# Clean up package directory
rm -rf package

# Show package info
if [ -f "refocused-production-lambda.zip" ]; then
    PACKAGE_SIZE=$(du -h "refocused-production-lambda.zip" | cut -f1)
    echo "✅ Deployment package created successfully!"
    echo "📁 Package: refocused-production-lambda.zip"
    echo "📏 Size: $PACKAGE_SIZE"
    echo ""
    echo "🚀 Ready to deploy to AWS Lambda!"
else
    echo "❌ Failed to create deployment package"
    exit 1
fi