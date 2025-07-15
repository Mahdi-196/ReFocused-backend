# ReFocused Backend - Time Management & Mock Time API

A comprehensive guide to the time management endpoints in the ReFocused backend API, including timezone handling, current time retrieval, and mock time functionality for testing.

## 🕐 Time Management Endpoints

### Base URL
```
http://localhost:8000/api/v1/time
```

### Authentication
All endpoints require JWT authentication via Bearer token:
```
Authorization: Bearer <your-jwt-token>
```

## 📅 Current Time Endpoints

### GET `/time/current`
**Get current time in user's timezone with enhanced information**

**Description:**
Returns detailed time information including current date/time, week number, day of week, quarter, and mock date status. All times respect mock datetime settings when enabled for testing.

**Response:**
```json
{
  "current_date": "2024-01-15",
  "current_time": "2024-01-15T10:30:00-05:00",
  "timezone": "America/New_York",
  "week_number": 3,
  "day_of_week": "Monday",
  "quarter": 1,
  "mock_date_enabled": false,
  "mock_datetime": null,
  "is_mock_time": false
}
```

**Response Fields:**
- `current_date`: Current date in YYYY-MM-DD format
- `current_time`: ISO 8601 formatted datetime with timezone
- `timezone`: User's configured timezone
- `week_number`: ISO week number (1-53)
- `day_of_week`: Full day name (Monday-Sunday)
- `quarter`: Quarter of the year (1-4)
- `mock_date_enabled`: Whether mock time is active
- `mock_datetime`: Mock datetime if enabled (ISO format)
- `is_mock_time`: Boolean indicating if current time is mocked

**Example Usage:**
```bash
curl -X GET "http://localhost:8000/api/v1/time/current" \
  -H "Authorization: Bearer your-jwt-token"
```

## 🌍 Timezone Management

### PUT `/time/timezone`
**Update user's timezone setting**

**Request Body:**
```json
{
  "timezone": "America/New_York"
}
```

**Response:**
```json
{
  "message": "Timezone updated successfully",
  "timezone": "America/New_York",
  "current_date": "2024-01-15",
  "current_time": "2024-01-15T10:30:00-05:00"
}
```

**Supported Timezone Formats:**
- IANA timezone identifiers (recommended): `America/New_York`, `Europe/London`
- UTC: `UTC`
- GMT: `GMT`

**Example Usage:**
```bash
curl -X PUT "http://localhost:8000/api/v1/time/timezone" \
  -H "Authorization: Bearer your-jwt-token" \
  -H "Content-Type: application/json" \
  -d '{"timezone": "America/New_York"}'
```

### GET `/time/timezones`
**Get list of available timezones organized by region**

**Response:**
```json
{
  "timezones": {
    "America": [
      "America/New_York",
      "America/Chicago",
      "America/Denver",
      "America/Los_Angeles",
      "America/Toronto",
      "America/Vancouver",
      "America/Mexico_City",
      "America/Sao_Paulo",
      "America/Argentina/Buenos_Aires"
    ],
    "Europe": [
      "Europe/London",
      "Europe/Paris",
      "Europe/Berlin",
      "Europe/Rome",
      "Europe/Madrid",
      "Europe/Amsterdam",
      "Europe/Stockholm",
      "Europe/Moscow"
    ],
    "Asia": [
      "Asia/Tokyo",
      "Asia/Shanghai",
      "Asia/Hong_Kong",
      "Asia/Singapore",
      "Asia/Dubai",
      "Asia/Kolkata",
      "Asia/Seoul",
      "Asia/Jakarta"
    ],
    "Pacific": [
      "Pacific/Auckland",
      "Pacific/Sydney",
      "Pacific/Melbourne",
      "Pacific/Fiji",
      "Pacific/Honolulu"
    ],
    "Africa": [
      "Africa/Cairo",
      "Africa/Lagos",
      "Africa/Johannesburg",
      "Africa/Casablanca"
    ]
  }
}
```

