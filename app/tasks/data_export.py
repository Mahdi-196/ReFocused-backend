"""
Background tasks for user data export.
Handles asynchronous data aggregation and export file generation.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from pathlib import Path

from app.db.database import async_session
from app.db.models import (
    User, Goal2Week, GoalLongTerm, Habit, HabitCompletion, HabitStreak,
    MoodEntry, PomodoroSettings, StudySet, Flashcard, Mantra,
    JournalCollection, JournalEntry, Gratitude, UserStatistics,
    CalendarEntry, CalendarHabitCompletion, CalendarMoodEntry, QuickAccess
)
from sqlalchemy import select
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

class DataExportTask:
    """Handles comprehensive user data export with human-readable structure."""

    @staticmethod
    async def aggregate_user_data(user_id: int) -> Dict[str, Any]:
        """
        Aggregate all user data into a comprehensive, human-readable structure.
        
        Returns:
            Dictionary containing all user data organized logically for export
        """
        async with async_session() as db:
            # Get user info
            user_result = await db.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if not user:
                raise ValueError(f"User {user_id} not found")
            
            # Build comprehensive data structure
            export_data = {
                "export_metadata": {
                    "export_date": datetime.utcnow().isoformat(),
                    "format_version": "1.0",
                    "user_id": user_id,
                    "description": "Complete user data export from ReFocused application"
                },
                
                "account_information": {
                    "user_id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "account_created": user.created_at.isoformat() if user.created_at else None,
                    "last_login": user.last_login.isoformat() if user.last_login else None,
                    "timezone": user.timezone,
                    "timezone_detection_method": user.timezone_detected_method,
                    "auth_provider": user.auth_provider,
                    "profile_picture": user.profile_picture,
                    "is_active": user.is_active
                },
                
                "user_data": {},
                "personal_content": {},
                "activity_history": {},
                "settings_and_preferences": {}
            }
            
            # Goals Data
            goals_data = await DataExportTask._aggregate_goals_data(db, user_id)
            export_data["user_data"]["goals"] = goals_data
            
            # Habits Data
            habits_data = await DataExportTask._aggregate_habits_data(db, user_id)
            export_data["user_data"]["habits"] = habits_data
            
            # Mood Tracking Data
            mood_data = await DataExportTask._aggregate_mood_data(db, user_id)
            export_data["activity_history"]["mood_tracking"] = mood_data
            
            # Journal Data
            journal_data = await DataExportTask._aggregate_journal_data(db, user_id)
            export_data["personal_content"]["journaling"] = journal_data
            
            # Study Data
            study_data = await DataExportTask._aggregate_study_data(db, user_id)
            export_data["user_data"]["study_materials"] = study_data
            
            # Personal Content
            personal_data = await DataExportTask._aggregate_personal_content(db, user_id)
            export_data["personal_content"].update(personal_data)
            
            # Statistics and Analytics
            stats_data = await DataExportTask._aggregate_statistics_data(db, user_id)
            export_data["activity_history"]["statistics"] = stats_data
            
            # Settings and Preferences
            settings_data = await DataExportTask._aggregate_settings_data(db, user_id)
            export_data["settings_and_preferences"] = settings_data
            
            # Calendar Data
            calendar_data = await DataExportTask._aggregate_calendar_data(db, user_id)
            export_data["activity_history"]["calendar"] = calendar_data
            
            return export_data

    @staticmethod
    async def _aggregate_goals_data(db, user_id: int) -> Dict[str, Any]:
        """Aggregate goals data with clear categorization."""
        # 2-week goals
        goals_2week_result = await db.execute(
            select(Goal2Week).where(Goal2Week.user_id == user_id)
            .order_by(Goal2Week.created_at.desc())
        )
        goals_2week = goals_2week_result.scalars().all()
        
        # Long-term goals
        goals_longterm_result = await db.execute(
            select(GoalLongTerm).where(GoalLongTerm.user_id == user_id)
            .order_by(GoalLongTerm.created_at.desc())
        )
        goals_longterm = goals_longterm_result.scalars().all()
        
        return {
            "summary": {
                "total_2week_goals": len(goals_2week),
                "total_longterm_goals": len(goals_longterm),
                "completed_2week_goals": len([g for g in goals_2week if g.is_completed]),
                "completed_longterm_goals": len([g for g in goals_longterm if g.is_completed])
            },
            "two_week_goals": [
                {
                    "id": goal.id,
                    "name": goal.name,
                    "type": goal.goal_type,
                    "target_value": goal.target_value,
                    "current_value": goal.current_value,
                    "progress_percentage": goal.progress_percentage,
                    "is_completed": goal.is_completed,
                    "created_date": goal.created_at.isoformat(),
                    "expires_date": goal.expires_at.isoformat(),
                    "completed_date": goal.completed_at.isoformat() if goal.completed_at else None
                }
                for goal in goals_2week
            ],
            "long_term_goals": [
                {
                    "id": goal.id,
                    "name": goal.name,
                    "type": goal.goal_type,
                    "target_value": goal.target_value,
                    "current_value": goal.current_value,
                    "progress_percentage": goal.progress_percentage,
                    "is_completed": goal.is_completed,
                    "created_date": goal.created_at.isoformat(),
                    "completed_date": goal.completed_at.isoformat() if goal.completed_at else None
                }
                for goal in goals_longterm
            ]
        }

    @staticmethod
    async def _aggregate_habits_data(db, user_id: int) -> Dict[str, Any]:
        """Aggregate habits data with completion history."""
        # Get habits with completions
        habits_result = await db.execute(
            select(Habit).where(Habit.user_id == user_id)
            .options(selectinload(Habit.completions))
            .order_by(Habit.created_at.desc())
        )
        habits = habits_result.scalars().all()
        
        habits_export = []
        for habit in habits:
            habit_data = {
                "id": habit.id,
                "name": habit.name,
                "is_favorite": habit.is_favorite,
                "is_active": habit.is_active,
                "current_streak": habit.streak,
                "created_date": habit.created_at.isoformat(),
                "last_updated": habit.last_updated_utc.isoformat(),
                "completion_history": [
                    {
                        "date": comp.date.isoformat(),
                        "completed": comp.completed,
                        "completed_at": comp.completed_at.isoformat() if comp.completed_at else None,
                        "timezone": comp.timezone
                    }
                    for comp in sorted(habit.completions, key=lambda x: x.date, reverse=True)
                ]
            }
            habits_export.append(habit_data)
        
        return {
            "summary": {
                "total_habits": len(habits),
                "active_habits": len([h for h in habits if h.is_active]),
                "favorite_habits": len([h for h in habits if h.is_favorite]),
                "average_streak": sum(h.streak for h in habits) / len(habits) if habits else 0
            },
            "habits": habits_export
        }

    @staticmethod
    async def _aggregate_mood_data(db, user_id: int) -> Dict[str, Any]:
        """Aggregate mood tracking data with trends."""
        mood_result = await db.execute(
            select(MoodEntry).where(MoodEntry.user_id == user_id)
            .order_by(MoodEntry.entry_date.desc())
        )
        mood_entries = mood_result.scalars().all()
        
        return {
            "summary": {
                "total_entries": len(mood_entries),
                "date_range": {
                    "first_entry": mood_entries[-1].entry_date.isoformat() if mood_entries else None,
                    "latest_entry": mood_entries[0].entry_date.isoformat() if mood_entries else None
                },
                "averages": {
                    "happiness": sum(m.happiness for m in mood_entries) / len(mood_entries) if mood_entries else 0,
                    "focus": sum(m.focus for m in mood_entries) / len(mood_entries) if mood_entries else 0,
                    "stress": sum(m.stress for m in mood_entries) / len(mood_entries) if mood_entries else 0
                }
            },
            "daily_entries": [
                {
                    "date": entry.entry_date.isoformat(),
                    "happiness_rating": entry.happiness,
                    "focus_rating": entry.focus,
                    "stress_rating": entry.stress,
                    "recorded_at": entry.created_at.isoformat()
                }
                for entry in mood_entries
            ]
        }

    @staticmethod
    async def _aggregate_journal_data(db, user_id: int) -> Dict[str, Any]:
        """Aggregate journal data with collections and entries."""
        # Get journal collections with entries
        collections_result = await db.execute(
            select(JournalCollection).where(JournalCollection.user_id == user_id)
            .options(selectinload(JournalCollection.entries))
            .order_by(JournalCollection.created_at.desc())
        )
        collections = collections_result.scalars().all()
        
        # Get gratitude entries
        gratitude_result = await db.execute(
            select(Gratitude).where(Gratitude.user_id == user_id)
            .order_by(Gratitude.date.desc())
        )
        gratitude_entries = gratitude_result.scalars().all()
        
        collections_export = []
        for collection in collections:
            collection_data = {
                "id": collection.id,
                "name": collection.name,
                "is_private": collection.is_private,
                "created_date": collection.created_at.isoformat(),
                "updated_date": collection.updated_at.isoformat(),
                "entries": [
                    {
                        "id": entry.id,
                        "title": entry.title,
                        "content": entry.content if not entry.is_encrypted else "[ENCRYPTED - Content protected]",
                        "is_encrypted": entry.is_encrypted,
                        "created_date": entry.created_at.isoformat(),
                        "updated_date": entry.updated_at.isoformat()
                    }
                    for entry in sorted(collection.entries, key=lambda x: x.created_at, reverse=True)
                ]
            }
            collections_export.append(collection_data)
        
        return {
            "journal_collections": {
                "summary": {
                    "total_collections": len(collections),
                    "private_collections": len([c for c in collections if c.is_private]),
                    "total_entries": sum(len(c.entries) for c in collections)
                },
                "collections": collections_export
            },
            "gratitude_entries": {
                "summary": {
                    "total_entries": len(gratitude_entries)
                },
                "entries": [
                    {
                        "date": entry.date.isoformat(),
                        "text": entry.text,
                        "created_at": entry.created_at.isoformat()
                    }
                    for entry in gratitude_entries
                ]
            }
        }

    @staticmethod
    async def _aggregate_study_data(db, user_id: int) -> Dict[str, Any]:
        """Aggregate study materials and flashcards."""
        study_sets_result = await db.execute(
            select(StudySet).where(StudySet.user_id == user_id)
            .options(selectinload(StudySet.flashcards))
            .order_by(StudySet.created_at.desc())
        )
        study_sets = study_sets_result.scalars().all()
        
        sets_export = []
        for study_set in study_sets:
            set_data = {
                "id": study_set.id,
                "title": study_set.title,
                "created_date": study_set.created_at.isoformat(),
                "flashcards": [
                    {
                        "id": card.id,
                        "question": card.question,
                        "answer": card.answer,
                        "created_date": card.created_at.isoformat()
                    }
                    for card in sorted(study_set.flashcards, key=lambda x: x.created_at)
                ]
            }
            sets_export.append(set_data)
        
        return {
            "summary": {
                "total_study_sets": len(study_sets),
                "total_flashcards": sum(len(s.flashcards) for s in study_sets)
            },
            "study_sets": sets_export
        }

    @staticmethod
    async def _aggregate_personal_content(db, user_id: int) -> Dict[str, Any]:
        """Aggregate mantras and personal content."""
        mantras_result = await db.execute(
            select(Mantra).where(Mantra.user_id == user_id)
            .order_by(Mantra.created_at.desc())
        )
        mantras = mantras_result.scalars().all()
        
        quick_access_result = await db.execute(
            select(QuickAccess).where(QuickAccess.user_id == user_id)
            .order_by(QuickAccess.created_at.desc())
        )
        quick_access_items = quick_access_result.scalars().all()
        
        return {
            "mantras": [
                {
                    "id": mantra.id,
                    "text": mantra.text,
                    "created_date": mantra.created_at.isoformat()
                }
                for mantra in mantras
            ],
            "quick_access_links": [
                {
                    "id": item.id,
                    "name": item.name,
                    "target_url": item.target_url,
                    "created_date": item.created_at.isoformat()
                }
                for item in quick_access_items
            ]
        }

    @staticmethod
    async def _aggregate_statistics_data(db, user_id: int) -> Dict[str, Any]:
        """Aggregate user statistics and analytics."""
        stats_result = await db.execute(
            select(UserStatistics).where(UserStatistics.user_id == user_id)
            .order_by(UserStatistics.date.desc())
        )
        statistics = stats_result.scalars().all()
        
        return {
            "summary": {
                "total_recorded_days": len(statistics),
                "total_focus_time_minutes": sum(s.focus_time_minutes for s in statistics),
                "total_completed_sessions": sum(s.completed_sessions for s in statistics),
                "total_completed_tasks": sum(s.completed_tasks for s in statistics)
            },
            "daily_statistics": [
                {
                    "date": stat.date.isoformat(),
                    "focus_time_minutes": stat.focus_time_minutes,
                    "completed_sessions": stat.completed_sessions,
                    "completed_tasks": stat.completed_tasks,
                    "recorded_at": stat.created_at.isoformat()
                }
                for stat in statistics
            ]
        }

    @staticmethod
    async def _aggregate_settings_data(db, user_id: int) -> Dict[str, Any]:
        """Aggregate user settings and preferences."""
        pomodoro_result = await db.execute(
            select(PomodoroSettings).where(PomodoroSettings.user_id == user_id)
        )
        pomodoro_settings = pomodoro_result.scalar_one_or_none()
        
        return {
            "pomodoro_settings": {
                "work_minutes": pomodoro_settings.work_minutes if pomodoro_settings else None,
                "break_minutes": pomodoro_settings.break_minutes if pomodoro_settings else None,
                "long_break_minutes": pomodoro_settings.long_break_minutes if pomodoro_settings else None,
                "sessions_before_long": pomodoro_settings.sessions_before_long if pomodoro_settings else None,
                "last_updated": pomodoro_settings.updated_at.isoformat() if pomodoro_settings else None
            }
        }

    @staticmethod
    async def _aggregate_calendar_data(db, user_id: int) -> Dict[str, Any]:
        """Aggregate calendar entries and historical data."""
        calendar_result = await db.execute(
            select(CalendarEntry).where(CalendarEntry.user_id == user_id)
            .options(
                selectinload(CalendarEntry.habit_completions),
                selectinload(CalendarEntry.mood_entry)
            )
            .order_by(CalendarEntry.date.desc())
        )
        calendar_entries = calendar_result.scalars().all()
        
        entries_export = []
        for entry in calendar_entries:
            entry_data = {
                "date": entry.date.isoformat(),
                "notes": entry.notes,
                "is_locked": entry.is_locked,
                "created_date": entry.created_at.isoformat(),
                "updated_date": entry.updated_at.isoformat(),
                "habit_completions": [
                    {
                        "habit_id": comp.habit_id,
                        "habit_name": comp.habit_name,
                        "completed": comp.completed,
                        "completed_at": comp.completed_at.isoformat() if comp.completed_at else None,
                        "was_active_on_date": comp.was_active_on_date
                    }
                    for comp in entry.habit_completions
                ],
                "mood_entry": {
                    "happiness": entry.mood_entry.happiness,
                    "focus": entry.mood_entry.focus,
                    "stress": entry.mood_entry.stress,
                    "day_rating": entry.mood_entry.day_rating
                } if entry.mood_entry else None
            }
            entries_export.append(entry_data)
        
        return {
            "summary": {
                "total_calendar_entries": len(calendar_entries),
                "locked_entries": len([e for e in calendar_entries if e.is_locked])
            },
            "calendar_entries": entries_export
        }

    @staticmethod
    async def create_export_file(user_id: int, export_data: Dict[str, Any]) -> str:
        """
        Create a formatted JSON export file.
        
        Returns:
            Path to the created export file
        """
        # Create exports directory if it doesn't exist
        export_dir = Path("exports")
        export_dir.mkdir(exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"user_{user_id}_data_export_{timestamp}.json"
        file_path = export_dir / filename
        
        # Write formatted JSON
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"Export file created: {file_path}")
        return str(file_path)


# Synchronous export function for background processing
def export_user_data_sync(user_id: int) -> Dict[str, Any]:
    """
    Synchronous function to export user data.
    Uses subprocess to run async code in isolation.
    
    Args:
        user_id: ID of the user whose data should be exported
        
    Returns:
        Dictionary with export results and file path
    """
    try:
        import subprocess
        import sys
        import tempfile
        
        # Create a temporary script to run the async export
        script_content = f'''
import asyncio
import json
import sys
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, "{Path(__file__).parent.parent}")

from app.tasks.data_export import DataExportTask

async def run_export():
    try:
        export_data = await DataExportTask.aggregate_user_data({user_id})
        file_path = await DataExportTask.create_export_file({user_id}, export_data)
        
        result = {{
            "success": True,
            "user_id": {user_id},
            "file_path": file_path,
            "export_date": export_data["export_metadata"]["export_date"],
            "data_summary": {{
                "total_goals": (
                    len(export_data["user_data"]["goals"]["two_week_goals"]) +
                    len(export_data["user_data"]["goals"]["long_term_goals"])
                ),
                "total_habits": len(export_data["user_data"]["habits"]["habits"]),
                "total_mood_entries": len(export_data["activity_history"]["mood_tracking"]["daily_entries"]),
                "total_journal_entries": export_data["personal_content"]["journaling"]["journal_collections"]["summary"]["total_entries"],
                "total_study_sets": len(export_data["user_data"]["study_materials"]["study_sets"])
            }}
        }}
        
        print(json.dumps(result))
        
    except Exception as e:
        error_result = {{
            "success": False,
            "error": str(e),
            "user_id": {user_id}
        }}
        print(json.dumps(error_result))

if __name__ == "__main__":
    asyncio.run(run_export())
'''
        
        # Write script to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(script_content)
            script_path = f.name
        
        try:
            # Run the script in a subprocess
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=60  # 60 second timeout
            )
            
            if result.returncode == 0:
                return json.loads(result.stdout.strip())
            else:
                raise Exception(f"Export subprocess failed: {result.stderr}")
                
        finally:
            # Clean up temp file
            Path(script_path).unlink(missing_ok=True)
            
    except Exception as e:
        logger.error(f"Sync export failed for user {user_id}: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "user_id": user_id
        }


# Celery task function - imported dynamically to avoid import issues
def export_user_data_task_function(user_id: int) -> Dict[str, Any]:
    """
    Function to export user data asynchronously.
    This will be wrapped as a Celery task in celery_worker.py
    
    Args:
        user_id: ID of the user whose data should be exported
        
    Returns:
        Dictionary with export results and file path
    """
    try:
        # Always use synchronous approach for background threads
        return export_user_data_sync(user_id)
            
    except Exception as e:
        logger.error(f"Export task failed for user {user_id}: {str(e)}")
        raise e