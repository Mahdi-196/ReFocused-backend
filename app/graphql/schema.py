import strawberry
from typing import List, Optional
from datetime import date
from strawberry.types import Info
from fastapi import Depends

from .types import (
    User, Goal, QuickAccess, Habit, HabitStreak, MoodEntry,
    PomodoroSettings, StudySet, Flashcard, Mantra,
    JournalCollection, JournalEntry,
    GoalInput, HabitInput, HabitStreakInput, MoodEntryInput,
    PomodoroSettingsInput, StudySetInput, FlashcardInput,
    QuickAccessInput, MantraInput, JournalCollectionInput,
    JournalEntryInput
)
from .enums import GoalDuration
from .scalars import Date, DateTime
from ..db.session import get_db
from .resolvers import (
    get_user, get_goals, get_habits, get_habit_streaks,
    get_mood_entries, get_pomodoro_settings, get_study_sets,
    get_flashcards, get_quick_access, get_mantras,
    get_journal_collections, get_journal_entries,
    create_goal, update_goal, delete_goal, create_habit,
    add_habit_streak, upsert_mood_entry, set_pomodoro
    # Add more resolvers as they're implemented
)

from sqlalchemy.ext.asyncio import AsyncSession

# Query type
@strawberry.type
class Query:
    @strawberry.field
    async def user(
        self, info: Info, id: strawberry.ID
    ) -> Optional[User]:
        """Get a user by ID"""
        db = info.context["db"]
        return await get_user(id=id, db=db)
    
    @strawberry.field
    async def goals(
        self, info: Info, user_id: strawberry.ID, duration: Optional[GoalDuration] = None
    ) -> List[Goal]:
        """Get goals for a user, optionally filtered by duration"""
        db = info.context["db"]
        return await get_goals(user_id=user_id, db=db, duration=duration)
    
    @strawberry.field
    async def habits(
        self, info: Info, user_id: strawberry.ID
    ) -> List[Habit]:
        """Get habits for a user"""
        db = info.context["db"]
        return await get_habits(user_id=user_id, db=db)
    
    @strawberry.field
    async def habit_streaks(
        self, info: Info, habit_id: strawberry.ID
    ) -> List[HabitStreak]:
        """Get streaks for a habit"""
        db = info.context["db"]
        return await get_habit_streaks(habit_id=habit_id, db=db)
    
    @strawberry.field
    async def mood_entries(
        self, info: Info, user_id: strawberry.ID, date: Optional[Date] = None
    ) -> List[MoodEntry]:
        """Get mood entries for a user, optionally filtered by date"""
        db = info.context["db"]
        return await get_mood_entries(user_id=user_id, db=db, date=date)
    
    @strawberry.field
    async def pomodoro_settings(
        self, info: Info, user_id: strawberry.ID
    ) -> Optional[PomodoroSettings]:
        """Get pomodoro settings for a user"""
        db = info.context["db"]
        return await get_pomodoro_settings(user_id=user_id, db=db)
    
    @strawberry.field
    async def study_sets(
        self, info: Info, user_id: strawberry.ID
    ) -> List[StudySet]:
        """Get study sets for a user"""
        db = info.context["db"]
        return await get_study_sets(user_id=user_id, db=db)
    
    @strawberry.field
    async def flashcards(
        self, info: Info, set_id: strawberry.ID
    ) -> List[Flashcard]:
        """Get flashcards for a study set"""
        db = info.context["db"]
        return await get_flashcards(set_id=set_id, db=db)
    
    @strawberry.field
    async def quick_access(
        self, info: Info, user_id: strawberry.ID
    ) -> List[QuickAccess]:
        """Get quick access items for a user"""
        db = info.context["db"]
        return await get_quick_access(user_id=user_id, db=db)
    
    @strawberry.field
    async def mantras(
        self, info: Info, user_id: strawberry.ID
    ) -> List[Mantra]:
        """Get mantras for a user"""
        db = info.context["db"]
        return await get_mantras(user_id=user_id, db=db)
    
    @strawberry.field
    async def journal_collections(
        self, info: Info, user_id: strawberry.ID
    ) -> List[JournalCollection]:
        """Get journal collections for a user"""
        db = info.context["db"]
        return await get_journal_collections(user_id=user_id, db=db)
    
    @strawberry.field
    async def journal_entries(
        self, info: Info, collection_id: strawberry.ID
    ) -> List[JournalEntry]:
        """Get journal entries for a collection"""
        db = info.context["db"]
        return await get_journal_entries(collection_id=collection_id, db=db)

# Mutation type
@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_goal(
        self, info: Info, user_id: strawberry.ID, input: GoalInput
    ) -> Goal:
        """Create a new goal for a user"""
        db = info.context["db"]
        return await create_goal(user_id=user_id, input=input, db=db)
    
    @strawberry.mutation
    async def update_goal(
        self, info: Info, id: strawberry.ID, input: GoalInput
    ) -> Goal:
        """Update an existing goal"""
        db = info.context["db"]
        return await update_goal(id=id, input=input, db=db)
    
    @strawberry.mutation
    async def delete_goal(
        self, info: Info, id: strawberry.ID
    ) -> bool:
        """Delete a goal"""
        db = info.context["db"]
        return await delete_goal(id=id, db=db)
    
    @strawberry.mutation
    async def create_habit(
        self, info: Info, user_id: strawberry.ID, input: HabitInput
    ) -> Habit:
        """Create a new habit for a user"""
        db = info.context["db"]
        return await create_habit(user_id=user_id, input=input, db=db)
    
    @strawberry.mutation
    async def add_habit_streak(
        self, info: Info, input: HabitStreakInput
    ) -> HabitStreak:
        """Add a streak for a habit"""
        db = info.context["db"]
        return await add_habit_streak(input=input, db=db)
    
    @strawberry.mutation
    async def upsert_mood_entry(
        self, info: Info, user_id: strawberry.ID, input: MoodEntryInput
    ) -> MoodEntry:
        """Create or update a mood entry for a user"""
        db = info.context["db"]
        return await upsert_mood_entry(user_id=user_id, input=input, db=db)
    
    @strawberry.mutation
    async def set_pomodoro(
        self, info: Info, user_id: strawberry.ID, input: PomodoroSettingsInput
    ) -> PomodoroSettings:
        """Set pomodoro settings for a user"""
        db = info.context["db"]
        return await set_pomodoro(user_id=user_id, input=input, db=db)
    
    # TODO: Add other mutations

# Create the schema
schema = strawberry.Schema(
    query=Query, 
    mutation=Mutation,
    # config=strawberry.StrawberryConfig(
    #     auto_camel_case=True  # Example config
    # )
    # Remove or update the config parameter based on library version
)

# Create GraphQL context with DB session
async def get_context(db: AsyncSession = Depends(get_db)):
    # Pass request/response if needed by resolvers
    yield {"db": db}

# Create the schema
schema = strawberry.Schema(
    query=Query, 
    mutation=Mutation,
    # config=strawberry.StrawberryConfig(
    #     auto_camel_case=True  # Example config
    # )
    # Remove or update the config parameter based on library version
)

# Create GraphQL context with DB session
async def get_context(db: AsyncSession = Depends(get_db)): # Use FastAPI's Depends
    """Create context for Strawberry GraphQL with DB session"""
    # Pass request/response if needed by resolvers
    yield {"db": db} 