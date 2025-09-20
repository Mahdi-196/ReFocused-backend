"""
Export service for handling data export functionality.
Provides synchronous data export operations using direct database queries.
"""
import logging
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ExportService:
    """Service for managing user data exports."""
    
    # Simple in-memory storage for development (use proper storage in production)
    _results_cache: Dict[str, Dict[str, Any]] = {}
    
    @staticmethod
    def initiate_export(user_id: int) -> Dict[str, Any]:
        """
        Initiate a synchronous data export for a user.
        
        Args:
            user_id: ID of the user to export data for
            
        Returns:
            Dictionary with export results
            
        Raises:
            Exception: If export cannot be completed
        """
        try:
            # Generate a task ID for tracking
            task_id = str(uuid.uuid4())
            
            # Perform synchronous data export
            result = ExportService._export_user_data(user_id, task_id)
            
            # Store result
            ExportService._store_result(task_id, result)
            
            return {
                "task_id": task_id,
                "status": "completed",
                "service": "synchronous",
                "result": result
            }
            
        except Exception as e:
            logger.error(f"Export failed for user {user_id}: {e}")
            raise
    
    @staticmethod
    def _export_user_data(user_id: int, task_id: str) -> Dict[str, Any]:
        """
        Export all user data synchronously.
        
        Args:
            user_id: ID of the user to export data for
            task_id: Task ID for tracking
            
        Returns:
            Dictionary with export results
        """
        try:
            # Import synchronous database session
            from app.db.database import sync_session
            from app.db.models import (
                User, Goal2Week, GoalLongTerm, Habit, HabitCompletion,
                MoodEntry, PomodoroSettings, StudySet, Flashcard, Mantra,
                JournalCollection, JournalEntry, Gratitude, UserStatistics,
                CalendarEntry, QuickAccess
            )
            from sqlalchemy.orm import selectinload
            
            # Create database session
            with sync_session() as db:
                # Get user info
                user = db.query(User).filter(User.id == user_id).first()
                if not user:
                    raise ValueError(f"User {user_id} not found")
                
                # Collect all user data
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
                        "timezone": user.timezone,
                        "auth_provider": user.auth_provider,
                        "profile_picture": user.profile_picture,
                        "is_active": user.is_active
                    }
                }
                
                # Goals Data
                goals_2week = db.query(Goal2Week).filter(Goal2Week.user_id == user_id).all()
                goals_longterm = db.query(GoalLongTerm).filter(GoalLongTerm.user_id == user_id).all()
                
                export_data["goals"] = {
                    "summary": {
                        "total_2week_goals": len(goals_2week),
                        "total_longterm_goals": len(goals_longterm),
                        "completed_2week_goals": len([g for g in goals_2week if g.is_completed]),
                        "completed_longterm_goals": len([g for g in goals_longterm if g.is_completed])
                    },
                    "2_week_goals": [
                        {
                            "id": goal.id,
                            "name": goal.name,
                            "goal_type": goal.goal_type,
                            "target_value": goal.target_value,
                            "current_value": goal.current_value,
                            "progress_percentage": goal.progress_percentage,
                            "is_completed": goal.is_completed,
                            "completed_at": goal.completed_at.isoformat() if goal.completed_at else None,
                            "created_at": goal.created_at.isoformat() if goal.created_at else None,
                            "updated_at": goal.updated_at.isoformat() if goal.updated_at else None,
                            "expires_at": goal.expires_at.isoformat() if goal.expires_at else None,
                            "duration": goal.duration
                        }
                        for goal in goals_2week
                    ],
                    "long_term_goals": [
                        {
                            "id": goal.id,
                            "name": goal.name,
                            "goal_type": goal.goal_type,
                            "target_value": goal.target_value,
                            "current_value": goal.current_value,
                            "progress_percentage": goal.progress_percentage,
                            "is_completed": goal.is_completed,
                            "completed_at": goal.completed_at.isoformat() if goal.completed_at else None,
                            "created_at": goal.created_at.isoformat() if goal.created_at else None,
                            "updated_at": goal.updated_at.isoformat() if goal.updated_at else None,
                            "duration": goal.duration
                        }
                        for goal in goals_longterm
                    ]
                }
                
                # Habits Data
                habits = db.query(Habit).filter(Habit.user_id == user_id).all()
                habits_data = []
                
                for habit in habits:
                    completions = db.query(HabitCompletion).filter(HabitCompletion.habit_id == habit.id).all()
                    habits_data.append({
                        "id": habit.id,
                        "name": habit.name,
                        "is_active": habit.is_active,
                        "is_favorite": habit.is_favorite,
                        "streak": habit.streak,
                        "created_at": habit.created_at.isoformat() if habit.created_at else None,
                        "last_updated_utc": habit.last_updated_utc.isoformat() if habit.last_updated_utc else None,
                        "completions": [
                            {
                                "id": comp.id,
                                "date": comp.date.isoformat() if comp.date else None,
                                "completed": comp.completed,
                                "completed_at": comp.completed_at.isoformat() if comp.completed_at else None,
                                "timezone": comp.timezone,
                                "created_at": comp.created_at.isoformat() if comp.created_at else None
                            }
                            for comp in completions
                        ]
                    })
                
                export_data["habits"] = {
                    "summary": {
                        "total_habits": len(habits),
                        "active_habits": len([h for h in habits if h.is_active]),
                        "favorite_habits": len([h for h in habits if h.is_favorite])
                    },
                    "habits": habits_data
                }
                
                # Mood Data
                mood_entries = db.query(MoodEntry).filter(MoodEntry.user_id == user_id).all()
                export_data["mood_tracking"] = {
                    "summary": {
                        "total_entries": len(mood_entries),
                        "averages": {
                            "happiness": sum(m.happiness for m in mood_entries) / len(mood_entries) if mood_entries else 0,
                            "focus": sum(m.focus for m in mood_entries) / len(mood_entries) if mood_entries else 0,
                            "stress": sum(m.stress for m in mood_entries) / len(mood_entries) if mood_entries else 0
                        }
                    },
                    "entries": [
                        {
                            "date": entry.entry_date.isoformat() if entry.entry_date else None,
                            "happiness_rating": entry.happiness,
                            "focus_rating": entry.focus,
                            "stress_rating": entry.stress,
                            "recorded_at": entry.created_at.isoformat() if entry.created_at else None
                        }
                        for entry in mood_entries
                    ]
                }
                
                # Journal Data
                journal_collections = db.query(JournalCollection).filter(JournalCollection.user_id == user_id).all()
                collections_data = []
                total_entries = 0
                
                for collection in journal_collections:
                    entries = db.query(JournalEntry).filter(JournalEntry.collection_id == collection.id).all()
                    total_entries += len(entries)
                    collections_data.append({
                        "id": collection.id,
                        "name": collection.name,
                        "is_private": collection.is_private,
                        "created_at": collection.created_at.isoformat() if collection.created_at else None,
                        "updated_at": collection.updated_at.isoformat() if collection.updated_at else None,
                        "entries": [
                            {
                                "id": entry.id,
                                "title": entry.title,
                                "content": entry.content if not entry.is_encrypted else "[ENCRYPTED CONTENT]",
                                "is_encrypted": entry.is_encrypted,
                                "encrypted_content": "[ENCRYPTED]" if entry.encrypted_content else None,
                                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                                "updated_at": entry.updated_at.isoformat() if entry.updated_at else None
                            }
                            for entry in entries
                        ]
                    })
                
                export_data["journal"] = {
                    "summary": {
                        "total_collections": len(journal_collections),
                        "total_entries": total_entries
                    },
                    "collections": collections_data
                }
                
                # Study Sets Data
                study_sets = db.query(StudySet).filter(StudySet.user_id == user_id).all()
                sets_data = []
                total_flashcards = 0
                
                for study_set in study_sets:
                    flashcards = db.query(Flashcard).filter(Flashcard.set_id == study_set.id).all()
                    total_flashcards += len(flashcards)
                    sets_data.append({
                        "id": study_set.id,
                        "title": study_set.title,
                        "created_at": study_set.created_at.isoformat() if study_set.created_at else None,
                        "flashcards": [
                            {
                                "id": card.id,
                                "question": card.question,
                                "answer": card.answer,
                                "created_at": card.created_at.isoformat() if card.created_at else None
                            }
                            for card in flashcards
                        ]
                    })
                
                export_data["study_materials"] = {
                    "summary": {
                        "total_study_sets": len(study_sets),
                        "total_flashcards": total_flashcards
                    },
                    "study_sets": sets_data
                }
                
                # Personal Content
                mantras = db.query(Mantra).filter(Mantra.user_id == user_id).all()
                quick_access = db.query(QuickAccess).filter(QuickAccess.user_id == user_id).all()
                
                export_data["personal_content"] = {
                    "mantras": [
                        {
                            "id": mantra.id,
                            "text": mantra.text,
                            "created_date": mantra.created_at.isoformat() if mantra.created_at else None
                        }
                        for mantra in mantras
                    ],
                    "quick_access_links": [
                        {
                            "id": item.id,
                            "name": item.name,
                            "target_url": item.target_url,
                            "created_date": item.created_at.isoformat() if item.created_at else None
                        }
                        for item in quick_access
                    ]
                }
                
                # Statistics
                statistics = db.query(UserStatistics).filter(UserStatistics.user_id == user_id).all()
                export_data["statistics"] = {
                    "summary": {
                        "total_recorded_days": len(statistics),
                        "total_focus_time_minutes": sum(s.focus_time_minutes for s in statistics),
                        "total_completed_sessions": sum(s.completed_sessions for s in statistics),
                        "total_completed_tasks": sum(s.completed_tasks for s in statistics)
                    },
                    "daily_statistics": [
                        {
                            "date": stat.date.isoformat() if stat.date else None,
                            "focus_time_minutes": stat.focus_time_minutes,
                            "completed_sessions": stat.completed_sessions,
                            "completed_tasks": stat.completed_tasks,
                            "recorded_at": stat.created_at.isoformat() if stat.created_at else None
                        }
                        for stat in statistics
                    ]
                }
                
                # Settings
                pomodoro_settings = db.query(PomodoroSettings).filter(PomodoroSettings.user_id == user_id).first()
                export_data["settings"] = {
                    "pomodoro_settings": {
                        "work_minutes": pomodoro_settings.work_minutes if pomodoro_settings else None,
                        "break_minutes": pomodoro_settings.break_minutes if pomodoro_settings else None,
                        "long_break_minutes": pomodoro_settings.long_break_minutes if pomodoro_settings else None,
                        "sessions_before_long": pomodoro_settings.sessions_before_long if pomodoro_settings else None,
                        "last_updated": pomodoro_settings.updated_at.isoformat() if pomodoro_settings and pomodoro_settings.updated_at else None
                    }
                }
                
                # Data summary
                export_data["data_summary"] = {
                    "total_goals": len(goals_2week) + len(goals_longterm),
                    "total_habits": len(habits),
                    "total_mood_entries": len(mood_entries),
                    "total_journal_entries": total_entries,
                    "total_study_sets": len(study_sets),
                    "note": "Complete synchronous export"
                }
            
            # Create exports directory
            export_dir = Path("exports")
            export_dir.mkdir(exist_ok=True)
            
            # Generate filename
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"user_{user_id}_data_export_{timestamp}.json"
            file_path = export_dir / filename
            
            # Write file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)
            
            result = {
                "success": True,
                "user_id": user_id,
                "file_path": str(file_path),
                "export_date": datetime.utcnow().isoformat(),
                "data_summary": {
                    "total_goals": len(goals_2week) + len(goals_longterm),
                    "total_habits": len(habits),
                    "total_mood_entries": len(mood_entries),
                    "total_journal_entries": total_entries,
                    "total_study_sets": len(study_sets)
                }
            }
            
            logger.info(f"Synchronous data export completed for user {user_id}")
            return result
            
        except Exception as e:
            logger.error(f"Data export failed for user {user_id}: {e}")
            raise
    
    @staticmethod
    def get_export_status(task_id: str) -> Dict[str, Any]:
        """
        Get the status of an export task.
        
        Args:
            task_id: ID of the export task
            
        Returns:
            Dictionary with task status and results
        """
        result = ExportService._get_stored_result(task_id)
        
        if result is None:
            return {
                "status": "NOT_FOUND",
                "message": "Export task not found"
            }
        
        if result.get("success", False):
            return {
                "status": "SUCCESS",
                "result": result,
                "completed_at": result.get("export_date"),
                "file_path": result.get("file_path"),
                "data_summary": result.get("data_summary")
            }
        else:
            return {
                "status": "FAILURE",
                "error": result.get("error", "Unknown error occurred"),
                "failed_at": result.get("export_date")
            }
    
    @staticmethod
    def _store_result(task_id: str, result: Dict[str, Any]) -> None:
        """Store export result for retrieval."""
        ExportService._results_cache[task_id] = result
    
    @staticmethod
    def _get_stored_result(task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored export result."""
        return ExportService._results_cache.get(task_id)

# Create instance for use in endpoints
export_service = ExportService()