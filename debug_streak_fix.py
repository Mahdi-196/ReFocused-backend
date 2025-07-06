#!/usr/bin/env python3
"""
Debug Streak Fix
================

This script debugs the streak increment issue by checking habit completion history.
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timedelta, date

async def debug_streak_fix():
    """Debug why streaks aren't incrementing"""
    
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
            print(f"Debugging habit: {habit['name']} (ID: {habit_id})")
            print(f"Current streak: {habit['streak']}")
        
        # 3. Get current time
        print("3. Getting current time...")
        async with session.get(f"{base_url}/api/v1/time/current", headers=headers) as response:
            if response.status != 200:
                print(f"Failed to get current time: {response.status}")
                return
            
            time_data = await response.json()
            current_date = time_data.get("user_date")
            current_time = time_data.get("user_datetime")
            print(f"Current date: {current_date}")
            print(f"Current time: {current_time}")
        
        # 4. Get habit completion history
        print("4. Getting habit completion history...")
        
        # Calculate date range for last 10 days
        current_date_obj = date.fromisoformat(current_date)
        start_date = current_date_obj - timedelta(days=10)
        
        # Skip completion history for now due to API error
        print("   Skipping completion history due to API error")
        
        # 5. Use the debug endpoint
        print("5. Using debug endpoint...")
        async with session.get(f"{base_url}/api/v1/habits/{habit_id}/debug", headers=headers) as response:
            if response.status != 200:
                print(f"Debug endpoint failed: {response.status}")
                response_text = await response.text()
                print(f"Response: {response_text}")
                return
            
            debug_data = await response.json()
            print(f"Debug information:")
            print(f"  - Stored streak: {debug_data.get('stored_streak')}")
            print(f"  - Fresh calculation: {debug_data.get('fresh_calculation')}")
            print(f"  - Streaks match: {debug_data.get('streaks_match')}")
            print(f"  - Current date: {debug_data.get('current_date')}")
            print(f"  - Last completion: {debug_data.get('last_completion')}")
            print(f"  - Completion count: {debug_data.get('completion_count')}")
            print(f"  - Completion dates: {debug_data.get('completion_dates')}")
        
        # 6. Check if we need to refresh the streak
        if debug_data.get('stored_streak') != debug_data.get('fresh_calculation'):
            print("6. Refreshing streak...")
            async with session.post(f"{base_url}/api/v1/habits/{habit_id}/refresh-streak", headers=headers) as response:
                if response.status != 200:
                    print(f"Failed to refresh streak: {response.status}")
                    return
                
                refresh_data = await response.json()
                print(f"Streak refreshed: {refresh_data.get('new_streak')}")
        else:
            print("6. Streaks match - no refresh needed")
                
        # 7. Check final habit state
        print("7. Checking final habit state...")
        async with session.get(f"{base_url}/api/v1/habits", headers=headers) as response:
            if response.status != 200:
                print(f"Failed to get final habits: {response.status}")
                return
            
            final_habits = await response.json()
            final_habit = next((h for h in final_habits if h["id"] == habit_id), None)
            if final_habit:
                print(f"Final streak: {final_habit['streak']}")
                print(f"Last completed: {final_habit.get('last_completed_date')}")

if __name__ == "__main__":
    asyncio.run(debug_streak_fix()) 