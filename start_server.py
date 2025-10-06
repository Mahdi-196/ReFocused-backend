"""
Server startup script with proper environment variable loading and safe fallbacks.
"""

import os
import sys
import argparse
import logging
import secrets
from dotenv import load_dotenv

def main():
    """Start the server with proper environment loading."""

    # Logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Start the FastAPI server')
    parser.add_argument('--port', type=int, default=8000, help='Port to run the server on')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--prod', action='store_true', help='Run production app (app.main_production:app)')
    parser.add_argument('--disable-db-startup', action='store_true', help='Disable DB startup tasks (sets DISABLE_DB_STARTUP=1)')
    args = parser.parse_args()

    # Load environment variables from .env file
    load_dotenv()

    # Defaults for development convenience
    os.environ.setdefault('APP_ENV', 'development')
    os.environ.setdefault('DEBUG', 'true')

    is_production = os.environ.get('APP_ENV', 'development').lower() == 'production'

    # Provide safe defaults in non-production
    if not os.getenv('SECRET_KEY'):
        if is_production:
            logging.error("Missing required environment variable: SECRET_KEY")
            sys.exit(1)
        os.environ['SECRET_KEY'] = f"dev-{secrets.token_hex(16)}"

    if not os.getenv('GOOGLE_CLIENT_ID'):
        if is_production:
            logging.error("Missing required environment variable: GOOGLE_CLIENT_ID")
            sys.exit(1)
        os.environ['GOOGLE_CLIENT_ID'] = 'dummy'

    if not os.getenv('GOOGLE_CLIENT_SECRET'):
        if is_production:
            logging.error("Missing required environment variable: GOOGLE_CLIENT_SECRET")
            sys.exit(1)
        os.environ['GOOGLE_CLIENT_SECRET'] = 'dummy'

    # DATABASE_URL default (used only if app attempts DB access)
    # Note: dev app may attempt DB connection; if that fails, we fallback to production app with DB startup disabled
    os.environ.setdefault('DATABASE_URL', 'sqlite+aiosqlite:///./app.db')

    # Optionally disable DB startup tasks
    if args.disable_db_startup:
        os.environ['DISABLE_DB_STARTUP'] = '1'

    # Choose app import path
    app_import = "app.main_production:app" if args.prod else "app.main:app"

    # Start the server
    import uvicorn
    try:
        uvicorn.run(
            app_import,
            host=args.host,
            port=args.port,
            reload=not args.prod,  # no reload in production mode
            log_level="info"
        )
    except Exception as exc:
        # Fallback to production app without DB startup (useful when dev DB is not available)
        if not args.prod:
            logging.warning(f"Dev app failed to start ({exc}); falling back to production app without DB startup.")
            os.environ['DISABLE_DB_STARTUP'] = '1'
            uvicorn.run(
                "app.main_production:app",
                host=args.host,
                port=args.port,
                reload=False,
                log_level="info"
            )
        else:
            raise

if __name__ == "__main__":
    main() 