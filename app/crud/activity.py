from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, func, select, update
from datetime import datetime

from app.db.models import (
    User, Goal2Week, GoalLongTerm, Habit, HabitCompletion, HabitStreak,
    MoodEntry, PomodoroSettings, StudySet, Flashcard, Mantra,
    JournalCollection, JournalEntry, Gratitude, UserStatistics,
    CalendarEntry, CalendarHabitCompletion, CalendarMoodEntry, QuickAccess,
    UserDailyStreak
)


class CRUDActivity:
    """
    CRUD operations for user activity data deletion.
    Provides secure bulk deletion of all user activity while preserving core account.
    """

    @staticmethod
    async def get_activity_counts(db: AsyncSession, user_id: int) -> Dict[str, int]:
        """
        Get counts of all activity data for a user before deletion.
        Returns a summary of data that will be deleted.
        """
        counts = {}
        
        # Goals (2-week and long-term)
        goals_2week_count = await db.execute(
            select(func.count(Goal2Week.id)).where(Goal2Week.user_id == user_id)
        )
        counts["goals_2week"] = goals_2week_count.scalar() or 0
        
        goals_longterm_count = await db.execute(
            select(func.count(GoalLongTerm.id)).where(GoalLongTerm.user_id == user_id)
        )
        counts["goals_longterm"] = goals_longterm_count.scalar() or 0
        
        # Habits and completions
        habits_count = await db.execute(
            select(func.count(Habit.id)).where(Habit.user_id == user_id)
        )
        counts["habits"] = habits_count.scalar() or 0
        
        habit_completions_count = await db.execute(
            select(func.count(HabitCompletion.id)).where(HabitCompletion.user_id == user_id)
        )
        counts["habit_completions"] = habit_completions_count.scalar() or 0
        
        habit_streaks_count = await db.execute(
            select(func.count(HabitStreak.id)).join(Habit).where(Habit.user_id == user_id)
        )
        counts["habit_streaks"] = habit_streaks_count.scalar() or 0
        
        # Mood entries
        mood_entries_count = await db.execute(
            select(func.count(MoodEntry.id)).where(MoodEntry.user_id == user_id)
        )
        counts["mood_entries"] = mood_entries_count.scalar() or 0
        
        # Journal data
        journal_collections_count = await db.execute(
            select(func.count(JournalCollection.id)).where(JournalCollection.user_id == user_id)
        )
        counts["journal_collections"] = journal_collections_count.scalar() or 0
        
        journal_entries_count = await db.execute(
            select(func.count(JournalEntry.id))
            .join(JournalCollection)
            .where(JournalCollection.user_id == user_id)
        )
        counts["journal_entries"] = journal_entries_count.scalar() or 0
        
        # Gratitude entries
        gratitude_count = await db.execute(
            select(func.count(Gratitude.id)).where(Gratitude.user_id == user_id)
        )
        counts["gratitude_entries"] = gratitude_count.scalar() or 0
        
        # Study data
        study_sets_count = await db.execute(
            select(func.count(StudySet.id)).where(StudySet.user_id == user_id)
        )
        counts["study_sets"] = study_sets_count.scalar() or 0
        
        flashcards_count = await db.execute(
            select(func.count(Flashcard.id))
            .join(StudySet)
            .where(StudySet.user_id == user_id)
        )
        counts["flashcards"] = flashcards_count.scalar() or 0
        
        # Other activity data
        mantras_count = await db.execute(
            select(func.count(Mantra.id)).where(Mantra.user_id == user_id)
        )
        counts["mantras"] = mantras_count.scalar() or 0
        
        statistics_count = await db.execute(
            select(func.count(UserStatistics.id)).where(UserStatistics.user_id == user_id)
        )
        counts["statistics"] = statistics_count.scalar() or 0
        
        quick_access_count = await db.execute(
            select(func.count(QuickAccess.id)).where(QuickAccess.user_id == user_id)
        )
        counts["quick_access"] = quick_access_count.scalar() or 0
        
        # Calendar data
        calendar_entries_count = await db.execute(
            select(func.count(CalendarEntry.id)).where(CalendarEntry.user_id == user_id)
        )
        counts["calendar_entries"] = calendar_entries_count.scalar() or 0
        
        calendar_habit_completions_count = await db.execute(
            select(func.count(CalendarHabitCompletion.id))
            .join(CalendarEntry)
            .where(CalendarEntry.user_id == user_id)
        )
        counts["calendar_habit_completions"] = calendar_habit_completions_count.scalar() or 0
        
        calendar_mood_entries_count = await db.execute(
            select(func.count(CalendarMoodEntry.id))
            .join(CalendarEntry)
            .where(CalendarEntry.user_id == user_id)
        )
        counts["calendar_mood_entries"] = calendar_mood_entries_count.scalar() or 0
        
        # Daily streak data
        daily_streaks_count = await db.execute(
            select(func.count(UserDailyStreak.id)).where(UserDailyStreak.user_id == user_id)
        )
        counts["daily_streaks"] = daily_streaks_count.scalar() or 0
        
        # Calculate total records
        counts["total_records"] = sum(counts.values())
        
        return counts

    @staticmethod
    async def delete_all_activity_data(db: AsyncSession, user_id: int) -> Dict[str, Any]:
        """
        Permanently delete all activity data for a user while preserving the core account.
        
        This operation:
        - Deletes all user activity history (goals, habits, mood, journal, etc.)
        - Preserves the core user account (users table)
        - Uses secure parameterized queries to prevent SQL injection
        - Returns a summary of deleted data for confirmation
        
        Args:
            db: Database session
            user_id: ID of the user whose activity data should be deleted
            
        Returns:
            Dictionary containing deletion summary and confirmation
        """
        try:
            # Get counts before deletion for summary
            deletion_summary = await CRUDActivity.get_activity_counts(db, user_id)
            
            # Verify user exists and is active (security check)
            user_result = await db.execute(
                select(User).where(User.id == user_id, User.is_active == True)
            )
            user = user_result.scalar_one_or_none()
            if not user:
                raise ValueError("User not found or inactive")
            
            # Delete calendar-related data first (due to foreign key constraints)
            await db.execute(
                delete(CalendarMoodEntry)
                .where(
                    CalendarMoodEntry.calendar_entry_id.in_(
                        select(CalendarEntry.id).where(CalendarEntry.user_id == user_id)
                    )
                )
            )
            
            await db.execute(
                delete(CalendarHabitCompletion)
                .where(
                    CalendarHabitCompletion.calendar_entry_id.in_(
                        select(CalendarEntry.id).where(CalendarEntry.user_id == user_id)
                    )
                )
            )
            
            await db.execute(
                delete(CalendarEntry).where(CalendarEntry.user_id == user_id)
            )
            
            # Delete study-related data
            await db.execute(
                delete(Flashcard)
                .where(
                    Flashcard.set_id.in_(
                        select(StudySet.id).where(StudySet.user_id == user_id)
                    )
                )
            )
            
            await db.execute(
                delete(StudySet).where(StudySet.user_id == user_id)
            )
            
            # Delete journal-related data
            await db.execute(
                delete(JournalEntry)
                .where(
                    JournalEntry.collection_id.in_(
                        select(JournalCollection.id).where(JournalCollection.user_id == user_id)
                    )
                )
            )
            
            await db.execute(
                delete(JournalCollection).where(JournalCollection.user_id == user_id)
            )
            
            # Delete habit-related data
            await db.execute(
                delete(HabitStreak)
                .where(
                    HabitStreak.habit_id.in_(
                        select(Habit.id).where(Habit.user_id == user_id)
                    )
                )
            )
            
            await db.execute(
                delete(HabitCompletion).where(HabitCompletion.user_id == user_id)
            )
            
            await db.execute(
                delete(Habit).where(Habit.user_id == user_id)
            )
            
            # Delete goals
            await db.execute(
                delete(Goal2Week).where(Goal2Week.user_id == user_id)
            )
            
            await db.execute(
                delete(GoalLongTerm).where(GoalLongTerm.user_id == user_id)
            )
            
            # Delete other activity data (direct user relationships)
            await db.execute(
                delete(MoodEntry).where(MoodEntry.user_id == user_id)
            )
            
            await db.execute(
                delete(Gratitude).where(Gratitude.user_id == user_id)
            )
            
            await db.execute(
                delete(Mantra).where(Mantra.user_id == user_id)
            )
            
            await db.execute(
                delete(UserStatistics).where(UserStatistics.user_id == user_id)
            )
            
            await db.execute(
                delete(QuickAccess).where(QuickAccess.user_id == user_id)
            )
            
            await db.execute(
                delete(PomodoroSettings).where(PomodoroSettings.user_id == user_id)
            )
            
            # Delete daily streak data
            await db.execute(
                delete(UserDailyStreak).where(UserDailyStreak.user_id == user_id)
            )
            
            # Reset user's streak data in users table
            await db.execute(
                update(User)
                .where(User.id == user_id)
                .values(
                    current_streak=0,
                    longest_streak=0,
                    last_interaction_date=None,
                    streak_updated_at=datetime.utcnow()
                )
            )
            
            # Commit all deletions
            await db.commit()
            
            return {
                "success": True,
                "message": "All activity data has been permanently deleted",
                "deleted_at": datetime.utcnow().isoformat(),
                "deletion_summary": deletion_summary,
                "user_account_preserved": True
            }
            
        except Exception as e:
            # Rollback on any error
            await db.rollback()
            raise e


# Create instance for use in endpoints
crud_activity = CRUDActivity()