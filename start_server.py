"""
Server startup script with proper environment variable loading.
"""

import os
import sys
import argparse
from dotenv import load_dotenv

def main():
    """Start the server with proper environment loading."""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Start the FastAPI server')
    parser.add_argument('--port', type=int, default=8000, help='Port to run the server on')
    args = parser.parse_args()
    
    # Load environment variables from .env file
    env_loaded = load_dotenv()
    
    # Ensure required environment variables are set
    required_vars = [
        'DATABASE_URL',
        'SECRET_KEY', 
        'GOOGLE_CLIENT_ID',
        'GOOGLE_CLIENT_SECRET'
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        import logging
        logging.error(f"Missing required environment variables: {missing_vars}")
        sys.exit(1)
    
    # Set default values for server
    os.environ.setdefault('DATABASE_URL', 'sqlite+aiosqlite:///./app.db')
    os.environ.setdefault('APP_ENV', 'development')
    os.environ.setdefault('DEBUG', 'true')
    
    # Server info logged by uvicorn
    
    # Start the server
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=args.port,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    main() 