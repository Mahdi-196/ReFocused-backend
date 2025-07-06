#!/usr/bin/env python3
"""
Grant Admin Privileges Script
============================

This script grants admin/superuser privileges to a test user to allow access
to debug endpoints like the mock time functionality.
"""

import asyncio
import sys
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.db.database import async_session
from app.db.models import User

async def grant_admin_privileges(email: str) -> bool:
    """Grant admin privileges to a user by email"""
    try:
        async with async_session() as db:
            # Find user by email
            result = await db.execute(
                select(User).where(User.email == email)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                print(f"User with email '{email}' not found")
                return False
            
            # Update user to have admin privileges
            user.is_superuser = True
            await db.commit()
            
            print(f"Successfully granted admin privileges to user: {email} (ID: {user.id})")
            return True
            
    except Exception as e:
        print(f"Error granting admin privileges: {str(e)}")
        return False

async def main():
    """Main function"""
    if len(sys.argv) != 2:
        print("Usage: python grant_admin_privileges.py <user_email>")
        sys.exit(1)
    
    email = sys.argv[1]
    success = await grant_admin_privileges(email)
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 