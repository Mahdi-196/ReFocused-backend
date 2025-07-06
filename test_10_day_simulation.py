#!/usr/bin/env python3
"""
10-Day Application Testing Script
=====================================

This script conducts a comprehensive 10-day simulation test of the application's
core user features including:
- User authentication and management
- Goal creation and tracking (perpetual and 2-week goals)
- Mood tracking and history
- Habit tracking and streak management
- Time-based functionality with mock time progression

The script uses the application's mock time endpoint to simulate the passage of time
and tests all daily reset logic, streak calculations, and data archival.
"""

import asyncio
import aiohttp
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import sys
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('test_10_day_simulation.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class TestUser:
    """Test user data"""
    email: str
    password: str
    name: str
    access_token: Optional[str] = None
    user_id: Optional[int] = None

@dataclass
class TestGoal:
    """Test goal data"""
    id: Optional[int] = None
    name: str = ""
    goal_type: str = "checklist"
    duration: str = "long_term"
    target_value: int = 1
    current_value: int = 0
    is_completed: bool = False
    expires_at: Optional[str] = None

@dataclass
class TestHabit:
    """Test habit data"""
    id: Optional[int] = None
    name: str = ""
    streak: int = 0
    is_favorite: bool = False

@dataclass
class DailyTestResults:
    """Daily test results"""
    day: int
    date: str
    user_authenticated: bool
    goals_created: bool
    mood_recorded: bool
    habit_completed: bool
    streak_incremented: bool
    time_advanced: bool
    errors: List[str]
    streak_values: Dict[str, int]

class ApplicationTester:
    """Main application tester class"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
        self.test_user: Optional[TestUser] = None
        self.test_goals: List[TestGoal] = []
        self.test_habits: List[TestHabit] = []
        self.daily_results: List[DailyTestResults] = []
        self.start_time: Optional[datetime] = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
            
    async def make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                          headers: Optional[Dict] = None) -> Dict[str, Any]:
        """Make HTTP request to the application"""
        url = f"{self.base_url}{endpoint}"
        
        # Add authentication header if available
        if self.test_user and self.test_user.access_token:
            if not headers:
                headers = {}
            headers["Authorization"] = f"Bearer {self.test_user.access_token}"
        
        try:
            async with self.session.request(method, url, json=data, headers=headers) as response:
                response_data = await response.json()
                
                if response.status >= 400:
                    logger.error(f"HTTP {response.status} - {method} {endpoint}: {response_data}")
                    return {"error": response_data, "status": response.status}
                
                return response_data
                
        except Exception as e:
            logger.error(f"Request failed - {method} {endpoint}: {str(e)}")
            return {"error": str(e), "status": 500}
    
    async def create_test_user(self) -> bool:
        """Create a test user with admin privileges"""
        logger.info("Creating test user...")
        
        # Generate unique test user credentials
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.test_user = TestUser(
            email=f"test_user_{timestamp}@example.com",
            password="Test123!@#",
            name=f"Test User {timestamp}"
        )
        
        # Register user
        register_data = {
            "email": self.test_user.email,
            "password": self.test_user.password,
            "name": self.test_user.name
        }
        
        response = await self.make_request("POST", "/api/v1/auth/register", register_data)
        if "error" in response:
            logger.error(f"User registration failed: {response}")
            return False
        
        # Extract access token and user ID
        self.test_user.access_token = response.get("access_token")
        
        # Get user profile to extract user ID
        profile_response = await self.make_request("GET", "/api/v1/auth/me")
        if "error" in profile_response:
            logger.error(f"Failed to get user profile: {profile_response}")
            return False
            
        self.test_user.user_id = profile_response.get("id")
        
        # Update user to have admin privileges for mock time access
        logger.info("Granting admin privileges to test user...")
        try:
            # Import database modules
            from sqlalchemy.ext.asyncio import AsyncSession
            from sqlalchemy import select
            from app.db.database import async_session
            from app.db.models import User
            
            # Grant admin privileges
            async with async_session() as db:
                result = await db.execute(
                    select(User).where(User.email == self.test_user.email)
                )
                user = result.scalar_one_or_none()
                
                if user:
                    user.is_superuser = True
                    await db.commit()
                    logger.info("Admin privileges granted successfully")
                else:
                    logger.error("User not found for admin privileges")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to grant admin privileges: {str(e)}")
            return False
        
        logger.info(f"Test user created successfully: {self.test_user.email} (ID: {self.test_user.user_id})")
        return True
    
    async def create_test_goals(self) -> bool:
        """Create test goals: one perpetual and one 2-week goal"""
        logger.info("Creating test goals...")
        
        # Create perpetual goal
        perpetual_goal_data = {
            "name": "Daily Reading - Perpetual Goal",
            "goal_type": "checklist",
            "duration": "long_term",
            "target_value": 1
        }
        
        response = await self.make_request("POST", "/api/v1/goals", perpetual_goal_data)
        if "error" in response:
            logger.error(f"Failed to create perpetual goal: {response}")
            return False
        
        perpetual_goal = TestGoal(
            id=response.get("id"),
            name=response.get("name"),
            goal_type=response.get("goal_type"),
            duration=response.get("duration"),
            target_value=response.get("target_value")
        )
        self.test_goals.append(perpetual_goal)
        
        # Create 2-week goal
        two_week_goal_data = {
            "name": "Exercise 10 Times - 2 Week Goal",
            "goal_type": "counter",
            "duration": "two_week",
            "target_value": 10
        }
        
        response = await self.make_request("POST", "/api/v1/goals", two_week_goal_data)
        if "error" in response:
            logger.error(f"Failed to create 2-week goal: {response}")
            return False
        
        two_week_goal = TestGoal(
            id=response.get("id"),
            name=response.get("name"),
            goal_type=response.get("goal_type"),
            duration=response.get("duration"),
            target_value=response.get("target_value"),
            expires_at=response.get("expires_at")
        )
        self.test_goals.append(two_week_goal)
        
        logger.info(f"Created {len(self.test_goals)} test goals successfully")
        return True
    
    async def create_test_habits(self) -> bool:
        """Create test habits for streak tracking"""
        logger.info("Creating test habits...")
        
        habit_names = [
            "Morning Meditation",
            "Daily Exercise",
            "Read for 30 minutes"
        ]
        
        for habit_name in habit_names:
            habit_data = {
                "name": habit_name,
                "is_favorite": False
            }
            
            response = await self.make_request("POST", "/api/v1/habits", habit_data)
            if "error" in response:
                logger.error(f"Failed to create habit '{habit_name}': {response}")
                continue
            
            habit = TestHabit(
                id=response.get("id"),
                name=response.get("name"),
                streak=response.get("streak", 0),
                is_favorite=response.get("is_favorite", False)
            )
            self.test_habits.append(habit)
        
        logger.info(f"Created {len(self.test_habits)} test habits successfully")
        return True
    
    async def record_daily_mood(self) -> bool:
        """Record daily mood entry"""
        logger.info("Recording daily mood...")
        
        mood_data = {
            "happiness": 4,
            "focus": 4,
            "stress": 2
        }
        
        response = await self.make_request("POST", "/api/v1/mood/today", mood_data)
        if "error" in response:
            logger.error(f"Failed to record mood: {response}")
            return False
        
        logger.info("Daily mood recorded successfully")
        return True
    
    async def complete_daily_goals(self) -> bool:
        """Complete daily goals"""
        logger.info("Completing daily goals...")
        
        success_count = 0
        for goal in self.test_goals:
            if goal.goal_type == "checklist":
                # Complete checklist goal
                progress_data = {"complete": True}
                response = await self.make_request("PATCH", f"/api/v1/goals/{goal.id}/progress", progress_data)
                if "error" not in response:
                    success_count += 1
                    logger.info(f"Completed checklist goal: {goal.name}")
            
            elif goal.goal_type == "counter":
                # Increment counter goal
                progress_data = {"increment": 1}
                response = await self.make_request("PATCH", f"/api/v1/goals/{goal.id}/progress", progress_data)
                if "error" not in response:
                    success_count += 1
                    logger.info(f"Incremented counter goal: {goal.name}")
        
        logger.info(f"Completed {success_count}/{len(self.test_goals)} goals")
        return success_count > 0
    
    async def complete_daily_habits(self) -> Dict[str, int]:
        """Complete daily habits and return current streak values"""
        logger.info("Completing daily habits...")
        
        # Get current date from the application
        current_time_response = await self.make_request("GET", "/api/v1/time/current")
        if "error" in current_time_response:
            logger.error(f"Failed to get current time: {current_time_response}")
            return {}
        
        current_date = current_time_response.get("user_date")
        if not current_date:
            logger.error("No current date found in time response")
            return {}
        
        streak_values = {}
        for habit in self.test_habits:
            # Mark habit as completed for today using correct API format
            completion_data = {
                "habit_id": habit.id,
                "date": current_date,
                "completed": True
            }
            response = await self.make_request("POST", "/api/v1/habits/completions", completion_data)
            
            if "error" not in response:
                # Get updated habit info to check streak
                habit_response = await self.make_request("GET", f"/api/v1/habits/{habit.id}")
                if "error" not in habit_response:
                    current_streak = habit_response.get("streak", 0)
                    streak_values[habit.name] = current_streak
                    logger.info(f"Completed habit '{habit.name}' - Current streak: {current_streak}")
                else:
                    logger.error(f"Failed to get updated habit info: {habit_response}")
            else:
                logger.error(f"Failed to complete habit '{habit.name}': {response}")
        
        return streak_values
    
    async def advance_time_by_24_hours(self) -> bool:
        """Advance application time by 24 hours using mock time endpoint"""
        logger.info("Advancing time by 24 hours...")
        
        # Get current time
        current_time_response = await self.make_request("GET", "/api/v1/time/current")
        if "error" in current_time_response:
            logger.error(f"Failed to get current time: {current_time_response}")
            return False
        
        current_time_str = current_time_response.get("user_datetime")
        if not current_time_str:
            logger.error("No current time found in response")
            return False
        
        # Parse current time and add 24 hours
        try:
            current_time = datetime.fromisoformat(current_time_str.replace('Z', '+00:00'))
            new_time = current_time + timedelta(hours=24)
            new_time_str = new_time.isoformat()
            
            # Set new mock time
            time_data = {"new_datetime": new_time_str}
            response = await self.make_request("POST", "/api/v1/time/debug/set-date", time_data)
            
            if "error" in response:
                logger.error(f"Failed to set mock time: {response}")
                return False
            
            logger.info(f"Time advanced successfully to: {new_time_str}")
            return True
            
        except Exception as e:
            logger.error(f"Error advancing time: {str(e)}")
            return False
    
    async def verify_data_state(self, day: int) -> bool:
        """Verify that data state is correct for the current day"""
        logger.info(f"Verifying data state for day {day}...")
        
        # Check that goals are still accessible
        goals_response = await self.make_request("GET", "/api/v1/goals")
        if "error" in goals_response:
            logger.error(f"Failed to get goals: {goals_response}")
            return False
        
        # Check that mood data is accessible
        mood_response = await self.make_request("GET", "/api/v1/mood/entries")
        if "error" in mood_response:
            logger.error(f"Failed to get mood entries: {mood_response}")
            return False
        
        # Check that habits are accessible
        habits_response = await self.make_request("GET", "/api/v1/habits")
        if "error" in habits_response:
            logger.error(f"Failed to get habits: {habits_response}")
            return False
        
        logger.info("Data state verification passed")
        return True
    
    async def run_daily_cycle(self, day: int) -> DailyTestResults:
        """Run a complete daily testing cycle"""
        logger.info(f"=== Starting Day {day} Testing Cycle ===")
        
        # Get current date for logging
        current_time_response = await self.make_request("GET", "/api/v1/time/current")
        current_date = current_time_response.get("user_date", "unknown") if "error" not in current_time_response else "unknown"
        
        # Initialize daily results
        results = DailyTestResults(
            day=day,
            date=current_date,
            user_authenticated=False,
            goals_created=False,
            mood_recorded=False,
            habit_completed=False,
            streak_incremented=False,
            time_advanced=False,
            errors=[],
            streak_values={}
        )
        
        try:
            # Verify user authentication
            auth_response = await self.make_request("GET", "/api/v1/auth/me")
            results.user_authenticated = "error" not in auth_response
            
            # Record daily mood
            results.mood_recorded = await self.record_daily_mood()
            
            # Complete daily goals
            results.goals_created = await self.complete_daily_goals()
            
            # Complete daily habits and get streak values
            results.streak_values = await self.complete_daily_habits()
            results.habit_completed = len(results.streak_values) > 0
            
            # Check if any streaks incremented
            if day > 1:
                previous_results = self.daily_results[-1]  # Get previous day's results
                for habit_name, current_streak in results.streak_values.items():
                    previous_streak = previous_results.streak_values.get(habit_name, 0)
                    if current_streak > previous_streak:
                        results.streak_incremented = True
                        break
            else:
                # First day, any streak > 0 means it incremented
                results.streak_incremented = any(streak > 0 for streak in results.streak_values.values())
            
            # Verify data state
            data_state_ok = await self.verify_data_state(day)
            if not data_state_ok:
                results.errors.append("Data state verification failed")
            
            # Advance time by 24 hours (except on last day)
            if day < 10:
                results.time_advanced = await self.advance_time_by_24_hours()
                if not results.time_advanced:
                    results.errors.append("Failed to advance time")
            
        except Exception as e:
            error_msg = f"Daily cycle error: {str(e)}"
            logger.error(error_msg)
            results.errors.append(error_msg)
        
        # Log daily results
        logger.info(f"Day {day} Results:")
        logger.info(f"  Date: {results.date}")
        logger.info(f"  User Authenticated: {results.user_authenticated}")
        logger.info(f"  Mood Recorded: {results.mood_recorded}")
        logger.info(f"  Goals Completed: {results.goals_created}")
        logger.info(f"  Habits Completed: {results.habit_completed}")
        logger.info(f"  Streak Incremented: {results.streak_incremented}")
        logger.info(f"  Time Advanced: {results.time_advanced}")
        logger.info(f"  Streak Values: {results.streak_values}")
        if results.errors:
            logger.info(f"  Errors: {results.errors}")
        
        self.daily_results.append(results)
        return results
    
    async def run_10_day_simulation(self) -> bool:
        """Run the complete 10-day simulation"""
        logger.info("=== Starting 10-Day Application Simulation ===")
        self.start_time = datetime.now()
        
        # Setup phase
        logger.info("=== SETUP PHASE ===")
        
        # Create test user
        if not await self.create_test_user():
            logger.error("Failed to create test user")
            return False
        
        # Create test goals
        if not await self.create_test_goals():
            logger.error("Failed to create test goals")
            return False
        
        # Create test habits
        if not await self.create_test_habits():
            logger.error("Failed to create test habits")
            return False
        
        # Testing phase - Run 10 consecutive days
        logger.info("=== TESTING PHASE ===")
        
        for day in range(1, 11):
            try:
                await self.run_daily_cycle(day)
                
                # Add small delay between days
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Critical error on day {day}: {str(e)}")
                return False
        
        logger.info("=== 10-Day Simulation Completed ===")
        return True
    
    def analyze_results(self) -> Dict[str, Any]:
        """Analyze the test results and identify issues"""
        logger.info("=== Analyzing Test Results ===")
        
        analysis = {
            "summary": {
                "total_days": len(self.daily_results),
                "successful_days": 0,
                "failed_days": 0,
                "total_errors": 0
            },
            "authentication": {
                "success_rate": 0.0,
                "failures": []
            },
            "mood_tracking": {
                "success_rate": 0.0,
                "failures": []
            },
            "goal_completion": {
                "success_rate": 0.0,
                "failures": []
            },
            "habit_tracking": {
                "success_rate": 0.0,
                "failures": []
            },
            "streak_tracking": {
                "success_rate": 0.0,
                "failures": [],
                "streak_progression": {}
            },
            "time_advancement": {
                "success_rate": 0.0,
                "failures": []
            },
            "identified_issues": []
        }
        
        # Analyze each day's results
        for day_result in self.daily_results:
            # Count successful vs failed days
            if not day_result.errors:
                analysis["summary"]["successful_days"] += 1
            else:
                analysis["summary"]["failed_days"] += 1
                analysis["summary"]["total_errors"] += len(day_result.errors)
            
            # Analyze authentication
            if not day_result.user_authenticated:
                analysis["authentication"]["failures"].append(f"Day {day_result.day}")
            
            # Analyze mood tracking
            if not day_result.mood_recorded:
                analysis["mood_tracking"]["failures"].append(f"Day {day_result.day}")
            
            # Analyze goal completion
            if not day_result.goals_created:
                analysis["goal_completion"]["failures"].append(f"Day {day_result.day}")
            
            # Analyze habit tracking
            if not day_result.habit_completed:
                analysis["habit_tracking"]["failures"].append(f"Day {day_result.day}")
            
            # Analyze streak tracking
            if not day_result.streak_incremented and day_result.day > 1:
                analysis["streak_tracking"]["failures"].append(f"Day {day_result.day}")
            
            # Analyze time advancement
            if day_result.day < 10 and not day_result.time_advanced:
                analysis["time_advancement"]["failures"].append(f"Day {day_result.day}")
        
        # Calculate success rates
        total_days = len(self.daily_results)
        if total_days > 0:
            analysis["authentication"]["success_rate"] = (total_days - len(analysis["authentication"]["failures"])) / total_days * 100
            analysis["mood_tracking"]["success_rate"] = (total_days - len(analysis["mood_tracking"]["failures"])) / total_days * 100
            analysis["goal_completion"]["success_rate"] = (total_days - len(analysis["goal_completion"]["failures"])) / total_days * 100
            analysis["habit_tracking"]["success_rate"] = (total_days - len(analysis["habit_tracking"]["failures"])) / total_days * 100
            analysis["streak_tracking"]["success_rate"] = (total_days - len(analysis["streak_tracking"]["failures"])) / total_days * 100
            analysis["time_advancement"]["success_rate"] = ((total_days - 1) - len(analysis["time_advancement"]["failures"])) / (total_days - 1) * 100 if total_days > 1 else 100
        
        # Analyze streak progression
        for habit in self.test_habits:
            habit_name = habit.name
            progression = []
            for day_result in self.daily_results:
                streak_value = day_result.streak_values.get(habit_name, 0)
                progression.append(streak_value)
            analysis["streak_tracking"]["streak_progression"][habit_name] = progression
        
        # Identify specific issues
        if analysis["authentication"]["success_rate"] < 100:
            analysis["identified_issues"].append("Authentication failures detected")
        
        if analysis["mood_tracking"]["success_rate"] < 100:
            analysis["identified_issues"].append("Mood tracking failures detected")
        
        if analysis["goal_completion"]["success_rate"] < 100:
            analysis["identified_issues"].append("Goal completion failures detected")
        
        if analysis["habit_tracking"]["success_rate"] < 100:
            analysis["identified_issues"].append("Habit tracking failures detected")
        
        if analysis["streak_tracking"]["success_rate"] < 100:
            analysis["identified_issues"].append("Streak tracking failures detected")
        
        if analysis["time_advancement"]["success_rate"] < 100:
            analysis["identified_issues"].append("Time advancement failures detected")
        
        # Check for streak consistency
        for habit_name, progression in analysis["streak_tracking"]["streak_progression"].items():
            for i in range(1, len(progression)):
                if progression[i] != progression[i-1] + 1:
                    analysis["identified_issues"].append(f"Streak inconsistency in '{habit_name}' between day {i} and {i+1}")
        
        return analysis
    
    def generate_report(self, analysis: Dict[str, Any]) -> str:
        """Generate a comprehensive test report"""
        report = []
        report.append("=" * 80)
        report.append("10-DAY APPLICATION TESTING REPORT")
        report.append("=" * 80)
        report.append("")
        
        # Summary
        report.append("SUMMARY")
        report.append("-" * 40)
        report.append(f"Total Days Tested: {analysis['summary']['total_days']}")
        report.append(f"Successful Days: {analysis['summary']['successful_days']}")
        report.append(f"Failed Days: {analysis['summary']['failed_days']}")
        report.append(f"Total Errors: {analysis['summary']['total_errors']}")
        report.append("")
        
        # Feature Analysis
        report.append("FEATURE ANALYSIS")
        report.append("-" * 40)
        report.append(f"Authentication Success Rate: {analysis['authentication']['success_rate']:.1f}%")
        report.append(f"Mood Tracking Success Rate: {analysis['mood_tracking']['success_rate']:.1f}%")
        report.append(f"Goal Completion Success Rate: {analysis['goal_completion']['success_rate']:.1f}%")
        report.append(f"Habit Tracking Success Rate: {analysis['habit_tracking']['success_rate']:.1f}%")
        report.append(f"Streak Tracking Success Rate: {analysis['streak_tracking']['success_rate']:.1f}%")
        report.append(f"Time Advancement Success Rate: {analysis['time_advancement']['success_rate']:.1f}%")
        report.append("")
        
        # Streak Progression
        report.append("STREAK PROGRESSION")
        report.append("-" * 40)
        for habit_name, progression in analysis['streak_tracking']['streak_progression'].items():
            report.append(f"{habit_name}: {progression}")
        report.append("")
        
        # Identified Issues
        report.append("IDENTIFIED ISSUES")
        report.append("-" * 40)
        if analysis['identified_issues']:
            for issue in analysis['identified_issues']:
                report.append(f"• {issue}")
        else:
            report.append("No issues identified - all tests passed!")
        report.append("")
        
        # Daily Results Log
        report.append("DAILY RESULTS LOG")
        report.append("-" * 40)
        for day_result in self.daily_results:
            report.append(f"Day {day_result.day} ({day_result.date}):")
            report.append(f"  Auth: {day_result.user_authenticated}, Mood: {day_result.mood_recorded}, Goals: {day_result.goals_created}")
            report.append(f"  Habits: {day_result.habit_completed}, Streak+: {day_result.streak_incremented}, Time+: {day_result.time_advanced}")
            report.append(f"  Streaks: {day_result.streak_values}")
            if day_result.errors:
                report.append(f"  Errors: {day_result.errors}")
            report.append("")
        
        report.append("=" * 80)
        
        return "\n".join(report)

async def main():
    """Main function to run the 10-day simulation"""
    logger.info("Starting 10-Day Application Testing")
    
    # Configuration
    base_url = os.getenv("APP_BASE_URL", "http://localhost:8000")
    
    async with ApplicationTester(base_url) as tester:
        # Run the simulation
        success = await tester.run_10_day_simulation()
        
        if not success:
            logger.error("10-day simulation failed")
            sys.exit(1)
        
        # Analyze results
        analysis = tester.analyze_results()
        
        # Generate report
        report = tester.generate_report(analysis)
        
        # Output report
        print("\n")
        print(report)
        
        # Save report to file
        with open("test_report.txt", "w") as f:
            f.write(report)
        
        logger.info("Test report saved to test_report.txt")
        
        # Exit with error code if issues were found
        if analysis['identified_issues']:
            logger.error(f"Testing completed with {len(analysis['identified_issues'])} issues found")
            sys.exit(1)
        else:
            logger.info("Testing completed successfully - no issues found")
            sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main()) 