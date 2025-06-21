#!/usr/bin/env python3
"""
Fast development server startup script
Disables heavy middleware for better performance during development
"""

import os
import uvicorn

# Set development environment variables
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("SECRET_KEY", "dev-secret-key-32-characters-long-minimum")
os.environ.setdefault("MOCK_DATE_ENABLED", "true")
os.environ.setdefault("MOCK_DATE", "2025-06-23")
os.environ.setdefault("RATE_LIMIT_ENABLED", "true")
os.environ.setdefault("RATE_LIMIT_MAX_REQUESTS", "15000")

if __name__ == "__main__":
    print("🚀 Starting ReFocused Backend in FAST development mode")
    print("📊 Statistics endpoints use MINUTES (not seconds)")
    print("🔧 Security monitoring DISABLED for performance")
    print("🌐 CORS enabled for http://localhost:3000")
    print("📅 Mock date ENABLED: 2025-06-23 (for frontend testing)")
    print("🚦 Rate limit: 15000 requests/minute (high for development)")
    print("⚡ Ready for frontend connection!")
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["app"],
        log_level="info"
    ) 