**Example Usage:**
```bash
curl -X GET "http://localhost:8000/api/v1/time/timezones" \
  -H "Authorization: Bearer your-jwt-token"
```

## 🧪 Mock Time Endpoints (Debug/Admin Only)

### POST `/time/debug/set-date`
**Set mock datetime for testing purposes**

**Security Notice:**
- Only available to users with admin/superuser privileges
- Disabled in production environments
- All usage is logged for security auditing

**Description:**
Enables "Time Travel" functionality for comprehensive testing of time-dependent features. When a mock datetime is set, all time-related operations for the user will be based on this mock time instead of the real system time.

**Request Body:**
```json
{
  "new_datetime": "2024-01-15T10:30:00Z"
}
```

**Supported DateTime Formats:**
- ISO 8601 with timezone: `2024-01-15T10:30:00Z`
- ISO 8601 with offset: `2024-01-15T10:30:00-05:00`
- ISO 8601 without timezone: `2024-01-15T10:30:00` (assumes UTC)

**Response:**
```json
{
  "message": "Mock datetime set successfully",
  "mock_datetime": "2024-01-15T10:30:00Z",
  "user_datetime": "2024-01-15T05:30:00-05:00",
  "timezone": "America/New_York",
  "mock_date_enabled": true,
  "admin_user": "admin@example.com"
}
```

**Example Usage:**
```bash
curl -X POST "http://localhost:8000/api/v1/time/debug/set-date" \
  -H "Authorization: Bearer admin-jwt-token" \
  -H "Content-Type: application/json" \
  -d '{"new_datetime": "2024-01-15T10:30:00Z"}'
```

### POST `/time/debug/reset-date`
**Reset mock datetime back to real system time**

**Security Notice:**
- Only available to users with admin/superuser privileges
- Disabled in production environments
- All usage is logged for security auditing

**Description:**
After calling this endpoint, all time-related operations will use the real system time.

**Response:**
```json
{
  "message": "Mock datetime reset successfully",
  "real_datetime": "2024-01-15T15:45:30Z",
  "user_datetime": "2024-01-15T10:45:30-05:00",
  "timezone": "America/New_York",
  "mock_date_enabled": false,
  "admin_user": "admin@example.com"
}
```

**Example Usage:**
```bash
curl -X POST "http://localhost:8000/api/v1/time/debug/reset-date" \
  -H "Authorization: Bearer admin-jwt-token"
```

## 🔍 Utility Endpoints

### GET `/time/validate-date/{date_str}`
**Validate if a date string is in the correct YYYY-MM-DD format**

**Path Parameter:**
- `date_str`: Date string to validate

**Response (Valid Date):**
```json
{
  "valid": true,
  "date": "2024-01-15",
  "message": "Date format is valid"
}
```

**Response (Invalid Date):**
```json
{
  "valid": false,
  "date": "invalid-date",
  "message": "Invalid date format. Expected YYYY-MM-DD"
}
```

**Example Usage:**
```bash
curl -X GET "http://localhost:8000/api/v1/time/validate-date/2024-01-15" \
  -H "Authorization: Bearer your-jwt-token"
```

## 🔧 How Time Management Works

### Timezone Handling
1. **User Timezone Storage**: Each user has a `timezone` field in the database
2. **Automatic Updates**: User timezone is updated when provided in requests
3. **Fallback to UTC**: If no timezone is provided, UTC is used as default
4. **Validation**: Timezone strings are validated against IANA timezone database

### Mock Time System
1. **Admin-Only Access**: Mock time endpoints require admin/superuser privileges
2. **Database Storage**: Mock datetime is stored in user's `mock_datetime_override` field
3. **Flag Control**: `mock_date_enabled` boolean controls whether mock time is active
4. **Automatic Conversion**: All time operations respect mock time when enabled
5. **Security Logging**: All mock time operations are logged for audit purposes

### Time Service Integration
The time management system integrates with other parts of the application:

