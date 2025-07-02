#!/usr/bin/env python3
"""
Test with debug logging to see what's happening in authentication
"""

import asyncio
import aiohttp
import time
import logging

# Set up debug logging
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/v1"

async def test_with_debug():
    """Test authentication with debug logging"""
    
    async with aiohttp.ClientSession() as session:
        print("🔍 Testing Authentication with Debug Logging")
        print("=" * 60)
        
        # Create user and login
        TEST_USER = {
            "email": f"debug_log_{int(time.time())}@example.com",
            "password": "TestPassword123!",
            "name": "Debug Log User"
        }
        
        # Register
        print("1️⃣ Registering user...")
        reg_url = f"{API_BASE}/auth/register"
        async with session.post(reg_url, json=TEST_USER) as response:
            reg_data = await response.json()
            if response.status != 201:
                print(f"❌ Registration failed")
                return
            
            access_token = reg_data.get("access_token")
            print(f"✅ Got token: {access_token[:30]}...")
        
        # Test a simple endpoint with the token
        print("\n2️⃣ Testing /user/me endpoint...")
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{API_BASE}/user/me"
        
        async with session.get(url, headers=headers) as response:
            try:
                data = await response.json()
            except:
                data = {"error": await response.text()}
            
            print(f"Status: {response.status}")
            print(f"Response: {data}")

if __name__ == "__main__":
    asyncio.run(test_with_debug()) 