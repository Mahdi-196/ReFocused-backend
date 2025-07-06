#!/usr/bin/env python3
"""
Test Streak Increment Fix
========================

This script tests the streak increment fix after advancing dates using mock time.
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timedelta

async def test_streak_increment():
    """Test that streaks increment correctly after date advancement"""
    
    # Test user credentials (from the 10-day simulation)
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
        
        # 2. Get habits
        print("2. Getting habits...")
        async with session.get(f"{base_url}/api/v1/habits", headers=headers) as response:
            if response.status != 200:
                print(f"Failed to get habits: {response.status}")
                return
            
            habits = await response.json()
            if not habits:
                print("No habits found")
                return
            
            habit = habits[0]
            habit_id = habit["id"]
            print(f"Testing habit: {habit['name']} (ID: {habit_id})")
            print(f"Initial streak: {habit['streak']}")
        
        # 3. Get current time
        print("3. Getting current time...")
        async with session.get(f"{base_url}/api/v1/time/current", headers=headers) as response:
            if response.status != 200:
                print(f"Failed to get current time: {response.status}")
                return
            
            time_data = await response.json()
            current_time_str = time_data.get("user_datetime")
            if not current_time_str:
                print("No current time found in response")
                return
            
            print(f"Current time: {current_time_str}")
        
        # 4. Advance time by 24 hours
        print("4. Advancing time by 24 hours...")
        try:
            # Parse current time and add 24 hours
            current_time = datetime.fromisoformat(current_time_str.replace('Z', '+00:00'))
            new_time = current_time + timedelta(hours=24)
            new_time_str = new_time.isoformat()
            
            # Set new mock time using correct format
            time_advance_data = {"new_datetime": new_time_str}
            async with session.post(f"{base_url}/api/v1/time/debug/set-date", json=time_advance_data, headers=headers) as response:
                if response.status != 200:
                    print(f"Failed to advance time: {response.status}")
                    response_text = await response.text()
                    print(f"Response: {response_text}")
                    return
                
                time_response = await response.json()
                print(f"Time advanced successfully to: {time_response.get('mock_datetime_utc', new_time_str)}")
        
        except Exception as e:
            print(f"Error advancing time: {str(e)}")
            return
        
        # 5. Mark habit completion for today
        print("5. Marking habit completion...")
        
        # Get current date from the time service
        async with session.get(f"{base_url}/api/v1/time/current", headers=headers) as response:
            if response.status != 200:
                print(f"Failed to get current date: {response.status}")
                return
            
            current_time_data = await response.json()
            current_date = current_time_data.get("user_date")
            if not current_date:
                print("No current date found in time response")
                return
        
        # Use the correct format that matches the 10-day simulation
        completion_data = {
            "habit_id": habit_id,
            "date": current_date,
            "completed": True
        }
        print(f"Marking habit completion for date: {current_date}")
        
        async with session.post(f"{base_url}/api/v1/habits/completions", json=completion_data, headers=headers) as response:
            if response.status != 200:
                print(f"Failed to mark completion: {response.status}")
                response_text = await response.text()
                print(f"Response: {response_text}")
                return
            
            print("Habit marked as completed")
        
        # 6. Check updated streak
        print("6. Checking updated streak...")
        async with session.get(f"{base_url}/api/v1/habits", headers=headers) as response:
            if response.status != 200:
                print(f"Failed to get updated habits: {response.status}")
                return
            
            updated_habits = await response.json()
            updated_habit = next((h for h in updated_habits if h["id"] == habit_id), None)
            
            if updated_habit:
                print(f"Updated streak: {updated_habit['streak']}")
                
                # Check if streak increased
                if updated_habit['streak'] > habit['streak']:
                    print("✅ SUCCESS: Streak incremented correctly!")
                    print(f"   Streak changed from {habit['streak']} to {updated_habit['streak']}")
                elif updated_habit['streak'] == habit['streak']:
                    print("⚠️  WARNING: Streak unchanged (the fix may not be working)")
                    print(f"   Streak remained at {habit['streak']}")
                else:
                    print("❌ ERROR: Streak decreased")
                    print(f"   Streak went from {habit['streak']} to {updated_habit['streak']}")
            else:
                print("❌ ERROR: Could not find updated habit")

if __name__ == "__main__":
    asyncio.run(test_streak_increment()) 