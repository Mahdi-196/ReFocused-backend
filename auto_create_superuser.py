#!/usr/bin/env python3
"""
Automated Superuser Creation - No prompts, just creates admin account
"""

import asyncio
import sys
import os
from sqlalchemy import select

# Add the app directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.database import async_session
from app.db.models import User
from app.core.security import get_password_hash, log_security_event


async def auto_create_superuser():
    """Automatically create superuser account with predefined credentials."""
    
    # Predefined secure credentials
    email = "admin@refocused.com"
    password = "SuperAdmin123!"  # Meets all security requirements: 8+ chars, upper, lower, number, special
    name = "System Administrator"
    
    print("🚀 Auto-Creating Superuser Account...")
    
    try:
        # Get database session
        async with async_session() as db:
            # Check if user already exists
            result = await db.execute(select(User).where(User.email == email))
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                if existing_user.is_superuser:
                    print("✅ Superuser already exists!")
                    return existing_user
                else:
                    # Promote existing user
                    existing_user.is_superuser = True
                    existing_user.name = name  # Update name
                    await db.commit()
                    await db.refresh(existing_user)
                    print("✅ Existing user promoted to superuser!")
                    return existing_user
            
            # Create new superuser
            user = User(
                email=email,
                hashed_password=get_password_hash(password),
                name=name,
                is_active=True,
                is_superuser=True,
                auth_provider="local"
            )
            
            db.add(user)
            await db.commit()
            await db.refresh(user)
            
            # Log security event
            log_security_event(
                event_type="auto_superuser_created",
                details={"email": email, "user_id": user.id},
                level="info"
            )
            
            print("✅ New superuser created successfully!")
            return user
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return None


def main():
    """Main execution - run the async function."""
    
    print("🔐 ReFocused Backend - Auto Superuser Creation")
    print("=" * 50)
    
    # Run the async function
    user = asyncio.run(auto_create_superuser())
    
    if user:
        print(f"\n✅ SUCCESS! Superuser Account Ready")
        print("=" * 50)
        print(f"📧 Email:    admin@refocused.com")
        print(f"🔑 Password: SuperAdmin123!")
        print(f"👤 Name:     {user.name}")
        print(f"🆔 User ID:  {user.id}")
        print(f"⭐ Superuser: {user.is_superuser}")
        
        print(f"\n🔗 LOGIN EXAMPLES:")
        print("=" * 30)
        
        print("\n1️⃣ cURL Login:")
        print('curl -X POST "http://localhost:8000/api/v1/auth/login" \\')
        print('  -H "Content-Type: application/json" \\')
        print('  -d \'{"email": "admin@refocused.com", "password": "SuperAdmin123!"}\'')
        
        print("\n2️⃣ JSON Login Request:")
        print('''{
  "email": "admin@refocused.com", 
  "password": "SuperAdmin123!"
}''')
        
        print("\n3️⃣ Form Login (application/x-www-form-urlencoded):")
        print("username=admin@refocused.com&password=SuperAdmin123!")
        
        print(f"\n🛠️  ADMIN ENDPOINTS (Requires Bearer Token):")
        print("=" * 45)
        print("• GET    /api/v1/admin/superusers       - List all superusers")
        print("• POST   /api/v1/admin/superuser        - Create new superuser")
        print("• PATCH  /api/v1/admin/user/{id}/promote - Promote user")
        print("• PATCH  /api/v1/admin/user/{id}/demote  - Demote user")
        print("• GET    /api/v1/admin/system/info      - System statistics")
        print("• GET    /api/v1/time/*                 - Time manipulation (testing)")
        
        print(f"\n🧪 TEST ADMIN ACCESS:")
        print("=" * 25)
        print("1. Login to get token")
        print("2. Use token in Authorization header:")
        print('   curl -H "Authorization: Bearer YOUR_TOKEN" \\')
        print('     "http://localhost:8000/api/v1/admin/system/info"')
        
        print(f"\n🎉 Ready to use!")
        
    else:
        print("\n❌ Failed to create superuser. Check the error messages above.")
        sys.exit(1)


if __name__ == "__main__":
    main() 