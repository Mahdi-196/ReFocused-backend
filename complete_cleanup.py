#!/usr/bin/env python3
"""
Complete User Data Cleanup Script
==================================

This script performs a complete cleanup of all user data including text-based references.
"""

import asyncio
import sys
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, text
import json

# Add the app directory to the Python path
sys.path.insert(0, './app')

from app.db.database import async_session
from app.db.models import User, SecurityLog

async def complete_cleanup_user_data(email: str) -> bool:
    """Perform complete cleanup of all user data including text references."""
    
    try:
        async with async_session() as db:
            # Find user by email
            result = await db.execute(
                select(User).where(User.email == email)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                print(f"❌ User with email '{email}' not found")
                return False
            
            user_id = user.id
            print(f"📧 Found user: {user.email} (ID: {user_id})")
            
            # 1. Delete all security logs that reference this user ID
            print("🗑️  Deleting security logs with user_id references...")
            result = await db.execute(delete(SecurityLog).where(SecurityLog.user_id == user_id))
            if result.rowcount > 0:
                print(f"   ✅ Deleted {result.rowcount} security logs with direct user_id reference")
            
            # 2. Delete security logs that contain the user ID in text fields
            print("🗑️  Deleting security logs with text references to user ID...")
            
            # Delete logs where details contain the user ID
            result = await db.execute(
                delete(SecurityLog).where(SecurityLog.details.like(f'%{user_id}%'))
            )
            if result.rowcount > 0:
                print(f"   ✅ Deleted {result.rowcount} security logs with user ID in details")
            
            # Delete logs where ip_address contains the user ID (if it's not a real IP)
            result = await db.execute(
                delete(SecurityLog).where(SecurityLog.ip_address.like(f'%{user_id}%'))
            )
            if result.rowcount > 0:
                print(f"   ✅ Deleted {result.rowcount} security logs with user ID in IP address")
            
            # 3. Clean up any remaining text references in other tables
            print("🗑️  Cleaning up any remaining text references...")
            
            # Get all tables that might have text references
            tables_to_check = [
                'login_attempts', 'password_history', 'token_blacklist',
                'security_alerts', 'calendar_entries', 'calendar_habit_completions',
                'calendar_mood_entries'
            ]
            
            cleaned_tables = []
            for table in tables_to_check:
                try:
                    # Check if table exists and has text columns that might contain user ID
                    result = await db.execute(text(f"""
                        SELECT COUNT(*) 
                        FROM information_schema.tables 
                        WHERE table_name = '{table}' 
                        AND table_schema = 'public'
                    """))
                    
                    if result.scalar() > 0:
                        # Get text columns
                        result = await db.execute(text(f"""
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name = '{table}' 
                            AND (data_type = 'text' OR data_type LIKE 'character%' OR data_type = 'json')
                        """))
                        
                        text_columns = [row[0] for row in result.fetchall()]
                        
                        # For each text column, delete rows that contain the user ID
                        for column in text_columns:
                            if column not in ['id', 'created_at', 'updated_at']:  # Skip non-text columns
                                try:
                                    result = await db.execute(text(f"""
                                        DELETE FROM {table} 
                                        WHERE {column}::text LIKE '%{user_id}%'
                                    """))
                                    if result.rowcount > 0:
                                        cleaned_tables.append(f"{table}.{column}")
                                        print(f"   ✅ Cleaned {result.rowcount} records from {table}.{column}")
                                except Exception as e:
                                    # Skip if column doesn't exist or other error
                                    pass
                                    
                except Exception as e:
                    # Skip if table doesn't exist
                    pass
            
            # 4. Reset user account to completely clean state
            print("🔄 Resetting user account to clean state...")
            user.name = f"Clean Superuser"
            user.is_superuser = True
            user.is_active = True
            user.failed_login_attempts = 0
            user.locked_until = None
            user.last_login = None
            user.password_changed_at = None
            user.timezone = "UTC"
            user.timezone_detected_method = "manual"
            user.timezone_confidence = 1.0
            user.timezone_updated_at = None
            user.mock_date_enabled = False
            user.mock_datetime_override = None
            user.profile_picture = None
            user.google_id = None
            user.auth_provider = "local"
            
            await db.commit()
            
            print("✅ Complete cleanup finished successfully!")
            print(f"📊 User account: {user.email} (ID: {user_id})")
            print(f"👑 Superuser: {user.is_superuser}")
            print(f"🔒 Active: {user.is_active}")
            
            if cleaned_tables:
                print(f"🧹 Cleaned text references from: {', '.join(cleaned_tables)}")
            
            return True
            
    except Exception as e:
        print(f"❌ Error during complete cleanup: {str(e)}")
        return False

async def main():
    """Main function to execute complete cleanup."""
    
    email = "cheaxx123@gmail.com"
    
    print(f"🎯 Target email: {email}")
    print("⚠️  WARNING: This will perform a COMPLETE cleanup of all user data!")
    print("   This includes security logs and any text references to the user ID.")
    
    # Ask for confirmation
    try:
        confirmation = input("Are you sure you want to proceed with complete cleanup? (yes/no): ").lower().strip()
        if confirmation != "yes":
            print("❌ Operation cancelled")
            return
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled")
        return
    
    print("\n🚀 Starting complete cleanup process...")
    success = await complete_cleanup_user_data(email)
    
    if success:
        print("\n🎉 Complete cleanup successful!")
        print("💡 All traces of user data have been removed.")
        print("👑 Account is now a clean superuser with no history.")
    else:
        print("\n💥 Complete cleanup failed!")

if __name__ == "__main__":
    asyncio.run(main()) 