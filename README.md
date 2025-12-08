# ReFocused Backend API

**Production API:** [refocused.app](https://refocused.app)

Backend API for the ReFocused productivity platform, built with FastAPI.

---

## What Is ReFocused Backend?

ReFocused Backend is a modern, high-performance FastAPI application powering the ReFocused productivity platform, supporting:
- Secure authentication
- Real-time data synchronization
- AI-powered features
- Robust monitoring and observability

Designed for performance, security, and scalability, it supports JWT authentication, Redis caching, PostgreSQL persistence, and advanced middleware. The architecture targets sub-100ms response times, 99.9% uptime, and seamless OAuth integration.

---

## Why Does This Exist?

To provide the ReFocused frontend with a reliable, scalable, and secure API. The backend demonstrates best practices in async Python backend development:
- Asynchronous database operations
- Production-grade middleware
- Structured logging with OpenTelemetry
- Rate limiting and CSRF protection
- Comprehensive monitoring

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
- **FastAPI 0.104.1:** Modern async web framework
- **Uvicorn 0.24.0:** High-performance ASGI server
- **Python 3.11:** Latest stable Python

### Database Layer
- **PostgreSQL:** Relational database
- **SQLAlchemy 2.0.23:** Async ORM (connection pooling)
- **Alembic 1.12.1:** Database migrations
- **asyncpg 0.29.0:** Async PostgreSQL driver
- **psycopg2-binary 2.9.9:** Adapter

### Caching & Sessions
- **Redis 5.0.1:** Distributed cache/session storage
- **redis.asyncio:** Async client with pooling

### Authentication & Security
- **python-jose:** JWT token handling (HS256/RS256)
- **passlib (bcrypt 1.7.4):** Secure password hashing (12 rounds)
- **cryptography 42.0.5:** Encryption operations
- **google-auth & google-auth-oauthlib:** OAuth 2.0 integration
- **itsdangerous 2.1.2:** Token manipulation

### Data Validation
- **Pydantic 2.5.0:** Data validation & settings
- **pydantic-settings 2.1.0:** Env-based config

### Monitoring & Observability
- **Sentry SDK 1.45.0:** Error tracking
- **OpenTelemetry:** Distributed tracing
- **Prometheus Client 0.19.0:** Metrics and export
- **structlog, python-json-logger:** Structured logging

### Task Scheduling
- **APScheduler 3.10.4:** Background tasks

### Utilities
- **httpx, python-multipart, Jinja2, python-dateutil, pytz, psutil:** HTTP, forms, templates, time, system info

### Testing
- **pytest, pytest-asyncio:** Test and async test support

---

## File Structure

> _The backend contains 132 Python modules, organized as follows:_

- **14 Endpoint Modules:** auth, users, goals, study, journal, statistics, ai, voting, feedback, admin, etc.
- **8 Routers:** habits, mood, streak, dashboard, calendar, time, monitoring, users
- **13 Core Modules:** config, auth, enhanced_auth, security, middleware, scheduler
- **12 Services:** google_oauth, ai_service, email_service, feedback_service, voting_service, journal_service, time_service, daily_streak_service, productivity_service, export_service, activity_logger
- **Plus layers for:** caching, monitoring, database, schemas, CRUD, utilities

---

## Architecture Overview

### Middleware Stack (Order)
1. **CORSMiddleware:** CORS handling w/ credentials
2. **SessionMiddleware:** Secure cookies
3. **SessionAuthenticationMiddleware:** JWT and cookie validation
4. **ProductionMiddleware:** Security headers, request IDs, rate limiting (token bucket), CSRF, monitoring, attack detection
5. **GZipMiddleware:** Compresses large responses

### Request/Response Flow
Client requests traverse CORS validation, session extraction, JWT validation, rate limiting (500/min/IP), CSRF token checks (for state changes), routing, endpoint execution, database querying (with pooling), Redis cache checks/updates, serialization, security headers, GZip compression, and response delivery.

### Database Connection Pooling
- Pool: 20 connections (+10 overflow)
- Timeout: 5s
- Recycling: 30min
- Engine: asyncpg

---

## Authentication & Security

### Multi-Layer Authentication
- **HTTP-Only Cookies:** Secure, SameSite=None, 30-day duration, auto refresh, multiple devices supported
- **JWT Bearer Tokens:** HS256 by default, RS256 w/ JWKS optional. Access: 30min; Refresh: 7–30days ("remember me").
- **Token Blacklist:** Immediate revocation on logout; persisted with TTL.

### OAuth 2.0
- **Google OAuth (PKCE):** Account linking, profile sync, hybrid authentication with optional password.

### Token Management
- **Auto Refresh:** Silently refreshes tokens via `/api/v1/auth/refresh` within 5 min of expiration.
- **Blacklisting:** Immediate invalidation via database-backed blacklist.

### Password Security
- **Hashing:** bcrypt, 12 rounds (~400ms)
- **Password History:** last 5 passwords prevented
- **Policy:** Min 8 chars, complexity required
- **Login Rate Limit:** Lockout after 5 failed attempts (30min)
- **Audit:** Each login attempt logged with IP

### Security Features
- **CSRF:** Double-submit cookie, X-CSRF-Token header
- **Rate Limiting:** 500/min/IP (global); endpoint limits e.g. login (5/15min), AI (50/day), email (10/day)
- **Headers:** CSP, X-Frame-Options:DENY, X-Content-Type-Options:nosniff, HSTS, X-XSS-Protection
- **Attack Detection:** SQLi, XSS, path traversal detection; suspicious requests logged to Sentry

### Session Management
- **Default:** 8h duration; auto refresh
- **Remember Me:** 30d duration
- **Invalidation:** Password change or logout

---

## API Endpoints

### Authentication (`/api/v1/auth`)
- `POST /login` – Email/password authentication
- `POST /register` – Registration
- `POST /google` – Google OAuth
- `POST /refresh` – Refresh tokens
- `POST /logout` – Blacklist & terminate session
- `POST /reset-password` – Reset

### User (`/api/v1/user`)
- `GET /me` – User profile
- `PUT /me` – Update
- `DELETE /me` – Delete
- `GET /statistics` – Usage statistics
- `POST /timezone` – Set timezone
- `POST /mock-date` – Developer mock datetime

### Goals (`/api/v1/goals`)
- List/create/get/update/delete progress
- Types: percentage/counter/checklist
- Completion endpoints

### Study (`/api/v1/study/sets`)
- List/create/get/update/delete sets
- Flashcard CRUD

### Journal (`/api/v1/journal`)
- Collections and entries CRUD
- Lock/unlock entries with password

### Habits (`/api/v1/habits`)
- List/create/update/delete habits
- Complete for today
- Calendar and statistics endpoints

### Mood (`/api/v1/mood`)
- Entry CRUD
- Analytics/stats/calendar

### Streaks (`/api/v1/streak`)
- Current/ping/history

### Dashboard, Statistics, AI, Voting, Feedback, Email, Time, Calendar, Monitoring
- See full endpoint list above

> **Total:** 140+ endpoints across 14 modules, 8 routers  
> **Docs:** [Swagger UI](/docs), [ReDoc](/redoc)

---

## Database Architecture

### SQLAlchemy Models (25+ Tables)
#### Core Models
- **User:** OAuth, email, passwords, streaks, security, mock date
- **Goal2Week/GoalLongTerm:** Percentage/counter/checklist, progress tracking
- **Habit:** Tracking, completion, stats
- **StudySet:** Flashcards, study sessions
- **JournalCollection/Entry:** Rich text, optional password protection
- **MoodEntry:** Daily logs
- **QuickAccess/Gratitude:** Notes and entries
- **UserStatistics/PomodoroSettings:** Productivity, settings

#### Auth & Security Models
- **TokenBlacklist, PasswordHistory, LoginAttempt, SecurityLog**

#### Relationships/Cascade Deletion
- **Cascade="all, delete-orphan"** for all user data

#### Indexes & Constraints
- **Daily unique constraints, foreign keys, check constraints, UTC timestamps**

#### Migration Strategy
- **Alembic migrations**
- **Automatic schema creation**
- **Rollback support**

---

## Caching Strategy

### Redis Architecture
- **Async client** (20 connections, health checks every 30s, 5s timeout, SSL/TLS/rediss:// supported)
- **TCP keepalive** for stability

#### Invalidation
- **TTL expiration**
- **Manual invalidation on updates**
- **Midnight UTC reset for date-scoped data**

#### Fallback
- **In-memory fallback** if Redis down

#### Patterns
- **Daily Cache:** Quotes/words (`daily:{date}:{type}`)
- **User Sessions:** (`session:{user_id}:{session_id}`)
- **Rate Limiting:** (`ratelimit:{ip}:{endpoint}`)
- **AI Chat Counter:** (`ai:daily:{user_id}:{date}`)
- **Query Results:** 5min TTL

#### Metrics
- **Prometheus:** hit/miss counters, latency histogram, cache size

---

## Monitoring & Observability

### Structured Logging
- **JSON logs** for parsing
- **Correlation IDs** (`X-Correlation-ID`)
- **Log levels:** DEBUG, INFO, WARNING, ERROR, CRITICAL
- **File logging:** `/var/log/refocused/app.log`
- **User/Environment tagging**

### Prometheus Metrics
- **HTTP:** request counts, latency, payload sizes
- **Database:** connections, query duration, pool metrics
- **Cache:** hit ratios, operation latency
- **Application:** health, active users, background jobs
- **Custom:** DAU, feature usage, error rates

### Error Tracking (Sentry)
- **Error capture/grouping**
- **Transaction/performance tracing**
- **Release/environment tagging**

### OpenTelemetry
- **Distributed tracing**, spans for DB queries
- **OTLP exporter**
- **Service name:** "ReFocused API"

### Performance Monitoring
- **Slow query logs (>100ms)**
- **Memory/CPU tracking**

---

## Deployment

### Docker
- **Multi-stage build:** Builder (Python 3.11, dependencies, build tools), Production (slim, non-root, runtime deps)
- **Image optimization:** Layer caching, `.dockerignore`, multi-platform support

### Performance Benchmarks
- **Response time:** <50ms
- **DB query time:** <20ms avg
- **Auth time (bcrypt):** <100ms
- **Token refresh:** <30ms

### Security Compliance
- **OWASP Top 10**
- **GDPR:** Data export and deletion
- **Secure cookies, input validation, rate limiting, CSRF**
- **Regular dependency CVE scans**

### AWS Deployment
- (Architecture docs forthcoming)


