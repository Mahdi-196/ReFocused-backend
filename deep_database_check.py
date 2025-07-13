#!/usr/bin/env python3
"""
Deep Database Check Script
==========================

This script checks ALL tables in the database for any references to a user ID or email.
"""

import asyncio
import sys
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, inspect

# Add the app directory to the Python path
sys.path.insert(0, './app')

from app.db.database import async_session, engine

async def deep_check_user_data(email: str, user_id: int):
    """Check all tables in the database for any references to the user."""
    
    async with async_session() as db:
        print(f"🔍 Deep scanning database for user: {email} (ID: {user_id})")
        print("=" * 60)
        
        # Get all table names from the database
        async with engine.connect() as conn:
            # Get table names from the database
            result = await conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """))
            tables = [row[0] for row in result.fetchall()]
        
        print(f"📋 Found {len(tables)} tables in database:")
        for table in tables:
            print(f"   - {table}")
        print()
        
        # Check each table for user_id references
        print("🔍 Checking for user_id references...")
        user_id_found = False
        
        for table in tables:
            try:
                # Check if table has user_id column
                result = await db.execute(text(f"""
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = '{table}' 
                    AND column_name = 'user_id'
                """))
                
                has_user_id = result.scalar() > 0
                
                if has_user_id:
                    # Check for records with this user_id
                    result = await db.execute(text(f"SELECT COUNT(*) FROM {table} WHERE user_id = :user_id"), {"user_id": user_id})
                    count = result.scalar()
                    if count > 0:
                        print(f"📊 {table}: {count} records with user_id={user_id}")
                        user_id_found = True
                    else:
                        print(f"✅ {table}: 0 records")
                        
            except Exception as e:
                print(f"⚠️  Could not check {table}: {e}")
        
        if not user_id_found:
            print("✅ No user_id references found in any table")
        
        print()
        
        # Check for email references
        print("🔍 Checking for email references...")
        email_found = False
        
        for table in tables:
            try:
                # Check if table has email column
                result = await db.execute(text(f"""
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = '{table}' 
                    AND column_name = 'email'
                """))
                
                has_email = result.scalar() > 0
                
                if has_email:
                    # Check for records with this email
                    result = await db.execute(text(f"SELECT COUNT(*) FROM {table} WHERE email = :email"), {"email": email})
                    count = result.scalar()
                    if count > 0:
                        print(f"📊 {table}: {count} records with email={email}")
                        email_found = True
                    else:
                        print(f"✅ {table}: 0 records")
                        
            except Exception as e:
                print(f"⚠️  Could not check {table}: {e}")
        
        if not email_found:
            print("✅ No email references found in any table")
        
        print()
        
        # Check for any string references to user ID
        print("🔍 Checking for string references to user ID...")
        string_found = False
        
        for table in tables:
            try:
                # Get all text/varchar columns
                result = await db.execute(text(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = '{table}' 
                    AND (data_type = 'text' OR data_type LIKE 'character%')
                """))
                
                text_columns = [row[0] for row in result.fetchall()]
                
                for column in text_columns:
                    # Check if any text column contains the user ID
                    result = await db.execute(text(f"SELECT COUNT(*) FROM {table} WHERE {column}::text LIKE '%{user_id}%'"))
                    count = result.scalar()
                    if count > 0:
                        print(f"📊 {table}.{column}: {count} records containing '{user_id}'")
                        string_found = True
                        
            except Exception as e:
                # Skip errors for this type of check
                pass
        
        if not string_found:
            print("✅ No string references to user ID found")
        
        print()
        print("=" * 60)
        
        if not user_id_found and not email_found and not string_found:
            print("🎉 DEEP SCAN COMPLETE: No data found for this user anywhere in the database!")
        else:
            print("❌ DEEP SCAN COMPLETE: Data still exists for this user!")

if __name__ == "__main__":
    email = "cheaxx123@gmail.com"
    user_id = 27  # From previous check
    asyncio.run(deep_check_user_data(email, user_id)) 