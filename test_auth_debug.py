#!/usr/bin/env python3
"""
Debug Authentication Issues

This script focuses on debugging the token validation issues found in the comprehensive test.
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/v1"

TEST_USER = {
    "email": f"debug_{int(time.time())}@example.com",
    "password": "TestPassword123!",
    "name": "Debug User"
}

async def debug_auth():
    async with aiohttp.ClientSession() as session:
        print("🔍 Debugging Authentication Issues")
        print("=" * 60)
        
        # Step 1: Test registration and examine response
        print("\n1️⃣ Testing Registration...")
        reg_url = f"{API_BASE}/auth/register"
        async with session.post(reg_url, json=TEST_USER) as response:
            reg_data = await response.json()
            print(f"Status: {response.status}")
            print(f"Response keys: {list(reg_data.keys())}")
            print(f"Full response: {json.dumps(reg_data, indent=2)}")
            
            if response.status != 201:
                print(f"❌ Registration failed: {reg_data}")
                return
        
        # Extract tokens
        access_token = reg_data.get("access_token")
        refresh_token = reg_data.get("refresh_token")
        
        print(f"\n📝 Token Details:")
        print(f"Access token length: {len(access_token) if access_token else 0}")
        print(f"Refresh token length: {len(refresh_token) if refresh_token else 0}")
        print(f"Access token starts with: {access_token[:50] if access_token else 'None'}...")
        
        # Step 2: Test login separately to compare tokens
        print("\n2️⃣ Testing Login...")
        login_url = f"{API_BASE}/auth/login"
        login_data = {"email": TEST_USER["email"], "password": TEST_USER["password"]}
        
        async with session.post(login_url, json=login_data) as response:
            login_response = await response.json()
            print(f"Login Status: {response.status}")
            print(f"Login Response keys: {list(login_response.keys())}")
            
            if response.status == 200:
                login_access_token = login_response.get("access_token")
                print(f"Login token length: {len(login_access_token) if login_access_token else 0}")
                print(f"Login token starts with: {login_access_token[:50] if login_access_token else 'None'}...")
                print(f"Tokens are same: {access_token == login_access_token}")
                
                # Use login token for further tests
                access_token = login_access_token
        
        if not access_token:
            print("❌ No access token available")
            return
        
        # Step 3: Test token validation with different endpoints
        print("\n3️⃣ Testing Token Validation...")
        
        test_endpoints = [
            ("/auth/status", "Auth Status"),
            ("/user/me", "User Profile"),
            ("/goals", "Goals")
        ]
        
        for endpoint, name in test_endpoints:
            headers = {"Authorization": f"Bearer {access_token}"}
            url = f"{API_BASE}{endpoint}"
            
            async with session.get(url, headers=headers) as response:
                try:
                    data = await response.json()
                except:
                    data = {"error": await response.text()}
                
                print(f"\n🔍 {name} ({endpoint}):")
                print(f"  Status: {response.status}")
                print(f"  Response: {json.dumps(data, indent=4)}")
        
        # Step 4: Test without Authorization header to confirm rejection
        print("\n4️⃣ Testing Without Auth (should fail)...")
        url = f"{API_BASE}/user/me"
        async with session.get(url) as response:
            try:
                data = await response.json()
            except:
                data = {"error": await response.text()}
            print(f"Status without auth: {response.status}")
            print(f"Response: {json.dumps(data, indent=2)}")
        
        # Step 5: Test malformed token
        print("\n5️⃣ Testing Malformed Token...")
        headers = {"Authorization": "Bearer invalid-token"}
        url = f"{API_BASE}/user/me"
        async with session.get(url, headers=headers) as response:
            try:
                data = await response.json()
            except:
                data = {"error": await response.text()}
            print(f"Status with bad token: {response.status}")
            print(f"Response: {json.dumps(data, indent=2)}")
        
        # Step 6: Check if server is using test mode
        print("\n6️⃣ Testing Development Mode...")
        test_headers = {"Authorization": "Bearer test-token-for-cache-testing"}
        url = f"{API_BASE}/user/me"
        async with session.get(url, headers=test_headers) as response:
            try:
                data = await response.json()
            except:
                data = {"error": await response.text()}
            print(f"Status with test token: {response.status}")
            print(f"Test mode response: {json.dumps(data, indent=2)}")

if __name__ == "__main__":
    asyncio.run(debug_auth()) 