- **Habit Streaks**: Automatic reset based on user's local day
- **Goal Expiration**: 2-week goals expire based on user's timezone
- **Mood Tracking**: Daily mood entries use user's local date
- **Statistics**: Focus time and task tracking use user's local time

## 🚨 Error Handling

### Common Error Responses

**401 Unauthorized:**
```json
{
  "detail": "Not authenticated"
}
```

**403 Forbidden (Admin Endpoints):**
```json
{
  "detail": "Admin privileges required. This endpoint is only available to superusers."
}
```

**404 Not Found (Production):**
```json
{
  "detail": "Debug endpoints are not available in production environment"
}
```

**400 Bad Request (Invalid Timezone):**
```json
{
  "detail": "Invalid timezone"
}
```

**422 Unprocessable Entity (Invalid Date):**
```json
{
  "detail": "Invalid date format. Expected YYYY-MM-DD"
}
```

## 🔒 Security Considerations

### Mock Time Security
- **Admin-Only Access**: Mock time endpoints require superuser privileges
- **Production Disabled**: Mock time is completely disabled in production
- **Audit Logging**: All mock time operations are logged with user details
- **Session Isolation**: Mock time only affects the specific user's session

### Timezone Security
- **Input Validation**: All timezone strings are validated
- **Fallback Handling**: Invalid timezones default to UTC
- **User Isolation**: Each user's timezone is independent

## 📊 Database Schema

### User Model Time Fields
```sql
-- Time-related fields in User table
timezone VARCHAR(50) DEFAULT 'UTC'
mock_date_enabled BOOLEAN DEFAULT FALSE
mock_datetime_override TIMESTAMP WITH TIME ZONE
```

### Security Log Model
```sql
-- Security logging for mock time operations
CREATE TABLE security_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    event_type VARCHAR(100),
    ip_address VARCHAR(45),
    details TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

## 🧪 Testing with Mock Time

### Testing Workflow
1. **Set Mock Time**: Use `/time/debug/set-date` to set a specific datetime
2. **Test Features**: All time-dependent features will use the mock time
3. **Verify Behavior**: Check that habits, goals, and other features work correctly
4. **Reset Time**: Use `/time/debug/reset-date` to return to real time

### Example Testing Scenarios
```bash
# Test habit streak reset at midnight
curl -X POST "/time/debug/set-date" \
  -d '{"new_datetime": "2024-01-15T23:59:59Z"}'

# Test goal expiration
curl -X POST "/time/debug/set-date" \
  -d '{"new_datetime": "2024-01-16T00:00:00Z"}'

# Test timezone changes
curl -X PUT "/time/timezone" \
  -d '{"timezone": "Asia/Tokyo"}'
```

## 🔧 Environment Configuration

### Required Environment Variables
```bash
# Timezone handling
DEFAULT_TIMEZONE=UTC

# Security settings
SECURITY_LOG_LEVEL=INFO
SECURITY_LOG_PATH=logs/security.log

# Admin settings
ADMIN_EMAIL=admin@example.com
SUPERUSER_EMAILS=admin@example.com,superuser@example.com
```

### Development vs Production
- **Development**: Mock time endpoints are available for testing
- **Production**: Mock time endpoints return 404 Not Found
- **Logging**: All mock time operations are logged in both environments

## 📈 Monitoring and Logging

### Security Event Types
- `debug_mock_datetime_set`: When mock datetime is set
- `debug_mock_datetime_reset`: When mock datetime is reset
- `unauthorized_debug_access`: When non-admin tries to access debug endpoints

### Log Format
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "event_type": "debug_mock_datetime_set",
  "user_id": 1,
  "user_email": "admin@example.com",
  "ip_address": "192.168.1.100",
  "details": "Admin user set mock datetime to 2024-01-15T10:30:00Z"
}
```

---

**ReFocused Time Management API** - Comprehensive timezone handling and testing capabilities for productivity applications. 