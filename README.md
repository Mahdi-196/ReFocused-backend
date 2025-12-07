# ReFocused Backend API

Backend API for the ReFocused productivity platform, built with FastAPI.

## Tech Stack

- **FastAPI**
- **PostgreSQL** (AsyncPG + SQLAlchemy)
- **Redis** (Caching & Rate Limiting)
- **Prometheus** (Metrics)

## Setup

1. Copy `.env.example` to `.env` and configure:
   ```bash
   cp .env.example .env
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run migrations:
   ```bash
   alembic upgrade head
   ```

4. Start server:
   ```bash
   uvicorn app.main_production:app --reload
   ```

## API Documentation

- Swagger UI: `/docs`
- ReDoc: `/redoc`

## Project Structure

- `app/api`: API endpoints
- `app/core`: Core config and middleware
- `app/db`: Database models and migrations
- `app/services`: Business logic
- `tests/`: Test suite
