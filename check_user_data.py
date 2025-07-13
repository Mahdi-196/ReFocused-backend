#!/usr/bin/env python3
"""
Check User Data Script
======================

This script checks all data associated with a user account to see what still exists.
"""

import asyncio
import sys
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

# Add the app directory to the Python path
sys.path.insert(0, './app')

from app.db.database import async_session
from app.db.models import (
    User, Goal2Week, GoalLongTerm, QuickAccess, Habit, HabitCompletion, 
    HabitStreak, MoodEntry, PomodoroSettings, StudySet, Flashcard, 
    Mantra, JournalCollection, JournalEntry, Gratitude, UserStatistics,
    PasswordHistory, LoginAttempt, SecurityLog, TokenBlacklist
)

async def check_user_data(email: str):
    """Check all data associated with a user account."""
    
    async with async_session() as db:
        # Find user by email
        result = await db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"❌ User with email '{email}' not found")
            return
        
        user_id = user.id
        print(f"📧 Found user: {user.email} (ID: {user_id})")
        print(f"👑 Superuser: {user.is_superuser}")
        print(f"🔒 Active: {user.is_active}")
        print()
        
        # Check all data types
        checks = [
            ("Goal2Week", Goal2Week, Goal2Week.user_id == user_id),
            ("GoalLongTerm", GoalLongTerm, GoalLongTerm.user_id == user_id),
            ("QuickAccess", QuickAccess, QuickAccess.user_id == user_id),
            ("Habit", Habit, Habit.user_id == user_id),
            ("MoodEntry", MoodEntry, MoodEntry.user_id == user_id),
            ("PomodoroSettings", PomodoroSettings, PomodoroSettings.user_id == user_id),
            ("StudySet", StudySet, StudySet.user_id == user_id),
            ("Mantra", Mantra, Mantra.user_id == user_id),
            ("JournalCollection", JournalCollection, JournalCollection.user_id == user_id),
            ("Gratitude", Gratitude, Gratitude.user_id == user_id),
            ("UserStatistics", UserStatistics, UserStatistics.user_id == user_id),
            ("PasswordHistory", PasswordHistory, PasswordHistory.user_id == user_id),
            ("LoginAttempt", LoginAttempt, LoginAttempt.user_id == user_id),
            ("SecurityLog", SecurityLog, SecurityLog.user_id == user_id),
        ]
        
        total_records = 0
        
        for table_name, model, condition in checks:
            result = await db.execute(select(func.count()).select_from(model).where(condition))
            count = result.scalar()
            if count > 0:
                print(f"📊 {table_name}: {count} records")
                total_records += count
        
        # Check for habit-related data
        if total_records > 0:
            habits_result = await db.execute(select(Habit.id).where(Habit.user_id == user_id))
            habit_ids = [row[0] for row in habits_result.fetchall()]
            
            if habit_ids:
                # Check habit completions
                result = await db.execute(select(func.count()).select_from(HabitCompletion).where(HabitCompletion.habit_id.in_(habit_ids)))
                count = result.scalar()
                if count > 0:
                    print(f"📊 HabitCompletion: {count} records")
                    total_records += count
                
                # Check habit streaks
                result = await db.execute(select(func.count()).select_from(HabitStreak).where(HabitStreak.habit_id.in_(habit_ids)))
                count = result.scalar()
                if count > 0:
                    print(f"📊 HabitStreak: {count} records")
                    total_records += count
        
        # Check for journal-related data
        collections_result = await db.execute(select(JournalCollection.id).where(JournalCollection.user_id == user_id))
        collection_ids = [row[0] for row in collections_result.fetchall()]
        
        if collection_ids:
            # Check journal entries
            result = await db.execute(select(func.count()).select_from(JournalEntry).where(JournalEntry.collection_id.in_(collection_ids)))
            count = result.scalar()
            if count > 0:
                print(f"📊 JournalEntry: {count} records")
                total_records += count
        
        # Check for study-related data
        study_sets_result = await db.execute(select(StudySet.id).where(StudySet.user_id == user_id))
        study_set_ids = [row[0] for row in study_sets_result.fetchall()]
        
        if study_set_ids:
            # Check flashcards
            result = await db.execute(select(func.count()).select_from(Flashcard).where(Flashcard.set_id.in_(study_set_ids)))
            count = result.scalar()
            if count > 0:
                print(f"📊 Flashcard: {count} records")
                total_records += count
        
        # Check for any other tables that might reference this user
        print()
        print("🔍 Checking for any additional data...")
        
        # Query all tables that have a user_id column
        tables_with_user_id = [
            "goals_2_week", "goals_long_term", "quick_access", "habits", 
            "mood_entries", "pomodoro_settings", "study_sets", "mantras", 
            "journal_collections", "gratitude_entries", "user_statistics",
            "password_history", "login_attempts", "security_logs"
        ]
        
        for table_name in tables_with_user_id:
            try:
                result = await db.execute(text(f"SELECT COUNT(*) FROM {table_name} WHERE user_id = :user_id"), {"user_id": user_id})
                count = result.scalar()
                if count > 0:
                    print(f"🔍 {table_name}: {count} records found")
            except Exception as e:
                print(f"⚠️  Could not check {table_name}: {e}")
        
        print()
        if total_records > 0:
            print(f"❌ Total records found: {total_records}")
            print("🗑️  Data cleanup needed!")
        else:
            print("✅ No data found for this user")

if __name__ == "__main__":
    email = "cheaxx123@gmail.com"
    asyncio.run(check_user_data(email)) 