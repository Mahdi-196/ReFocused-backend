#!/usr/bin/env python3
"""
Server startup script with proper environment variable loading.
"""

import os
import sys
from dotenv import load_dotenv

def main():
    """Start the server with proper environment loading."""
    
    # Load environment variables from .env file
    env_loaded = load_dotenv()
    print(f"✅ Environment file loaded: {env_loaded}")
    
    # Ensure required environment variables are set
    required_vars = [
        'DATABASE_URL',
        'SECRET_KEY', 
        'GOOGLE_CLIENT_ID',
        'GOOGLE_CLIENT_SECRET'
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            missing_vars.append(var)
        else:
            # Only show first few chars of sensitive data
            if 'SECRET' in var or 'CLIENT_SECRET' in var:
                display_value = f"{value[:10]}..."
            else:
                display_value = value
            print(f"✅ {var}: {display_value}")
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {missing_vars}")
        print("Please check your .env file or environment setup.")
        sys.exit(1)
    
    # Set default values for server
    os.environ.setdefault('DATABASE_URL', 'sqlite+aiosqlite:///./app.db')
    os.environ.setdefault('APP_ENV', 'development')
    os.environ.setdefault('DEBUG', 'true')
    
    print("🚀 Starting FastAPI server...")
    print("📡 Server will be available at: http://localhost:8000")
    print("📚 API docs at: http://localhost:8000/docs")
    print("🔧 Google OAuth endpoint: http://localhost:8000/api/v1/auth/google")
    
    # Start the server
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    main() 