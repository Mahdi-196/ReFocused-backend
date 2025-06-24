#!/usr/bin/env python3
"""
Comprehensive 10-Day Streak Test for Test User (test@test.com)
Tests habit streak building with date verification at each step
"""

import requests
import json
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional

class StreakTester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.user_email = "test@test.com"
        self.user_password = "test123"
        self.user_id = None
        self.token = ""
        self.headers = {}
        self.test_habit_id = None
        
    def authenticate_user(self) -> bool:
        """Authenticate as test user"""
        print(f"🔐 Authenticating as {self.user_email}...")
        
        # Try to login
        login_response = requests.post(
            f"{self.base_url}/api/v1/auth/login",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "username": self.user_email,
                "password": self.user_password,
                "grant_type": "password"
            }
        )
        
        if login_response.status_code == 200:
            auth_data = login_response.json()
            self.token = auth_data["access_token"]
            self.user_id = auth_data.get("user_id", "Unknown")
            self.headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "X-User-Timezone": "America/New_York"
            }
            print(f"✅ Successfully authenticated as {self.user_email} (ID: {self.user_id})")
            return True
        else:
            print(f"❌ Failed to authenticate: {login_response.status_code} - {login_response.text}")
            return False
    
    def get_current_time_info(self) -> Dict[str, Any]:
        """Get current time information from the system"""
        response = requests.get(f"{self.base_url}/api/v1/time/current")
        if response.status_code == 200:
            return response.json()
        return {}
    
    def set_mock_date(self, target_date: str) -> bool:
        """Set specific mock date for testing"""
        response = requests.post(
            f"{self.base_url}/api/v1/time/debug/mock-date",
            headers=self.headers,
            params={"mock_date": target_date}
        )
        if response.status_code == 200:
            result = response.json()
            print(f"📅 Mock date set to: {target_date}")
            print(f"   User timezone date: {result.get('user_current_date', 'N/A')}")
            return True
        else:
            print(f"❌ Failed to set mock date: {response.text}")
            return False
    
    def change_mock_day(self, direction: int = 1) -> Optional[str]:
        """Change mock date by days (+1 forward, -1 backward)"""
        response = requests.post(
            f"{self.base_url}/api/v1/time/debug/change-day",
            headers=self.headers,
            params={"direction": direction}
        )
        if response.status_code == 200:
            result = response.json()
            direction_text = "forward" if direction > 0 else "backward"
            print(f"🗓️  Moved {direction_text}: {result['previous_date']} → {result['new_date']}")
            return result['new_date']
        else:
            print(f"❌ Failed to change day: {response.text}")
            return None
    
    def get_user_habits(self) -> List[Dict[str, Any]]:
        """Get all habits for the user"""
        response = requests.get(f"{self.base_url}/api/v1/habits", headers=self.headers)
        if response.status_code == 200:
            habits = response.json()
            print(f"📋 Found {len(habits)} habits for user {self.user_email}")
            for habit in habits:
                print(f"   • {habit['name']} (ID: {habit['id']}, Streak: {habit.get('streak', 0)})")
            return habits
        else:
            print(f"❌ Failed to get habits: {response.text}")
            return []
    
    def create_test_habit(self, name: str = "10-Day Streak Test") -> Optional[int]:
        """Create a test habit for streak testing"""
        response = requests.post(
            f"{self.base_url}/api/v1/habits",
            headers=self.headers,
            json={"name": name, "is_favorite": False, "is_active": True}
        )
        if response.status_code == 201:
            habit_data = response.json()
            habit_id = habit_data["id"]
            print(f"✅ Created test habit '{name}' with ID {habit_id}")
            return habit_id
        else:
            print(f"❌ Failed to create habit: {response.text}")
            return None
    
    def select_or_create_habit(self) -> Optional[int]:
        """Select existing habit or create new one for testing"""
        habits = self.get_user_habits()
        
        if habits:
            print("\n🎯 Available habits:")
            for i, habit in enumerate(habits):
                print(f"   {i+1}. {habit['name']} (Current streak: {habit.get('streak', 0)})")
            
            choice = input("\nEnter habit number to use (or press Enter to create new): ").strip()
            
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(habits):
                    selected_habit = habits[idx]
                    print(f"✅ Selected habit: {selected_habit['name']} (ID: {selected_habit['id']})")
                    return selected_habit['id']
        
        # Create new habit
        return self.create_test_habit()
    
    def mark_habit_completion(self, habit_id: int, completion_date: str, completed: bool = True) -> bool:
        """Mark habit as completed/uncompleted for specific date"""
        response = requests.post(
            f"{self.base_url}/api/v1/habits/completions",
            headers=self.headers,
            json={
                "habitId": habit_id,
                "date": completion_date,
                "completed": completed
            }
        )
        
        if response.status_code == 200:
            status = "✅ Completed" if completed else "❌ Uncompleted"
            print(f"   {status} habit {habit_id} on {completion_date}")
            return True
        else:
            print(f"   ❌ Failed to mark completion: {response.text}")
            return False
    
    def get_habit_stats(self, habit_id: int) -> Dict[str, Any]:
        """Get habit statistics including current streak"""
        response = requests.get(
            f"{self.base_url}/api/v1/habits/{habit_id}/stats",
            headers=self.headers
        )
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Failed to get habit stats: {response.text}")
            return {}
    
    def verify_habit_state(self, habit_id: int, expected_streak: int, day_number: int) -> bool:
        """Verify habit streak matches expected value"""
        stats = self.get_habit_stats(habit_id)
        actual_streak = stats.get("current_streak", 0)
        longest_streak = stats.get("longest_streak", 0)
        
        time_info = self.get_current_time_info()
        current_date = time_info.get("user_date", "Unknown")
        
        print(f"   📊 Day {day_number} Status:")
        print(f"      Current Date: {current_date}")
        print(f"      Current Streak: {actual_streak} (Expected: {expected_streak})")
        print(f"      Longest Streak: {longest_streak}")
        
        if actual_streak == expected_streak:
            print(f"   ✅ Streak verification PASSED")
            return True
        else:
            print(f"   ❌ Streak verification FAILED - Expected {expected_streak}, got {actual_streak}")
            return False
    
    def build_10_day_streak(self) -> bool:
        """Build a complete 10-day streak with verification at each step"""
        print("\n🚀 Starting 10-Day Streak Build Test")
        print("=" * 60)
        
        # Set starting date
        start_date = "2025-01-20"
        if not self.set_mock_date(start_date):
            return False
        
        # Select or create habit
        habit_id = self.select_or_create_habit()
        if not habit_id:
            return False
        
        self.test_habit_id = habit_id
        
        # Verify starting state
        print(f"\n📊 Initial State Check:")
        time_info = self.get_current_time_info()
        print(f"   System Date: {time_info.get('user_date', 'Unknown')}")
        print(f"   Mock Enabled: {time_info.get('is_mock_enabled', False)}")
        print(f"   User Timezone: {time_info.get('timezone_id', 'Unknown')}")
        
        success_count = 0
        failed_days = []
        
        print(f"\n🎯 Building 10-Day Streak for Habit ID {habit_id}")
        print("-" * 40)
        
        for day in range(1, 11):  # Days 1-10
            print(f"\n📅 Day {day} of 10:")
            
            # Get current date for completion
            time_info = self.get_current_time_info()
            current_date = time_info.get("user_date")
            
            if not current_date:
                print(f"   ❌ Could not get current date")
                failed_days.append(day)
                continue
            
            print(f"   Date: {current_date}")
            
            # Mark habit completion
            if self.mark_habit_completion(habit_id, current_date, True):
                # Verify streak after completion
                if self.verify_habit_state(habit_id, day, day):
                    success_count += 1
                else:
                    failed_days.append(day)
            else:
                failed_days.append(day)
            
            # Move to next day (except on last day)
            if day < 10:
                print(f"   🔄 Moving to next day...")
                next_date = self.change_mock_day(1)
                if not next_date:
                    print(f"   ❌ Failed to advance day")
                    failed_days.append(day)
                    break
            
            print(f"   {'✅ Success' if day not in failed_days else '❌ Failed'}")
        
        # Final verification
        print("\n" + "=" * 60)
        print("🏁 FINAL STREAK VERIFICATION")
        print("=" * 60)
        
        final_stats = self.get_habit_stats(habit_id)
        final_streak = final_stats.get("current_streak", 0)
        longest_streak = final_stats.get("longest_streak", 0)
        
        time_info = self.get_current_time_info()
        final_date = time_info.get("user_date", "Unknown")
        
        print(f"📊 Final Results:")
        print(f"   Final Date: {final_date}")
        print(f"   Current Streak: {final_streak}")
        print(f"   Longest Streak: {longest_streak}")
        print(f"   Successful Days: {success_count}/10")
        print(f"   Failed Days: {failed_days}")
        
        if final_streak == 10 and success_count == 10:
            print(f"\n🎉 SUCCESS! 10-day streak built successfully!")
            print(f"   ✅ All 10 days completed")
            print(f"   ✅ Streak correctly shows 10")
            print(f"   ✅ Date tracking worked correctly")
            return True
        else:
            print(f"\n❌ PARTIAL SUCCESS - Some issues detected:")
            if final_streak != 10:
                print(f"   • Final streak is {final_streak}, expected 10")
            if success_count != 10:
                print(f"   • Only {success_count}/10 days successful")
            if failed_days:
                print(f"   • Failed on days: {failed_days}")
            return False
    
    def cleanup(self):
        """Clean up test data"""
        if self.test_habit_id:
            print(f"\n🗑️ Cleaning up test habit {self.test_habit_id}")
            response = requests.delete(
                f"{self.base_url}/api/v1/habits/{self.test_habit_id}",
                headers=self.headers
            )
            if response.status_code == 204:
                print("✅ Test habit deleted successfully")
            else:
                print(f"❌ Failed to delete test habit: {response.text}")
        
        # Reset mock date
        print("🔄 Resetting mock date to real time")
        reset_response = requests.post(
            f"{self.base_url}/api/v1/time/debug/reset-date",
            headers=self.headers
        )
        if reset_response.status_code == 200:
            print("✅ Mock date reset successfully")
        else:
            print(f"❌ Failed to reset mock date: {reset_response.text}")
    
    def run_test(self) -> bool:
        """Run the complete 10-day streak test"""
        print("🚀 10-Day Streak Test for Test User")
        print(f"📧 Email: {self.user_email}")
        print(f"🔑 Password: {self.user_password}")
        print("=" * 60)
        
        try:
            # Step 1: Authenticate
            if not self.authenticate_user():
                print("❌ Authentication failed. Please check user credentials.")
                return False
            
            # Step 2: Build 10-day streak
            return self.build_10_day_streak()
            
        except Exception as e:
            print(f"❌ Test failed with error: {str(e)}")
            return False
        finally:
            # Always cleanup
            if self.headers:  # Only cleanup if we authenticated
                self.cleanup()

def main():
    print("🎯 ReFocused Backend - 10-Day Streak Test")
    print("Testing habit streak functionality for test user")
    print("📧 Email: test@test.com")
    print("🔑 Password: test123")
    print()
    
    tester = StreakTester()
    
    success = tester.run_test()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 TEST COMPLETED SUCCESSFULLY!")
        print("✅ 10-day streak built and verified")
    else:
        print("❌ TEST COMPLETED WITH ISSUES")
        print("❗ Check the output above for details")
    print("=" * 60)

if __name__ == "__main__":
    main() 