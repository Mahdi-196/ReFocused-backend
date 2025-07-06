#!/usr/bin/env python3
"""
Test Streak Fix Script
=====================

This script tests if the streak calculation fix is working correctly.
"""

import asyncio
import sys
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.db.database import async_session
from app.db.models import User, Habit, HabitCompletion
from app.crud.habit import habit_crud
from app.services.time_service import TimeService
from datetime import date, datetime, timedelta
import pytz

async def test_streak_fix():
    """Test the streak calculation fix"""
    async with async_session() as db:
        # Find the test user from our simulation
        result = await db.execute(
            select(User).where(User.email.like("test_user_%@example.com"))
        )
        user = result.scalar_one_or_none()
        
        if not user:
            print("No test user found")
            return
        
        print(f"Testing streak fix for user: {user.email}")
        
        # Get habits for this user
        habits_result = await db.execute(
            select(Habit).where(Habit.user_id == user.id)
        )
        habits = habits_result.scalars().all()
        
        print(f"Found {len(habits)} habits")
        
        for habit in habits:
            print(f"\nTesting habit: {habit.name} (ID: {habit.id})")
            print(f"Current stored streak: {habit.streak}")
            
            # Manually recalculate the streak using the fixed method
            try:
                calculated_streak = await habit_crud._recalculate_habit_streak(db, habit.id, user)
                print(f"Recalculated streak: {calculated_streak}")
                
                # Commit the changes
                await db.commit()
                
                # Fetch the habit again to see the updated streak
                updated_habit_result = await db.execute(
                    select(Habit).where(Habit.id == habit.id)
                )
                updated_habit = updated_habit_result.scalar_one_or_none()
                
                if updated_habit:
                    print(f"Updated stored streak: {updated_habit.streak}")
                    print(f"Fix successful: {updated_habit.streak == calculated_streak}")
                
            except Exception as e:
                print(f"Error testing habit {habit.id}: {str(e)}")
                await db.rollback()

async def main():
    """Main function"""
    await test_streak_fix()

if __name__ == "__main__":
    asyncio.run(main()) 