# ReFocused Backend

A FastAPI-based backend for the ReFocused productivity application.

## Features

- User Authentication with JWT
- Goal Management
- Habit Tracking
- Mood Tracking
- Pomodoro Timer Settings
- Study Sets & Flashcards
- Journal Collections
- Security Logging & Monitoring

## Tech Stack

- FastAPI
- SQLAlchemy (Async)
- PostgreSQL
- JWT Authentication
- Rate Limiting
- Security Logging

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the root directory:
```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/refocus_db
SECRET_KEY=your-secret-key
ENVIRONMENT=development
```

4. Initialize the database:
```bash
python -m app.db.init_db
```

5. Run the application:
```bash
uvicorn app.main:app --reload
```

## API Documentation

Once the application is running, you can access:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Security Features

- JWT Authentication
- Password Hashing
- Rate Limiting
- Token Blacklisting
- Security Event Logging
- Account Lockout Protection
- CORS Protection
- Security Headers

## Development

- Use `alembic` for database migrations
- Follow PEP 8 style guide
- Write tests for new features
- Update documentation as needed

## License

MIT 