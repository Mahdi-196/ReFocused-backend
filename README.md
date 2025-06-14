# ReFocused API

Backend API for the ReFocused productivity application.

## Features

- User authentication with JWT tokens
- Study sets management
- Security features including rate limiting and audit logs
- PostgreSQL database with async support

## Architecture Improvements

The codebase has been improved with:

1. **Transaction Management**
   - Transaction middleware for automatic transaction handling
   - Context managers for explicit transaction control

2. **Code Organization**
   - Repository pattern for data access
   - Service layer for business logic
   - Dependency injection for better testing

3. **Performance Optimizations**
   - Database connection pooling
   - Query optimization with indexes
   - In-memory caching for frequently accessed data

4. **Error Handling & Logging**
   - Standardized error responses
   - Global exception handler
   - Structured logging with contextual information

5. **Security Improvements**
   - Enhanced input validation
   - Security headers middleware
   - Comprehensive audit logging

## Setup

### Environment Variables

Create a `.env` file in the root directory with:

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/refocused
SECRET_KEY=your-secret-key
APP_ENV=development
DEBUG=true
```

### Running with Docker

The easiest way to run the application is with Docker Compose:

```bash
# Build and start containers
docker-compose up -d

# Run migrations
docker-compose exec app alembic upgrade head
```

### Running Locally

```bash
# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start the server
uvicorn app.main:app --reload
```

## API Documentation

API documentation is available at:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Development

### Running Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "Migration name"

# Apply migrations
alembic upgrade head

# Revert migrations
alembic downgrade -1
```

## Project Structure

```
app/
├── api/                # API endpoints
│   └── v1/
│       └── endpoints/  # API route handlers
├── core/               # Core functionality
│   ├── auth.py         # Authentication
│   ├── config.py       # Configuration
│   ├── security.py     # Security utilities
├── db/                 # Database
│   ├── database.py     # Database connection
│   ├── models.py       # SQLAlchemy models
├── repositories/       # Repository pattern
├── services/           # Business logic
├── schemas/            # Pydantic models
└── utils/              # Utility functions
```

## Study Set API Endpoints

The study set API allows users to manage their flashcards and study sets. All endpoints require authentication via JWT token.

### Endpoints

1. **Get All Study Sets** 
   - `GET /api/v1/study/sets`
   - Returns all study sets belonging to the authenticated user

2. **Get Study Set by ID**
   - `GET /api/v1/study/sets/{study_set_id}`
   - Returns a specific study set by ID if owned by the authenticated user

3. **Create/Update Study Set**
   - `POST /api/v1/study/sets`
   - Creates a new study set or updates an existing one
   - Request body must contain title and flashcards array
   - To update an existing set, include the set ID in the request

4. **Bulk Create/Update Study Sets**
   - `POST /api/v1/study/sets/bulk`
   - Creates or updates multiple study sets in a single request
   - Request body must contain an array of study sets

5. **Delete Study Set**
   - `DELETE /api/v1/study/sets/{study_set_id}`
   - Deletes a study set and all its flashcards
   - Returns 204 No Content on success

### Security Features

- All endpoints are protected by authentication
- Each study set is associated with a specific user
- Users can only access and modify their own study sets
- Rate limiting is applied to prevent abuse
- All actions are logged for security purposes
