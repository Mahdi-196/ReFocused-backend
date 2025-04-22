# ReFocused API

A secure backend for the ReFocused productivity application.

## Security Features

This application implements comprehensive security measures:

- **Authentication**: JWT-based with secure password handling
- **Authorization**: Role-based access control
- **Input Validation**: Strong validation and sanitization
- **Security Headers**: HSTS, CSP, and other protective headers
- **Rate Limiting**: Protection against brute force attacks
- **HTTPS Enforcement**: Automatic redirection to secure connections
- **Dependency Scanning**: Regular vulnerability scanning
- **Security Logging**: Centralized security event monitoring

## Security Setup Instructions

### 1. Environment Configuration

Create a `.env` file with secure settings:

```
# Required in production
SECRET_KEY=<generate-a-secure-random-key>
ENVIRONMENT=production
SSL_ENABLED=true
SSL_CERT_FILE=/path/to/cert.pem
SSL_KEY_FILE=/path/to/key.pem

# Database
DATABASE_URL=<secure-database-connection-string>

# CORS
FRONTEND_URL=https://your-frontend-domain.com
BACKEND_URL=https://your-api-domain.com
```

To generate a secure random key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. SSL/TLS Setup

In production, always use HTTPS:

1. Obtain SSL certificates (Let's Encrypt recommended)
2. Configure your reverse proxy (Nginx, etc.) with proper SSL settings
3. Set `SSL_ENABLED=true` in your `.env` file

### 3. Security Scanning

Run regular security scans:

```bash
# Scan code for security issues
bandit -r app/

# Check dependencies for vulnerabilities
safety check -r requirements.txt
```

A GitHub Actions workflow is included that runs these checks automatically.

### 4. Security Best Practices

- Never commit `.env` files or secrets to version control
- Keep dependencies updated regularly
- Review security logs for suspicious activity
- Implement defense in depth - don't rely on a single security control
- Apply the principle of least privilege for all components

## Development Setup

1. Clone the repository
2. Create a virtual environment: `python -m venv venv`
3. Activate the environment: `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows)
4. Install dependencies: `pip install -r requirements.txt`
5. Create a development `.env` file with appropriate settings
6. Run the server: `uvicorn app.main:app --reload`

## API Documentation

When running in development mode, API documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Security Contact

If you discover a security vulnerability, please contact us at [security@example.com](mailto:security@example.com) rather than opening a public issue. 