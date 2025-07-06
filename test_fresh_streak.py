#!/usr/bin/env python3
"""
Test Fresh Streak
================

This script tests streak building from scratch by marking completions on consecutive days.
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timedelta, date

async def test_fresh_streak():
    """Test building a streak from scratch"""
    
    # Test user credentials
    test_user = {
        "email": "test_user_20250705_132127@example.com",
        "password": "Test123!@#"
    }
    
    base_url = "http://localhost:8000"
    
    async with aiohttp.ClientSession() as session:
        # 1. Login
        print("1. Logging in...")
        async with session.post(f"{base_url}/api/v1/auth/login", json=test_user) as response:
            if response.status != 200:
                print(f"Login failed: {response.status}")
                return
            
            auth_data = await response.json()
            access_token = auth_data["access_token"]
            
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # 2. Create a new habit for testing
        print("2. Creating a new test habit...")
        habit_data = {
            "name": f"Test Streak Habit {datetime.now().strftime('%H%M%S')}",
            "is_favorite": False,
            "is_active": True
        }
        
        async with session.post(f"{base_url}/api/v1/habits", json=habit_data, headers=headers) as response:
            if response.status != 201:
                print(f"Failed to create habit: {response.status}")
                return
            
            habit = await response.json()
            habit_id = habit["id"]
            print(f"Created habit: {habit['name']} (ID: {habit_id})")
            print(f"Initial streak: {habit['streak']}")
        
        # 3. Reset to a specific date (yesterday)
        print("3. Setting base date...")
        base_date = "2025-01-15T10:00:00Z"
        
        async with session.post(f"{base_url}/api/v1/time/debug/set-date", 
                              json={"new_datetime": base_date}, headers=headers) as response:
            if response.status != 200:
                print(f"Failed to set base date: {response.status}")
                return
            
            print(f"Set base date to: {base_date}")
        
        # 4. Mark completion for Day 1
        print("4. Marking completion for Day 1...")
        
        async with session.get(f"{base_url}/api/v1/time/current", headers=headers) as response:
            if response.status != 200:
                print(f"Failed to get current date: {response.status}")
                return
            
            time_data = await response.json()
            current_date = time_data.get("user_date")
            print(f"Current date: {current_date}")
        
        completion_data = {
            "habit_id": habit_id,
            "date": current_date,
            "completed": True
        }
        
        async with session.post(f"{base_url}/api/v1/habits/completions", json=completion_data, headers=headers) as response:
            if response.status != 200:
                print(f"Failed to mark Day 1 completion: {response.status}")
                return
            
            print("✅ Day 1 completed")
        
        # Check streak after Day 1
        async with session.get(f"{base_url}/api/v1/habits", headers=headers) as response:
            habits = await response.json()
            test_habit = next((h for h in habits if h["id"] == habit_id), None)
            if test_habit:
                print(f"Streak after Day 1: {test_habit['streak']}")
        
        # 5. Advance to Day 2 and mark completion
        print("5. Advancing to Day 2...")
        
        # Advance by 24 hours
        next_day = datetime.fromisoformat(base_date.replace('Z', '+00:00')) + timedelta(days=1)
        next_day_str = next_day.isoformat()
        
        async with session.post(f"{base_url}/api/v1/time/debug/set-date", 
                              json={"new_datetime": next_day_str}, headers=headers) as response:
            if response.status != 200:
                print(f"Failed to advance to Day 2: {response.status}")
                return
            
            print(f"Advanced to: {next_day_str}")
        
        # Get current date for Day 2
        async with session.get(f"{base_url}/api/v1/time/current", headers=headers) as response:
            time_data = await response.json()
            current_date = time_data.get("user_date")
            print(f"Day 2 date: {current_date}")
        
        # Mark completion for Day 2
        completion_data = {
            "habit_id": habit_id,
            "date": current_date,
            "completed": True
        }
        
        async with session.post(f"{base_url}/api/v1/habits/completions", json=completion_data, headers=headers) as response:
            if response.status != 200:
                print(f"Failed to mark Day 2 completion: {response.status}")
                return
            
            print("✅ Day 2 completed")
        
        # Check final streak
        async with session.get(f"{base_url}/api/v1/habits", headers=headers) as response:
            habits = await response.json()
            test_habit = next((h for h in habits if h["id"] == habit_id), None)
            if test_habit:
                final_streak = test_habit['streak']
                print(f"Final streak after Day 2: {final_streak}")
                
                if final_streak == 2:
                    print("🎉 SUCCESS: Streak incremented correctly!")
                elif final_streak == 1:
                    print("⚠️  PARTIAL: Only 1-day streak (Day 1 might not count)")
                elif final_streak == 0:
                    print("❌ FAILURE: Streak still 0 - fix not working")
                else:
                    print(f"🤔 UNEXPECTED: Streak is {final_streak}")
        
        # 6. Clean up - delete test habit
        print("6. Cleaning up test habit...")
        async with session.delete(f"{base_url}/api/v1/habits/{habit_id}", headers=headers) as response:
            if response.status == 204:
                print("✅ Test habit deleted")
            else:
                print(f"⚠️  Failed to delete test habit: {response.status}")

if __name__ == "__main__":
    asyncio.run(test_fresh_streak()) 