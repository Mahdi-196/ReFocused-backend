#!/usr/bin/env python3
"""
Create a test user for habit streak testing
"""

from app.db.models import User
from app.core.security import get_password_hash
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from sqlalchemy import create_engine

def create_test_user():
    """Create a test user with simple credentials"""
    
    # Database connection
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Simple test user credentials
        email = "test@test.com"
        password = "test123"
        name = "Test User"
        
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            print(f"✅ User already exists:")
            print(f"   📧 Email: {email}")
            print(f"   🆔 User ID: {existing_user.id}")
            print(f"   🔑 Password: {password}")
            return existing_user.id, email, password
        
        # Hash the password
        hashed_password = get_password_hash(password)
        
        # Create new user
        new_user = User(
            email=email,
            name=name,
            hashed_password=hashed_password,
            is_active=True,
            timezone="America/New_York"
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        print(f"🎉 Successfully created test user!")
        print(f"   📧 Email: {email}")
        print(f"   🆔 User ID: {new_user.id}")
        print(f"   🔑 Password: {password}")
        print(f"   👤 Name: {name}")
        print(f"   🌍 Timezone: America/New_York")
        
        return new_user.id, email, password
        
    except Exception as e:
        print(f"❌ Error creating user: {str(e)}")
        db.rollback()
        return None, None, None
    finally:
        db.close()

if __name__ == "__main__":
    print("🚀 Creating Test User for Habit Streak Testing")
    print("=" * 50)
    
    user_id, email, password = create_test_user()
    
    if user_id:
        print("\n" + "=" * 50)
        print("✅ Test User Ready!")
        print(f"📋 Login Credentials:")
        print(f"   Email: {email}")
        print(f"   Password: {password}")
        print(f"   User ID: {user_id}")
        print("=" * 50)
    else:
        print("\n❌ Failed to create test user") 