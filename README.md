# ReFocused Backend API

**Production API:** [refocused.app](https://refocused.app)

---

## What This Is

ReFocused Backend is a FastAPI application for the ReFocused productivity platform. It provides secure authentication, real-time data synchronization, AI powered features, and monitoring. Built with performance, security, and scalability in mind, it handles everything from JWT authentication to Redis caching to PostgreSQL data persistence.

---

## Why This Exists

This backend was built to support ReFocused's  frontend with a reliable, scalable, and secure API. It demonstrates modern Python backend development practices including asynchronous database operations, production ready middleware stacks, structured logging with OpenTelemetry, rate limiting, CSRF protection, and comprehensive monitoring. The architecture evolved through multiple iterations to achieve sub-100ms response times, 99.9% uptime, and seamless OAuth integration.

---

## Table of Contents

1. [Tech Stack](#tech-stack)
2. [Architecture Overview](#architecture-overview)
3. [Authentication & Security](#authentication--security)
4. [API Endpoints](#api-endpoints)
5. [Database Architecture](#database-architecture)
6. [Caching Strategy](#caching-strategy)
7. [Monitoring & Observability](#monitoring--observability)
8. [Deployment](#deployment)

---

## Tech Stack

### Core Framework
**FastAPI 0.104.1** Modern async web framework
**Uvicorn 0.24.0** ASGI server with production performance
**Python 3.11** Latest stable Python with performance improvements

### Database Layer
**PostgreSQL** Primary relational database
**SQLAlchemy 2.0.23** Async ORM with connection pooling
**Alembic 1.12.1** Database migrations
**asyncpg 0.29.0** High-performance async PostgreSQL driver
**psycopg2-binary 2.9.9** PostgreSQL adapter

### Caching & Session Management
**Redis 5.0.1** Distributed caching and session storage
**redis.asyncio** Async Redis client with connection pooling

### Authentication & Security
**python-jose[cryptography] 3.3.0** JWT token handling (HS256/RS256)
**passlib[bcrypt] 1.7.4** Password hashing with bcrypt (12 rounds)
**cryptography 42.0.5** Cryptographic operations
**google-auth 2.23.4** Google OAuth 2.0 integration
**google-auth-oauthlib 1.1.0** OAuth 2.0 flows
**itsdangerous 2.1.2** Secure token generation

### Data Validation
**Pydantic 2.5.0** Data validation and settings management
**pydantic-settings 2.1.0** Environment-based configuration

### Monitoring & Observability
**Sentry SDK 1.45.0** Error tracking and performance monitoring
**OpenTelemetry API 1.25.0** Distributed tracing
**OpenTelemetry SDK 1.25.0** Telemetry data collection
**OpenTelemetry FastAPI 0.46b0** FastAPI auto-instrumentation
**Prometheus Client 0.19.0** Metrics collection and export
**structlog 23.2.0** Structured logging
**python-json-logger 2.0.7** JSON log formatting

### Task Scheduling
**APScheduler 3.10.4** Background job scheduling

### Utilities
**httpx 0.25.2** Async HTTP client
**python-multipart 0.0.6** Form data parsing
**Jinja2 3.1.2** Template rendering
**python-dateutil 2.8.2** Date/time manipulation
**pytz 2023.3** Timezone support
**psutil 5.9.8** System resource monitoring

### Testing
**pytest 7.4.4** Testing framework
**pytest-asyncio 0.23.5** Async test support

### File Structure

The backend has 132 Python modules organized into:
- 14 API endpoint modules (auth, users, goals, study, journal, statistics, ai, voting, feedback, admin, and more)
- 8 router modules (habits, mood, streak, dashboard, calendar, time, monitoring, users)
- 13 core infrastructure modules (config, auth, enhanced_auth, security, middleware, scheduler)
- 12 service modules (google_oauth, ai_service, email_service, feedback_service, voting_service, journal_service, time_service, daily_streak_service, productivity_service, export_service, activity_logger)
- Additional layers for caching, monitoring, database, schemas, CRUD operations, and utilities

**Total:** 132 Python modules across the application

---

## Architecture Overview

### Middleware Stack (Execution Order)

1. **CORSMiddleware** handles cross-origin resource sharing with credential support
2. **SessionMiddleware** manages sessions with secure cookies
3. **SessionAuthenticationMiddleware** validates JWT tokens and cookies
4. **ProductionMiddleware** provides consolidated security and monitoring including request ID generation, response time tracking, security headers (CSP, X-Frame-Options, HSTS), rate limiting via token bucket algorithm, CSRF validation, and attack detection
5. **GZipMiddleware** compresses responses over 1000 bytes

### Request/Response Flow

Client requests flow through CORS validation, session extraction from cookies or headers, JWT validation and user resolution, rate limiting checks (500 requests per minute per IP), CSRF token validation for state-changing operations, router matching, endpoint handler execution, database queries with connection pooling, Redis cache checks and updates, response serialization, security header injection, GZip compression, and finally delivery to the client.

### Database Connection Pooling

The application maintains a pool of 20 database connections with a maximum overflow of 10 additional connections. Connections timeout after 5 seconds for fail-fast behavior and recycle every 1800 seconds (30 minutes). The async engine uses the high-performance asyncpg driver.

---

## Authentication & Security

### Multi-Layer Authentication

**Primary: HTTP-Only Cookies**
The system uses secure, HTTP-only session cookies with SameSite=None for cross-origin requests (requires HTTPS). Cookies expire after 30 days with automatic refresh and domain scoping for security.

**Fallback: JWT Bearer Tokens**
HS256 signing is used by default (configurable to RS256 with JWKS). Access tokens last 30 minutes, refresh tokens last 7 days (30 days with "remember me" enabled). Token blacklist support enables instant revocation on logout.

**OAuth 2.0 Integration**
Google OAuth with PKCE flow provides automatic account linking by email, profile picture synchronization, and hybrid authentication where OAuth users can optionally set passwords.

### Token Management

**Automatic Token Refresh**
Tokens automatically refresh when they expire within 5 minutes, providing silent refresh without user interruption via the /api/v1/auth/refresh endpoint.

**Token Blacklisting**
Immediate token revocation occurs on logout through a database-backed blacklist with TTL, preventing replay attacks.

### Password Security

Passwords use bcrypt hashing with 12 rounds (approximately 400ms hashing time per password). The system tracks password history to prevent reuse of the last 5 passwords. Minimum password length is 8 characters with complexity requirements. After 5 failed login attempts, accounts lock for 30 minutes. All login attempts are logged with IP addresses.

### Security Features

**CSRF Protection**
Double-submit cookie pattern with X-CSRF-Token header validation on all state-changing operations.

**Rate Limiting**
Global limit of 500 requests per minute per IP using a token bucket algorithm (120 capacity, 2 tokens per second refill rate). Endpoint-specific limits include 5 login attempts per 15 minutes, 50 AI chat messages per day per user, and 10 email subscription actions per day per IP.

**Security Headers**
All responses include Content-Security-Policy (CSP), X-Frame-Options set to DENY, X-Content-Type-Options set to nosniff, Strict-Transport-Security (HSTS), and X-XSS-Protection.

**Attack Detection**
The system detects SQL injection patterns, XSS payloads, and path traversal attempts. Suspicious requests are logged to Sentry for alerting.

### Session Management

Default session duration is 8 hours with automatic refresh on activity. "Remember me" sessions last 30 days. Sessions invalidate on password changes and support multiple devices with session tracking.

---

## API Endpoints

### Authentication (`/api/v1/auth`)
POST /login provides email/password authentication. POST /register handles user registration with validation. POST /google enables Google OAuth authentication. POST /refresh refreshes tokens. 
POST /logout terminates sessions and blacklists tokens. POST /reset-password completes password resets.

### User Management (`/api/v1/user`)
GET /me returns current user profile. PUT /me updates profile (name, timezone, avatar). DELETE /me handles account deletion. GET /statistics provides user statistics overview. POST /timezone updates timezone settings. POST /mock-date enables mock date/time for developers.

### Goals (`/api/v1/goals`)
GET / lists all goals with pagination and filtering. POST / creates new goals (percentage/counter/checklist types). GET /{id} retrieves goal details. PUT /{id} updates goal progress. DELETE /{id} deletes goals. POST /{id}/complete marks goals complete. GET /completed lists completed goals with time-to-completion.

### Study System (`/api/v1/study/sets`)
GET / lists all study sets. POST / creates study sets. GET /{id} gets study sets with flashcards. PUT /{id} updates study sets. DELETE /{id} deletes study sets. POST /{id}/cards adds flashcards. PUT /{id}/cards/{card_id} updates flashcards. DELETE /{id}/cards/{card_id} deletes flashcards.

### Journal (`/api/v1/journal`)
GET /collections lists journal collections. POST /collections creates collections. GET /collections/{id} gets collection entries. POST /entries creates journal entries. PUT /entries/{id} updates entries. DELETE /entries/{id} deletes entries. POST /entries/{id}/lock password-protects entries with bcrypt. POST /entries/{id}/unlock unlocks protected entries.

### Habits (`/api/v1/habits`)
GET / lists all habits. POST / creates habits. PUT /{id} updates habits. DELETE /{id} deletes habits. POST /{id}/complete marks habits complete for today. GET /{id}/calendar gets habit completion calendars. GET /statistics provides habit completion statistics.

### Mood Tracking (`/api/v1/mood`)
GET /entries lists mood entries. POST /entries logs mood entries. GET /statistics provides mood trends and analytics. GET /calendar shows mood calendar view.

### Streak Management (`/api/v1/streak`)
GET /current shows current daily interaction streak. POST /ping records daily interactions. GET /history displays streak history.

### Dashboard (`/api/v1/dashboard`)
GET /summary provides dashboard summary (goals, habits, streaks). GET /productivity shows monthly productivity score.

### Statistics (`/api/v1/statistics`)
GET /monthly provides monthly productivity analytics. GET /overview shows comprehensive statistics overview.

### AI Features (`/api/v1/ai`)
POST /chat sends AI messages (50/day limit). GET /conversations lists conversations. DELETE /conversations/{id} deletes conversations.

### Voting System (`/api/v1/voting`)
GET /features lists feature requests. POST /vote votes for features. DELETE /vote/{id} removes votes.

### Feedback (`/api/v1/feedback`)
POST /submit submits user feedback. GET /list lists feedback (admin only).

### Email Subscription (`/api/v1/email`)
POST /refocusedSubscribe subscribes to mailing list. POST /unsubscribe unsubscribes. POST /status checks subscription status.

### Time Synchronization (`/api/v1/time`)
GET /server gets server time (UTC + user timezone). POST /sync synchronizes client time.

### Calendar (`/api/v1/calendar`)
GET /events gets calendar events. POST /events creates events.

### Monitoring
GET /health provides health check endpoint. GET /metrics exports Prometheus metrics. GET / shows API information and version.

**Total Endpoints:** 140+ across 14 endpoint modules + 8 routers

---

## Database Architecture

### SQLAlchemy Models (25+ tables)

**Core Models:**

The User table stores user accounts with OAuth support. Fields include email, hashed_password, google_id, auth_provider, and timezone. Streak tracking fields include current_streak, longest_streak, and last_interaction_date. Security fields include failed_login_attempts, locked_until, and password_history. Mock date support enables testing.

Goal2Week and GoalLongTerm tables handle goal tracking with three types: percentage, counter, and checklist. Progress tracking includes computed percentages and completion timestamps.

Habit table manages daily habit tracking with completion calendars, streak calculations, and statistics integration.

StudySet table contains flashcard collections with nested flashcards and study session tracking.

JournalCollection and JournalEntry tables provide the journal system with rich text content, optional password protection using bcrypt, and collection organization.

MoodEntry table tracks daily mood logs with notes and context.

QuickAccess table stores quick notes that auto-delete at midnight.

Gratitude table holds gratitude entries.

UserStatistics table aggregates monthly productivity scores and activity logs.

PomodoroSettings table configures Pomodoro timer settings.

**Auth & Security Models:**

TokenBlacklist stores revoked JWT tokens. PasswordHistory prevents password reuse. LoginAttempt tracks failed login attempts. SecurityLog records security events.

**Feature Models:**

### Relationships & Cascade Deletion

All user-related data uses cascade="all, delete-orphan" for automatic cleanup on account deletion.

### Indexes & Constraints

Composite unique constraints on user_id + date ensure data integrity for daily entries. Indexed foreign keys enable fast joins. Check constraints validate data. All timestamps are timezone-aware with UTC storage.

### Migration Strategy

Alembic handles migrations for schema versioning. Automatic table creation runs on startup (configurable). Migration rollback support enables safe schema changes.

---

## Caching Strategy

### Redis Architecture

**Connection Configuration:**
Async redis-py client with connection pooling. Maximum 20 connections with health checks every 30 seconds. 5-second socket timeout for fail-fast behavior. SSL/TLS support via rediss:// URL scheme. TCP keepalive on Linux for connection stability.

**Cache Invalidation:**
TTL-based expiration. Manual invalidation on data updates. Daily reset at midnight UTC for date-scoped data.

**Fallback Strategy:**
Graceful degradation when Redis unavailable. In-memory fallback for critical operations. Automatic reconnection attempts.

### Caching Patterns

**Daily Cache** stores daily motivational quotes and words with automatic invalidation at UTC midnight using key pattern daily:{date}:{type}

**User Session Cache** maintains active sessions with 8-hour TTL and auto-refresh on activity using key pattern session:{user_id}:{session_id}

**Rate Limiting** uses token bucket counters per IP with sliding window rate limits using key pattern ratelimit:{ip}:{endpoint}

**AI Chat Limits** tracks daily message counters per user that reset at midnight UTC using key pattern ai:daily:{user_id}:{date}

**Query Result Caching** stores frequently accessed data (goals, habits) with 5-minute TTL and invalidation on mutations

### Metrics Tracking

Cache hit/miss counters via Prometheus. Cache operation latency histograms. Cache size monitoring.

---

## Monitoring & Observability

### Structured Logging

**Configuration:**
JSON log formatting for parsing. Log levels include DEBUG, INFO, WARNING, ERROR, and CRITICAL. Contextual logging with correlation IDs. File logging to /var/log/refocused/app.log.

**Logs:**
Request ID tracking via X-Correlation-ID header. User ID injection. Timestamps with timezone. Environment tagging (production/development).

### Prometheus Metrics

**HTTP Metrics** include http_requests_total (request counter by method/endpoint/status), http_request_duration_seconds (request latency histogram), http_request_size_bytes (request payload size), and http_response_size_bytes (response payload size).

**Database Metrics** include db_connections_active (active database connections), db_query_duration_seconds (query execution time), and db_pool_size (connection pool metrics).

**Cache Metrics** include cache_hits and cache_misses (cache hit ratio) plus cache_operation_duration (cache operation latency).

**Application Metrics** include app_health_status (application health 0/1), active_users (concurrent active users), and background_jobs (background task status).

**Custom Metrics** track daily active users (DAU), feature usage counters, and error rates by endpoint.

### Error Tracking with Sentry

Automatic error capture and grouping. Performance transaction tracing. Release tracking (version 1.0.0). Environment tagging (production/staging). Breadcrumb trail for debugging.

### OpenTelemetry Tracing

Distributed tracing across services. Span generation for database queries. OTLP exporter for trace aggregation. Service name: "ReFocused API".


### Performance Monitoring

Request/response time tracking. Slow query logging (>100ms threshold). Memory usage tracking via psutil. CPU usage monitoring.

---

## Deployment

### Docker Configuration

**Multi-Stage Build:**

Builder Stage compiles dependencies using Python 3.11 on Debian Bullseye. Installs build tools (gcc, libpq-dev) and pre-compiles Python packages.

Production Stage uses Python 3.11-slim for reduced image size. Runs as non-root user (app) for security. Includes only runtime dependencies (libpq5, curl).

**Image Optimization:**
Layer caching for faster rebuilds. .dockerignore for smaller build context. Multi-platform support (linux/amd64).


## Performance Benchmarks

**Average Response Time:** <50ms 
**Database Query Time:** <20ms average
**Authentication Time:** <100ms (bcrypt hashing)
**Token Refresh Time:** <30ms

---

## Security Compliance

OWASP Top 10 protection. GDPR compliance (data export, account deletion). Password storage: bcrypt with 12 rounds. Session management: Secure, HTTP-only cookies. API security: Rate limiting, CSRF protection, input validation. Dependency scanning: Regular updates for CVEs.

