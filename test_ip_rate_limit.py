#!/usr/bin/env python3
"""
Test script for per-IP AI chat rate limiting.
This script will test the 50 messages per day per IP limit.
"""

import asyncio
import httpx
import json
import time
from datetime import datetime, timezone

# Configuration
BASE_URL = "http://localhost:8000"
AUTH_TOKEN = "your_auth_token_here"  # Replace with actual token
TEST_MESSAGE = "Hello, this is a test message for rate limiting."

async def test_rate_limiting():
    """Test the per-IP rate limiting functionality"""
    
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    
    print(f"🚀 Testing per-IP rate limiting at {BASE_URL}")
    print(f"📅 Test started at: {datetime.now(timezone.utc).isoformat()}")
    print(f"🎯 Target: 50 messages per day per IP")
    print("-" * 60)
    
    # Test 1: Send first message and check response format
    print("\n📤 Test 1: First message")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/api/v1/ai/chat",
                headers=headers,
                json={
                    "message": f"{TEST_MESSAGE} (1/50)",
                    "system_prompt": "You are a helpful assistant. Keep responses brief."
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Success! Status: {response.status_code}")
                print(f"   Response: {data.get('response', 'N/A')[:100]}...")
                print(f"   IP Remaining: {data.get('ip_remaining', 'N/A')}")
                print(f"   IP Reset in: {data.get('ip_reset_seconds', 'N/A')} seconds")
                print(f"   Messages Remaining: {data.get('messages_remaining', 'N/A')}")
            else:
                print(f"❌ Failed! Status: {response.status_code}")
                print(f"   Response: {response.text}")
                return
                
    except Exception as e:
        print(f"❌ Error: {e}")
        return
    
    # Test 2: Send multiple messages to test counting
    print("\n📤 Test 2: Multiple messages (testing counter)")
    try:
        async with httpx.AsyncClient() as client:
            for i in range(2, 6):  # Send messages 2-5
                response = await client.post(
                    f"{BASE_URL}/api/v1/ai/chat",
                    headers=headers,
                    json={
                        "message": f"{TEST_MESSAGE} ({i}/50)",
                        "system_prompt": "You are a helpful assistant. Keep responses brief."
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"   Message {i}: IP Remaining = {data.get('ip_remaining', 'N/A')}")
                else:
                    print(f"   Message {i}: Failed with status {response.status_code}")
                    break
                    
    except Exception as e:
        print(f"❌ Error in multiple message test: {e}")
    
    # Test 3: Rapid fire to test rate limiting
    print("\n📤 Test 3: Rapid fire test (sending many messages quickly)")
    try:
        async with httpx.AsyncClient() as client:
            success_count = 0
            for i in range(6, 55):  # Try to send messages 6-55
                response = await client.post(
                    f"{BASE_URL}/api/v1/ai/chat",
                    headers=headers,
                    json={
                        "message": f"{TEST_MESSAGE} ({i}/50)",
                        "system_prompt": "You are a helpful assistant. Keep responses brief."
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    success_count += 1
                    if i % 10 == 0:  # Show progress every 10 messages
                        print(f"   Message {i}: IP Remaining = {data.get('ip_remaining', 'N/A')}")
                elif response.status_code == 429:
                    print(f"   🚫 Rate limit hit at message {i}!")
                    print(f"   Response: {response.text}")
                    print(f"   Retry-After header: {response.headers.get('Retry-After', 'N/A')}")
                    break
                else:
                    print(f"   Message {i}: Unexpected status {response.status_code}")
                    print(f"   Response: {response.text}")
                    break
                    
            print(f"   Total successful messages: {success_count}")
            
    except Exception as e:
        print(f"❌ Error in rapid fire test: {e}")
    
    # Test 4: Verify rate limit response format
    print("\n📤 Test 4: Verify rate limit response format")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/api/v1/ai/chat",
                headers=headers,
                json={
                    "message": f"{TEST_MESSAGE} (rate limit test)",
                    "system_prompt": "You are a helpful assistant. Keep responses brief."
                }
            )
            
            if response.status_code == 429:
                print("✅ Rate limit response format:")
                print(f"   Status: {response.status_code}")
                print(f"   Body: {response.text}")
                print(f"   Retry-After: {response.headers.get('Retry-After', 'N/A')}")
            else:
                print(f"❌ Expected 429, got {response.status_code}")
                print(f"   Response: {response.text}")
                
    except Exception as e:
        print(f"❌ Error in rate limit format test: {e}")
    
    print("\n" + "=" * 60)
    print("🏁 Rate limiting test completed!")
    print(f"📅 Test ended at: {datetime.now(timezone.utc).isoformat()}")

if __name__ == "__main__":
    print("⚠️  IMPORTANT: Make sure your server is running and you have a valid auth token!")
    print("   Update the AUTH_TOKEN variable in this script with your actual token.")
    print("   The server should be running on http://localhost:8000")
    print()
    
    # Check if token is set
    if AUTH_TOKEN == "your_auth_token_here":
        print("❌ Please update AUTH_TOKEN with your actual authentication token!")
        print("   You can get this by logging into your app and checking the browser's network tab.")
        exit(1)
    
    # Run the test
    asyncio.run(test_rate_limiting())


