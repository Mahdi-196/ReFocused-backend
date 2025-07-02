#!/usr/bin/env python3
"""
Direct test of enhanced_auth_service to isolate authentication issues
"""

import asyncio
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.abspath('.'))

from app.core.enhanced_auth import enhanced_auth_service
from app.db.database import async_session
from app.db.models import User
from fastapi import Request, Response
from unittest.mock import Mock
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("test")

async def test_direct_auth():
    """Test enhanced_auth_service directly"""
    
    print("🔍 Direct Enhanced Auth Service Test")
    print("=" * 50)
    
    # Create a test user first
    async with async_session() as db:
        # Check if test user exists
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.email == "test@direct.com"))
        user = result.scalar_one_or_none()
        
        if not user:
            print("Creating test user...")
            from app.core.security import get_password_hash
            user = User(
                email="test@direct.com",
                hashed_password=get_password_hash("password123"),
                name="Direct Test User",
                is_active=True
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            print(f"✅ Created user with ID: {user.id}")
        else:
            print(f"✅ Using existing user with ID: {user.id}")
    
    # Create tokens for this user
    print("\n1️⃣ Creating tokens...")
    tokens = enhanced_auth_service.create_session_tokens(user, remember_me=False)
    access_token = tokens["access_token"]
    print(f"✅ Created token: {access_token[:50]}...")
    
    # Decode the token to see its structure
    print("\n2️⃣ Decoding token...")
    import jwt
    from app.core.config import settings
    
    try:
        payload = jwt.decode(
            access_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        print(f"✅ Token payload:")
        print(f"  sub: {payload.get('sub')}")
        print(f"  user_id: {payload.get('user_id')}")
        print(f"  type: {payload.get('type')}")
        print(f"  exp: {payload.get('exp')}")
    except Exception as e:
        print(f"❌ Token decode error: {e}")
        return
    
    # Test enhanced_auth_service directly
    print("\n3️⃣ Testing enhanced_auth_service...")
    
    # Mock request with Bearer token
    mock_request = Mock(spec=Request)
    mock_request.cookies = {}
    mock_request.headers = {"Authorization": f"Bearer {access_token}"}
    mock_request.url.path = "/test"
    
    mock_response = Mock(spec=Response)
    
    async with async_session() as db:
        try:
            # Test token extraction
            extracted_token = enhanced_auth_service.extract_token_from_request(mock_request)
            print(f"✅ Token extraction: {extracted_token[:50] if extracted_token else 'None'}...")
            
            # Test token verification
            payload = await enhanced_auth_service.verify_and_refresh_if_needed(mock_request, mock_response, db)
            print(f"✅ Token verification: {payload is not None}")
            if payload:
                print(f"  Payload sub: {payload.get('sub')}")
                print(f"  Payload user_id: {payload.get('user_id')}")
            
            # Test user lookup
            found_user = await enhanced_auth_service.get_current_user_from_request(mock_request, mock_response, db)
            print(f"✅ User lookup: {found_user.email if found_user else 'None'}")
            
        except Exception as e:
            print(f"❌ Enhanced auth service error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_direct_auth()) 