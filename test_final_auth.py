#!/usr/bin/env python3
"""
Final Authentication Test

This script tests the key endpoints after our fixes to verify everything works.
"""

import asyncio
import aiohttp
import json
import time

BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/v1"

async def test_complete_auth_flow():
    """Test the complete authentication flow"""
    
    async with aiohttp.ClientSession() as session:
        print("🔐 Final Authentication Test")
        print("=" * 50)
        
        # Step 1: Create user
        TEST_USER = {
            "email": f"final_test_{int(time.time())}@example.com",
            "password": "TestPassword123!",
            "name": "Final Test User"
        }
        
        print("\n1️⃣ Registration...")
        reg_url = f"{API_BASE}/auth/register"
        async with session.post(reg_url, json=TEST_USER) as response:
            reg_data = await response.json()
            if response.status != 201:
                print(f"❌ Registration failed: {reg_data}")
                return
            print(f"✅ Registration successful")
            reg_token = reg_data.get("access_token")
        
        print("\n2️⃣ Login...")
        login_url = f"{API_BASE}/auth/login"
        login_data = {"email": TEST_USER["email"], "password": TEST_USER["password"]}
        async with session.post(login_url, json=login_data) as response:
            login_response = await response.json()
            if response.status != 200:
                print(f"❌ Login failed: {login_response}")
                return
            print(f"✅ Login successful")
            login_token = login_response.get("access_token")
        
        # Step 2: Test key endpoints with both tokens
        key_endpoints = [
            ("GET", "/auth/status", "Auth Status"),
            ("GET", "/auth/me", "Auth Me"),
            ("GET", "/user/me", "User Profile"),
            ("GET", "/goals", "Goals"),
            ("POST", "/goals", "Create Goal", {
                "title": "Test Goal",
                "description": "Test goal description",
                "target_date": "2025-07-30",
                "priority": "medium"
            }),
        ]
        
        for token_name, token in [("Registration", reg_token), ("Login", login_token)]:
            print(f"\n3️⃣ Testing with {token_name} token...")
            
            headers = {"Authorization": f"Bearer {token}"}
            
            for method, endpoint, name, *data in key_endpoints:
                request_data = data[0] if data else None
                url = f"{API_BASE}{endpoint}"
                
                try:
                    async with session.request(method, url, json=request_data, headers=headers) as response:
                        try:
                            response_data = await response.json()
                        except:
                            response_data = {"error": await response.text()}
                        
                        status_icon = "✅" if 200 <= response.status < 300 else "❌"
                        print(f"  {status_icon} {method} {endpoint} ({name}): {response.status}")
                        
                        if response.status >= 400:
                            print(f"    Error: {response_data.get('detail', response_data)}")
                        elif 'authenticated' in response_data:
                            print(f"    Authenticated: {response_data['authenticated']}")
                        elif 'id' in response_data:
                            print(f"    User/Goal ID: {response_data['id']}")
                        
                except Exception as e:
                    print(f"  ❌ {method} {endpoint}: Exception - {str(e)}")
        
        # Step 3: Test logout
        print("\n4️⃣ Testing logout...")
        logout_url = f"{API_BASE}/auth/logout"
        headers = {"Authorization": f"Bearer {login_token}"}
        
        try:
            async with session.post(logout_url, headers=headers) as response:
                status_icon = "✅" if 200 <= response.status < 300 else "❌"
                print(f"  {status_icon} Logout: {response.status}")
                
                if response.status >= 400:
                    try:
                        error_data = await response.json()
                        print(f"    Error: {error_data.get('detail', error_data)}")
                    except:
                        error_text = await response.text()
                        print(f"    Error: {error_text}")
                else:
                    print(f"    Successfully logged out")
                    
        except Exception as e:
            print(f"  ❌ Logout exception: {str(e)}")
        
        print("\n🎯 Authentication Test Complete!")

if __name__ == "__main__":
    asyncio.run(test_complete_auth_flow()) 