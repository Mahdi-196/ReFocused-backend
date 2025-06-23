#!/usr/bin/env python3
"""
Comprehensive Backend Habit Validation Test Script
Tests all validation features implemented in the backend.
"""

import requests
import json
from typing import Dict, Any

class HabitValidationTester:
    def __init__(self, base_url: str = "http://localhost:8000", token: str = ""):
        self.base_url = base_url
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-User-Timezone": "America/New_York"
        }
    
    def test_create_habit_success(self):
        """Test successful habit creation"""
        print("\n🧪 Testing successful habit creation...")
        
        response = requests.post(
            f"{self.base_url}/api/v1/habits",
            headers=self.headers,
            json={
                "name": "Test Exercise Habit",
                "is_favorite": False,
                "is_active": True
            }
        )
        
        if response.status_code == 201:
            habit = response.json()
            print(f"✅ SUCCESS: Created habit '{habit['name']}' with ID {habit['id']}")
            return habit["id"]
        else:
            print(f"❌ FAILED: {response.status_code} - {response.text}")
            return None
    
    def test_empty_name_validation(self):
        """Test validation for empty habit names"""
        print("\n🧪 Testing empty name validation...")
        
        test_cases = [
            "",           # Empty string
            "   ",        # Whitespace only
            "\t\n ",      # Various whitespace
        ]
        
        for empty_name in test_cases:
            response = requests.post(
                f"{self.base_url}/api/v1/habits",
                headers=self.headers,
                json={
                    "name": empty_name,
                    "is_favorite": False
                }
            )
            
            if response.status_code == 400:
                print(f"✅ SUCCESS: Rejected empty name '{repr(empty_name)}'")
            else:
                print(f"❌ FAILED: Should reject empty name '{repr(empty_name)}' - {response.status_code}")
    
    def test_duplicate_name_validation(self):
        """Test validation for duplicate habit names"""
        print("\n🧪 Testing duplicate name validation...")
        
        # Create first habit
        habit1_response = requests.post(
            f"{self.base_url}/api/v1/habits",
            headers=self.headers,
            json={
                "name": "Duplicate Test Habit",
                "is_favorite": False
            }
        )
        
        if habit1_response.status_code == 201:
            print("✅ Created first habit successfully")
            habit1_id = habit1_response.json()["id"]
            
            # Try to create duplicate
            habit2_response = requests.post(
                f"{self.base_url}/api/v1/habits",
                headers=self.headers,
                json={
                    "name": "Duplicate Test Habit",  # Same name
                    "is_favorite": False
                }
            )
            
            if habit2_response.status_code == 400:
                print("✅ SUCCESS: Rejected duplicate habit name")
            else:
                print(f"❌ FAILED: Should reject duplicate name - {habit2_response.status_code}")
            
            # Test case-sensitivity (should allow different case)
            habit3_response = requests.post(
                f"{self.base_url}/api/v1/habits",
                headers=self.headers,
                json={
                    "name": "duplicate test habit",  # Different case
                    "is_favorite": False
                }
            )
            
            if habit3_response.status_code == 201:
                print("✅ SUCCESS: Allowed different case")
                habit3_id = habit3_response.json()["id"]
                # Clean up
                requests.delete(f"{self.base_url}/api/v1/habits/{habit3_id}", headers=self.headers)
            else:
                print(f"❌ FAILED: Should allow different case - {habit3_response.status_code}")
            
            # Clean up
            requests.delete(f"{self.base_url}/api/v1/habits/{habit1_id}", headers=self.headers)
        else:
            print(f"❌ FAILED: Could not create first habit - {habit1_response.status_code}")
    
    def test_favorite_limit_validation(self):
        """Test validation for favorite habit limit (max 3)"""
        print("\n🧪 Testing favorite limit validation...")
        
        created_habits = []
        
        # Create 3 favorite habits (should succeed)
        for i in range(3):
            response = requests.post(
                f"{self.base_url}/api/v1/habits",
                headers=self.headers,
                json={
                    "name": f"Favorite Habit {i+1}",
                    "is_favorite": True
                }
            )
            
            if response.status_code == 201:
                habit_id = response.json()["id"]
                created_habits.append(habit_id)
                print(f"✅ Created favorite habit {i+1}")
            else:
                print(f"❌ FAILED: Could not create favorite habit {i+1} - {response.status_code}")
                return
        
        # Try to create 4th favorite habit (should fail)
        response = requests.post(
            f"{self.base_url}/api/v1/habits",
            headers=self.headers,
            json={
                "name": "Favorite Habit 4",
                "is_favorite": True
            }
        )
        
        if response.status_code == 400:
            print("✅ SUCCESS: Rejected 4th favorite habit")
        else:
            print(f"❌ FAILED: Should reject 4th favorite - {response.status_code}")
        
        # Test unfavoriting and then adding new favorite
        if created_habits:
            # Unfavorite first habit
            unfavorite_response = requests.put(
                f"{self.base_url}/api/v1/habits/{created_habits[0]}",
                headers=self.headers,
                json={"is_favorite": False}
            )
            
            if unfavorite_response.status_code == 200:
                print("✅ Successfully unfavorited habit")
                
                # Now try to create new favorite (should succeed)
                new_favorite_response = requests.post(
                    f"{self.base_url}/api/v1/habits",
                    headers=self.headers,
                    json={
                        "name": "New Favorite After Unfavorite",
                        "is_favorite": True
                    }
                )
                
                if new_favorite_response.status_code == 201:
                    print("✅ SUCCESS: Created new favorite after unfavoriting")
                    created_habits.append(new_favorite_response.json()["id"])
                else:
                    print(f"❌ FAILED: Should allow new favorite after unfavoriting - {new_favorite_response.status_code}")
            else:
                print(f"❌ FAILED: Could not unfavorite habit - {unfavorite_response.status_code}")
        
        # Clean up all created habits
        for habit_id in created_habits:
            requests.delete(f"{self.base_url}/api/v1/habits/{habit_id}", headers=self.headers)
    
    def test_update_validations(self):
        """Test validation during habit updates"""
        print("\n🧪 Testing update validations...")
        
        # Create test habit
        create_response = requests.post(
            f"{self.base_url}/api/v1/habits",
            headers=self.headers,
            json={
                "name": "Update Test Habit",
                "is_favorite": False
            }
        )
        
        if create_response.status_code != 201:
            print(f"❌ FAILED: Could not create test habit - {create_response.status_code}")
            return
        
        habit_id = create_response.json()["id"]
        print(f"✅ Created test habit with ID {habit_id}")
        
        # Test updating to empty name
        empty_name_response = requests.put(
            f"{self.base_url}/api/v1/habits/{habit_id}",
            headers=self.headers,
            json={"name": "   "}
        )
        
        if empty_name_response.status_code == 400:
            print("✅ SUCCESS: Rejected empty name update")
        else:
            print(f"❌ FAILED: Should reject empty name update - {empty_name_response.status_code}")
        
        # Test updating to duplicate name
        # First create another habit
        other_habit_response = requests.post(
            f"{self.base_url}/api/v1/habits",
            headers=self.headers,
            json={
                "name": "Other Habit",
                "is_favorite": False
            }
        )
        
        if other_habit_response.status_code == 201:
            other_habit_id = other_habit_response.json()["id"]
            
            # Try to update first habit to same name as second
            duplicate_response = requests.put(
                f"{self.base_url}/api/v1/habits/{habit_id}",
                headers=self.headers,
                json={"name": "Other Habit"}
            )
            
            if duplicate_response.status_code == 400:
                print("✅ SUCCESS: Rejected duplicate name update")
            else:
                print(f"❌ FAILED: Should reject duplicate name update - {duplicate_response.status_code}")
            
            # Clean up
            requests.delete(f"{self.base_url}/api/v1/habits/{other_habit_id}", headers=self.headers)
        
        # Clean up
        requests.delete(f"{self.base_url}/api/v1/habits/{habit_id}", headers=self.headers)
    
    def test_name_trimming(self):
        """Test that habit names are properly trimmed"""
        print("\n🧪 Testing name trimming...")
        
        response = requests.post(
            f"{self.base_url}/api/v1/habits",
            headers=self.headers,
            json={
                "name": "  Trimmed Habit Name  ",
                "is_favorite": False
            }
        )
        
        if response.status_code == 201:
            habit = response.json()
            if habit["name"] == "Trimmed Habit Name":
                print("✅ SUCCESS: Name was properly trimmed")
            else:
                print(f"❌ FAILED: Name not trimmed correctly - got '{habit['name']}'")
            
            # Clean up
            requests.delete(f"{self.base_url}/api/v1/habits/{habit['id']}", headers=self.headers)
        else:
            print(f"❌ FAILED: Could not create habit with spaces - {response.status_code}")
    
    def run_all_tests(self):
        """Run all validation tests"""
        print("🚀 Starting Backend Habit Validation Tests")
        print("=" * 50)
        
        if not self.token:
            print("❌ ERROR: No authentication token provided")
            return
        
        try:
            self.test_create_habit_success()
            self.test_empty_name_validation()
            self.test_duplicate_name_validation()
            self.test_favorite_limit_validation()
            self.test_update_validations()
            self.test_name_trimming()
            
            print("\n" + "=" * 50)
            print("✅ All tests completed!")
            
        except Exception as e:
            print(f"\n❌ ERROR during testing: {str(e)}")


def main():
    """Main function to run the tests"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python test_habit_validation.py <JWT_TOKEN>")
        print("Get your token by logging in first")
        sys.exit(1)
    
    token = sys.argv[1]
    tester = HabitValidationTester(token=token)
    tester.run_all_tests()


if __name__ == "__main__":
    main() 