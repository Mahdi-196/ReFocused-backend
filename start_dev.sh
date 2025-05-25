#!/bin/bash

# ReFocused Backend Development Startup Script

echo "🚀 Starting ReFocused Backend Development Environment"
echo "=================================================="

# Set environment variables
export DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/refocused-local-testing"
export GOOGLE_CLIENT_ID="477145264379-8d6fn373vdbt4e4uibmkr7sdaoik7406.apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="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"
export SECRET_KEY="dev-secret-key-change-in-production"
export APP_ENV="development"
export DEBUG="true"

echo "✅ Environment variables set"

# Check if PostgreSQL is running
if ! pg_isready -U postgres -h localhost -p 5432 > /dev/null 2>&1; then
    echo "❌ PostgreSQL is not running. Please start PostgreSQL first."
    echo "   You can use: brew services start postgresql"
    echo "   Or use Docker: docker-compose up postgres -d"
    exit 1
fi

echo "✅ PostgreSQL is running"

# Check if database exists
if ! psql -U postgres -lqt | cut -d \| -f 1 | grep -qw "refocused-local-testing"; then
    echo "📦 Creating database..."
    psql -U postgres -c "CREATE DATABASE \"refocused-local-testing\";" || {
        echo "❌ Failed to create database"
        exit 1
    }
fi

echo "✅ Database exists"

# Run migrations
echo "🔄 Running database migrations..."
alembic upgrade head || {
    echo "❌ Failed to run migrations"
    exit 1
}

echo "✅ Migrations completed"

# Start the server
echo "🌟 Starting FastAPI server..."
echo "   Server will be available at: http://localhost:8000"
echo "   API Documentation: http://localhost:8000/docs"
echo "   Health Check: http://localhost:8000/health"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload 