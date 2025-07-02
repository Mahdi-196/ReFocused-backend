#!/usr/bin/env python3
"""
Debug Authentication Middleware Behavior

This script tests the middleware path matching logic to understand why some endpoints work and others don't.
"""

import asyncio
import aiohttp
import json
import time

BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/v1"

async def test_middleware_behavior():
    """Test how the middleware handles different paths"""
    
    # First, get a valid token
    async with aiohttp.ClientSession() as session:
        print("🔍 Testing Middleware Path Matching")
        print("=" * 60)
        
        # Step 1: Create user and get token
        print("\n1️⃣ Getting valid token...")
        TEST_USER = {
            "email": f"middleware_test_{int(time.time())}@example.com",
            "password": "TestPassword123!",
            "name": "Middleware Test User"
        }
        
        # Register
        reg_url = f"{API_BASE}/auth/register"
        async with session.post(reg_url, json=TEST_USER) as response:
            reg_data = await response.json()
            if response.status != 201:
                print(f"❌ Registration failed: {reg_data}")
                return
        
        # Login to get fresh token
        login_url = f"{API_BASE}/auth/login"
        login_data = {"email": TEST_USER["email"], "password": TEST_USER["password"]}
        async with session.post(login_url, json=login_data) as response:
            login_response = await response.json()
            if response.status != 200:
                print(f"❌ Login failed: {login_response}")
                return
                
            access_token = login_response.get("access_token")
            print(f"✅ Got token: {access_token[:50]}...")
        
        # Step 2: Test various endpoints with token
        print("\n2️⃣ Testing endpoints with detailed response analysis...")
        
        test_endpoints = [
            # Should work (auth endpoints)
            "/auth/status",
            "/auth/me",
            
            # Should require auth (API endpoints)
            "/user/me",
            "/user/profile", 
            "/goals",
            "/habits",
            
            # Should work without auth (public)
            "/content/quote",
        ]
        
        headers = {"Authorization": f"Bearer {access_token}"}
        
        for endpoint in test_endpoints:
            url = f"{API_BASE}{endpoint}"
            
            try:
                async with session.get(url, headers=headers) as response:
                    try:
                        data = await response.json()
                    except:
                        data = {"error": await response.text()}
                    
                    status_icon = "✅" if 200 <= response.status < 300 else "❌"
                    print(f"\n{status_icon} {endpoint}:")
                    print(f"  Status: {response.status}")
                    print(f"  Headers: {dict(response.headers)}")
                    
                    if response.status >= 400:
                        print(f"  Error: {data}")
                    else:
                        # For successful responses, show key info
                        if isinstance(data, dict):
                            if "authenticated" in data:
                                print(f"  Authenticated: {data['authenticated']}")
                            if "user" in data and data["user"]:
                                print(f"  User ID: {data['user'].get('id', 'N/A')}")
                            if "id" in data:
                                print(f"  User ID: {data['id']}")
                            if "email" in data:
                                print(f"  Email: {data['email']}")
                        print(f"  Response type: {type(data)}")
                        
            except Exception as e:
                print(f"❌ {endpoint}: Exception - {str(e)}")
        
        # Step 3: Test the same endpoints WITHOUT token
        print("\n3️⃣ Testing endpoints WITHOUT token (should mostly fail)...")
        
        for endpoint in test_endpoints:
            if endpoint.startswith("/auth"):
                continue  # Skip auth endpoints in this test
                
            url = f"{API_BASE}{endpoint}"
            
            try:
                async with session.get(url) as response:
                    try:
                        data = await response.json()
                    except:
                        data = {"error": await response.text()}
                    
                    expected_fail = endpoint not in ["/content/quote"]
                    status_icon = "✅" if (expected_fail and response.status == 401) or (not expected_fail and response.status == 200) else "❌"
                    
                    print(f"{status_icon} {endpoint} (no auth): {response.status}")
                    if response.status >= 400:
                        print(f"  Error: {data.get('detail', data)}")
                        
            except Exception as e:
                print(f"❌ {endpoint}: Exception - {str(e)}")
        
        # Step 4: Test path pattern matching manually
        print("\n4️⃣ Testing path pattern logic...")
        import re
        
        api_path_pattern = re.compile(r"^/api/v1/(?!auth)")
        
        test_paths = [
            "/api/v1/auth/login",
            "/api/v1/auth/status", 
            "/api/v1/user/me",
            "/api/v1/goals",
            "/api/v1/content/quote",
            "/health",
            "/docs"
        ]
        
        for path in test_paths:
            is_api = bool(api_path_pattern.match(path))
            is_auth = path.startswith("/api/v1/auth/")
            print(f"  {path}: API={is_api}, Auth={is_auth}")

if __name__ == "__main__":
    asyncio.run(test_middleware_behavior()) 