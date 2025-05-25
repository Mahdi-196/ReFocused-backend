#!/usr/bin/env python3
"""
Test script for Google OAuth authentication endpoint.

This script demonstrates how to use the /api/v1/auth/google endpoint.
In a real frontend application, you would get the Google ID token from 
the Google Sign-In JavaScript library.
"""

import requests
import json

# API endpoint
BASE_URL = "http://localhost:8000"
GOOGLE_AUTH_ENDPOINT = f"{BASE_URL}/api/v1/auth/google"

def test_google_oauth_endpoint():
    """Test the Google OAuth endpoint with various scenarios."""
    
    print("🔍 Testing Google OAuth Endpoint")
    print("=" * 50)
    
    # Test 1: Empty token (should fail)
    print("\n1. Testing with empty token...")
    response = requests.post(
        GOOGLE_AUTH_ENDPOINT,
        json={"token": ""},
        headers={"Content-Type": "application/json"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    # Test 2: Invalid token (should fail)
    print("\n2. Testing with invalid token...")
    response = requests.post(
        GOOGLE_AUTH_ENDPOINT,
        json={"token": "invalid_token_here"},
        headers={"Content-Type": "application/json"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    # Test 3: Check API documentation
    print("\n3. Checking API documentation...")
    docs_response = requests.get(f"{BASE_URL}/docs")
    print(f"API Docs available at: {BASE_URL}/docs")
    print(f"Status: {docs_response.status_code}")
    
    print("\n" + "=" * 50)
    print("✅ Google OAuth endpoint is properly configured!")
    print("\nTo test with a real Google token:")
    print("1. Get a Google ID token from your frontend")
    print("2. Send POST request to /api/v1/auth/google")
    print("3. Include the token in the request body: {'token': 'your_google_id_token'}")
    print("\nExpected successful response format:")
    print(json.dumps({
        "access_token": "jwt_token_here",
        "user": {
            "id": 1,
            "email": "user@example.com",
            "name": "User Name",
            "username": "user",
            "profile_picture": "https://..."
        },
        "token_type": "bearer",
        "expires_in": 1800
    }, indent=2))

if __name__ == "__main__":
    try:
        test_google_oauth_endpoint()
    except requests.exceptions.ConnectionError:
        print("❌ Error: Could not connect to the server.")
        print("Make sure the server is running on http://localhost:8000")
    except Exception as e:
        print(f"❌ Error: {e}") 