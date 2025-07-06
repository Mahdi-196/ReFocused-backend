#!/usr/bin/env python3
"""
Debug Streak Issue Script
========================

This script investigates the habit streak calculation issue identified in the 10-day simulation.
"""

import asyncio
import sys
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.db.database import async_session
from app.db.models import User, Habit, HabitCompletion
from app.services.time_service import TimeService
from datetime import date, datetime, timedelta
import pytz

async def debug_streak_issue():
    """Debug the streak calculation issue"""
    async with async_session() as db:
        # Find the test user from our simulation
        result = await db.execute(
            select(User).where(User.email.like("test_user_%@example.com"))
        )
        user = result.scalar_one_or_none()
        
        if not user:
            print("No test user found")
            return
        
        print(f"Found test user: {user.email} (ID: {user.id})")
        print(f"Mock date enabled: {getattr(user, 'mock_date_enabled', False)}")
        print(f"Mock datetime: {getattr(user, 'mock_datetime_override', 'None')}")
        
        # Get current time info
        time_service = TimeService()
        current_date = time_service.get_user_current_date(user)
        current_time = time_service.get_current_time_for_user(user)
        
        print(f"Current date: {current_date}")
        print(f"Current time: {current_time}")
        print()
        
        # Get habits for this user
        habits_result = await db.execute(
            select(Habit).where(Habit.user_id == user.id)
        )
        habits = habits_result.scalars().all()
        
        print(f"Found {len(habits)} habits:")
        for habit in habits:
            print(f"  - {habit.name} (ID: {habit.id}, Streak: {habit.streak})")
            print(f"    Last updated: {habit.last_updated_utc}")
            
            # Get all completions for this habit
            completions_result = await db.execute(
                select(HabitCompletion).where(
                    HabitCompletion.habit_id == habit.id
                ).order_by(HabitCompletion.date.desc())
            )
            completions = completions_result.scalars().all()
            
            print(f"    Completions ({len(completions)}):")
            for completion in completions:
                print(f"      {completion.date}: {completion.completed} (created: {completion.completed_at})")
            
            # Manual streak calculation
            print(f"    Manual streak calculation:")
            manual_streak = 0
            check_date = current_date
            
            for i in range(20):  # Check last 20 days
                completion_result = await db.execute(
                    select(HabitCompletion).where(
                        and_(
                            HabitCompletion.habit_id == habit.id,
                            HabitCompletion.date == check_date,
                            HabitCompletion.completed == True
                        )
                    )
                )
                completed = completion_result.scalar_one_or_none() is not None
                
                print(f"      {check_date}: {completed}")
                
                if not completed:
                    break
                    
                manual_streak += 1
                check_date -= timedelta(days=1)
            
            print(f"    Manual streak: {manual_streak}")
            print(f"    Stored streak: {habit.streak}")
            print(f"    Match: {manual_streak == habit.streak}")
            print()

async def main():
    """Main function"""
    await debug_streak_issue()

if __name__ == "__main__":
    asyncio.run(main()) 