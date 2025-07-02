#!/usr/bin/env python3
"""
Debug JWT Token Structure

This script decodes JWT tokens to understand their exact payload structure.
"""

import asyncio
import aiohttp
import json
import time
import jwt
import base64

BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/v1"

def decode_jwt_payload(token: str) -> dict:
    """Decode JWT token payload without verification (for debugging)"""
    try:
        # Split the token
        parts = token.split('.')
        if len(parts) != 3:
            return {"error": "Invalid JWT format"}
        
        # Decode the payload (middle part)
        payload = parts[1]
        # Add padding if needed
        payload += '=' * (4 - len(payload) % 4)
        
        # Decode base64
        decoded_bytes = base64.urlsafe_b64decode(payload)
        payload_dict = json.loads(decoded_bytes.decode('utf-8'))
        
        return payload_dict
        
    except Exception as e:
        return {"error": f"Failed to decode: {str(e)}"}

async def debug_tokens():
    """Debug token structure and validation"""
    
    async with aiohttp.ClientSession() as session:
        print("🔍 JWT Token Structure Analysis")
        print("=" * 60)
        
        # Step 1: Create user and get tokens
        print("\n1️⃣ Creating user and getting tokens...")
        TEST_USER = {
            "email": f"jwt_debug_{int(time.time())}@example.com",
            "password": "TestPassword123!",
            "name": "JWT Debug User"
        }
        
        # Register
        reg_url = f"{API_BASE}/auth/register"
        async with session.post(reg_url, json=TEST_USER) as response:
            reg_data = await response.json()
            if response.status != 201:
                print(f"❌ Registration failed: {reg_data}")
                return
            
            reg_access_token = reg_data.get("access_token")
            print(f"✅ Registration token: {reg_access_token[:50]}...")
            
            # Decode registration token
            reg_payload = decode_jwt_payload(reg_access_token)
            print(f"📝 Registration token payload:")
            print(json.dumps(reg_payload, indent=2))
        
        # Login
        login_url = f"{API_BASE}/auth/login"
        login_data = {"email": TEST_USER["email"], "password": TEST_USER["password"]}
        async with session.post(login_url, json=login_data) as response:
            login_response = await response.json()
            if response.status != 200:
                print(f"❌ Login failed: {login_response}")
                return
                
            login_access_token = login_response.get("access_token")
            print(f"\n✅ Login token: {login_access_token[:50]}...")
            
            # Decode login token
            login_payload = decode_jwt_payload(login_access_token)
            print(f"📝 Login token payload:")
            print(json.dumps(login_payload, indent=2))
        
        # Step 2: Test token validation using the backend's own validation
        print("\n2️⃣ Testing backend token validation...")
        
        # Try to validate tokens by making a simple request
        for token_name, token in [("Registration", reg_access_token), ("Login", login_access_token)]:
            if not token:
                continue
                
            headers = {"Authorization": f"Bearer {token}"}
            url = f"{API_BASE}/auth/status"
            
            async with session.get(url, headers=headers) as response:
                try:
                    data = await response.json()
                except:
                    data = {"error": await response.text()}
                
                print(f"\n🔍 {token_name} token validation:")
                print(f"  Status: {response.status}")
                print(f"  Authenticated: {data.get('authenticated', 'N/A')}")
                if 'user' in data and data['user']:
                    print(f"  User ID: {data['user'].get('id', 'N/A')}")
                    print(f"  User Email: {data['user'].get('email', 'N/A')}")
                else:
                    print(f"  Error: {data.get('detail', data)}")
        
        # Step 3: Test direct token decoding with backend settings
        print("\n3️⃣ Testing with backend JWT validation...")
        
        try:
            from app.core.config import settings
            
            for token_name, token in [("Registration", reg_access_token), ("Login", login_access_token)]:
                if not token:
                    continue
                    
                try:
                    payload = jwt.decode(
                        token,
                        settings.SECRET_KEY,
                        algorithms=[settings.ALGORITHM]
                    )
                    print(f"\n✅ {token_name} token - Backend validation SUCCESS:")
                    print(f"  sub: {payload.get('sub')}")
                    print(f"  user_id: {payload.get('user_id')}")
                    print(f"  type: {payload.get('type')}")
                    print(f"  exp: {payload.get('exp')}")
                    print(f"  iat: {payload.get('iat')}")
                    
                except jwt.ExpiredSignatureError:
                    print(f"❌ {token_name} token EXPIRED")
                except jwt.InvalidTokenError as e:
                    print(f"❌ {token_name} token INVALID: {str(e)}")
                except Exception as e:
                    print(f"❌ {token_name} token ERROR: {str(e)}")
                    
        except ImportError:
            print("❌ Could not import backend settings")

if __name__ == "__main__":
    asyncio.run(debug_tokens()) 