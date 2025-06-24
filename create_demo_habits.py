#!/usr/bin/env python3
"""
Create demo habits for the test user to populate the dashboard
"""

import requests
import json
from datetime import datetime, date, timedelta

def create_demo_habits():
    """Create demo habits with some existing completions"""
    
    base_url = "http://localhost:8000"
    
    # Login as test user
    print("🔐 Logging in as test user...")
    login_response = requests.post(
        f"{base_url}/api/v1/auth/login",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "username": "test@test.com",
            "password": "test123",
            "grant_type": "password"
        }
    )
    
    if login_response.status_code != 200:
        print(f"❌ Login failed: {login_response.text}")
        return
    
    auth_data = login_response.json()
    token = auth_data["access_token"]
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-User-Timezone": "America/New_York"
    }
    
    print("✅ Successfully logged in!")
    
    # Demo habits to create
    demo_habits = [
        {"name": "Morning Exercise", "is_favorite": True},
        {"name": "Read 20 Minutes", "is_favorite": True},
        {"name": "Drink 8 Glasses Water", "is_favorite": False},
        {"name": "Meditate", "is_favorite": True},
        {"name": "Write Journal", "is_favorite": False}
    ]
    
    created_habits = []
    
    # Create habits
    print(f"\n📝 Creating {len(demo_habits)} demo habits...")
    for habit_data in demo_habits:
        response = requests.post(
            f"{base_url}/api/v1/habits",
            headers=headers,
            json=habit_data
        )
        
        if response.status_code == 201:
            habit = response.json()
            created_habits.append(habit)
            favorite_star = "⭐" if habit["is_favorite"] else ""
            print(f"   ✅ {habit['name']} {favorite_star} (ID: {habit['id']})")
        else:
            print(f"   ❌ Failed to create {habit_data['name']}: {response.text}")
    
    # Set mock date to build some history
    print(f"\n📅 Setting up habit history...")
    
    # Set date to 5 days ago to build some streaks
    start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    
    requests.post(
        f"{base_url}/api/v1/time/debug/mock-date",
        headers=headers,
        params={"mock_date": start_date}
    )
    
    # Complete some habits over the past few days
    for day in range(5):  # Past 5 days
        current_date = (datetime.now() - timedelta(days=5-day)).strftime("%Y-%m-%d")
        
        # Set mock date
        requests.post(
            f"{base_url}/api/v1/time/debug/mock-date",
            headers=headers,
            params={"mock_date": current_date}
        )
        
        print(f"   📅 Day {day+1} ({current_date}):")
        
        # Complete different habits on different days to create varied streaks
        for i, habit in enumerate(created_habits):
            should_complete = False
            
            # Morning Exercise - complete most days (build good streak)
            if habit["name"] == "Morning Exercise" and day != 2:  # skip day 3
                should_complete = True
            
            # Read 20 Minutes - complete every day (perfect streak)
            elif habit["name"] == "Read 20 Minutes":
                should_complete = True
            
            # Drink Water - complete occasionally 
            elif habit["name"] == "Drink 8 Glasses Water" and day in [0, 2, 4]:
                should_complete = True
            
            # Meditate - complete last 3 days (recent streak)
            elif habit["name"] == "Meditate" and day >= 2:
                should_complete = True
            
            # Journal - complete first 2 days only (broken streak)
            elif habit["name"] == "Write Journal" and day < 2:
                should_complete = True
            
            if should_complete:
                response = requests.post(
                    f"{base_url}/api/v1/habits/completions",
                    headers=headers,
                    json={
                        "habitId": habit["id"],
                        "date": current_date,
                        "completed": True
                    }
                )
                
                if response.status_code == 200:
                    print(f"      ✅ {habit['name']}")
                else:
                    print(f"      ❌ Failed: {habit['name']}")
    
    # Reset to current date
    print(f"\n🔄 Resetting to current date...")
    reset_response = requests.post(
        f"{base_url}/api/v1/time/debug/reset-date",
        headers=headers
    )
    
    # Get final habit stats
    print(f"\n📊 Final Habit Status:")
    habits_response = requests.get(f"{base_url}/api/v1/habits", headers=headers)
    
    if habits_response.status_code == 200:
        habits = habits_response.json()
        for habit in habits:
            streak = habit.get("streak", 0)
            favorite = "⭐" if habit.get("is_favorite") else "  "
            print(f"   {favorite} {habit['name']:<20} - Streak: {streak} days")
    
    print(f"\n🎉 Demo habits created successfully!")
    print(f"📧 Login to frontend with: test@test.com / test123")
    print(f"🔄 Refresh your dashboard to see the habits!")

if __name__ == "__main__":
    create_demo_habits() 