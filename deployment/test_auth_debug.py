#!/usr/bin/env python3
"""
Debug script to test authentication timeouts locally
"""
import asyncio
import os
import time
import traceback
from fastapi.testclient import TestClient

# Set minimal required environment variables for testing
os.environ.update({
    "SECRET_KEY": "test-secret-key-for-debugging-only",
    "GOOGLE_CLIENT_ID": "test-client-id",
    "GOOGLE_CLIENT_SECRET": "test-client-secret",
    "DATABASE_URL": "sqlite+aiosqlite:///./test.db",  # Use async SQLite for local testing
    "APP_ENV": "development",
    "REDIS_URL": "",  # Disable Redis for testing
    "RATE_LIMIT_ENABLED": "false",  # Disable rate limiting for testing
    "DEBUG": "true"
})

print("🔧 Environment variables set for testing")

# Import the app after setting environment variables
from app.main import app

def test_health_endpoint():
    """Test basic health endpoint"""
    print("\n🏥 Testing health endpoint...")
    try:
        with TestClient(app) as client:
            start_time = time.time()
            response = client.get("/health")
            elapsed = time.time() - start_time

            print(f"⏱️  Health check took {elapsed:.3f}s")
            print(f"📊 Status Code: {response.status_code}")
            print(f"📄 Response: {response.json()}")

            if elapsed > 5.0:
                print(f"⚠️  SLOW: Health check took {elapsed:.3f}s")

            return response.status_code == 200
    except Exception as e:
        print(f"❌ Health endpoint failed: {e}")
        traceback.print_exc()
        return False

def test_auth_endpoints():
    """Test authentication endpoints for timeouts"""
    print("\n🔐 Testing authentication endpoints...")

    with TestClient(app) as client:
        # Test login endpoint with invalid credentials (should be fast)
        print("Testing login endpoint...")
        start_time = time.time()
        try:
            response = client.post("/api/v1/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "wrongpassword"
                },
                headers={"Content-Type": "application/json"}
            )
            elapsed = time.time() - start_time

            print(f"⏱️  Login request took {elapsed:.3f}s")
            print(f"📊 Status Code: {response.status_code}")
            print(f"📄 Response: {response.text[:200]}...")

            if elapsed > 10.0:
                print(f"🐌 TIMEOUT ISSUE: Login took {elapsed:.3f}s")
                return False

        except Exception as e:
            elapsed = time.time() - start_time
            print(f"❌ Login endpoint failed after {elapsed:.3f}s: {e}")
            traceback.print_exc()
            return False

        # Test register endpoint (should also be fast with validation error)
        print("\nTesting register endpoint...")
        start_time = time.time()
        try:
            response = client.post("/api/v1/auth/register",
                json={
                    "email": "test@example.com",
                    "password": "short",  # Too short, should fail validation quickly
                    "name": "Test User"
                },
                headers={"Content-Type": "application/json"}
            )
            elapsed = time.time() - start_time

            print(f"⏱️  Register request took {elapsed:.3f}s")
            print(f"📊 Status Code: {response.status_code}")
            print(f"📄 Response: {response.text[:200]}...")

            if elapsed > 10.0:
                print(f"🐌 TIMEOUT ISSUE: Register took {elapsed:.3f}s")
                return False

        except Exception as e:
            elapsed = time.time() - start_time
            print(f"❌ Register endpoint failed after {elapsed:.3f}s: {e}")
            traceback.print_exc()
            return False

    return True

def test_middleware_timing():
    """Test middleware execution timing"""
    print("\n⚙️  Testing middleware timing...")

    with TestClient(app) as client:
        # Test a simple endpoint to see middleware overhead
        endpoints_to_test = [
            "/",
            "/health",
            "/api/v1/auth/login"  # This should hit middleware
        ]

        for endpoint in endpoints_to_test:
            print(f"Testing {endpoint}...")
            start_time = time.time()
            try:
                if endpoint == "/api/v1/auth/login":
                    response = client.post(endpoint,
                        json={"email": "test@example.com", "password": "test"},
                        headers={"Content-Type": "application/json"}
                    )
                else:
                    response = client.get(endpoint)

                elapsed = time.time() - start_time
                print(f"  ⏱️  {endpoint} took {elapsed:.3f}s (status: {response.status_code})")

                if elapsed > 5.0:
                    print(f"  🐌 SLOW: {endpoint} took {elapsed:.3f}s")

            except Exception as e:
                elapsed = time.time() - start_time
                print(f"  ❌ {endpoint} failed after {elapsed:.3f}s: {e}")

def main():
    """Run all debug tests"""
    print("🚀 Starting authentication timeout debug tests...")
    print("=" * 60)

    # Test basic functionality first
    health_ok = test_health_endpoint()
    if not health_ok:
        print("❌ Basic health check failed, stopping tests")
        return False

    # Test middleware timing
    test_middleware_timing()

    # Test authentication endpoints
    auth_ok = test_auth_endpoints()

    print("\n" + "=" * 60)
    if auth_ok:
        print("✅ All authentication tests passed - no timeout issues detected locally")
    else:
        print("❌ Authentication timeout issues detected")

    return auth_ok

if __name__ == "__main__":
    main()