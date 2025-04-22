import strawberry
from typing import List, Optional
from datetime import date

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
        self, id: strawberry.ID, 
        db: AsyncSession = strawberry.Private[AsyncSession]
    ) -> Optional[User]:
        """Get a user by ID"""
        return await get_user(id=id, db=db)
    
    @strawberry.field
    async def goals(
        self, 
        user_id: strawberry.ID, 
        duration: Optional[GoalDuration] = None,
        db: AsyncSession = strawberry.Private[AsyncSession]
    ) -> List[Goal]:
        """Get goals for a user, optionally filtered by duration"""
        return await get_goals(user_id=user_id, db=db, duration=duration)
    
    @strawberry.field
    async def habits(
        self, 
        user_id: strawberry.ID,
        db: AsyncSession = strawberry.Private[AsyncSession]
    ) -> List[Habit]:
        """Get habits for a user"""
        return await get_habits(user_id=user_id, db=db)
    
    @strawberry.field
    async def habit_streaks(
        self, 
        habit_id: strawberry.ID,
        db: AsyncSession = strawberry.Private[AsyncSession]
    ) -> List[HabitStreak]:
        """Get streaks for a habit"""
        return await get_habit_streaks(habit_id=habit_id, db=db)
    
    @strawberry.field
    async def mood_entries(
        self, 
        user_id: strawberry.ID,
        date: Optional[Date] = None,
        db: AsyncSession = strawberry.Private[AsyncSession]
    ) -> List[MoodEntry]:
        """Get mood entries for a user, optionally filtered by date"""
        return await get_mood_entries(user_id=user_id, db=db, date=date)
    
    @strawberry.field
    async def pomodoro_settings(
        self, 
        user_id: strawberry.ID,
        db: AsyncSession = strawberry.Private[AsyncSession]
    ) -> Optional[PomodoroSettings]:
        """Get pomodoro settings for a user"""
        return await get_pomodoro_settings(user_id=user_id, db=db)
    
    @strawberry.field
    async def study_sets(
        self, 
        user_id: strawberry.ID,
        db: AsyncSession = strawberry.Private[AsyncSession]
    ) -> List[StudySet]:
        """Get study sets for a user"""
        return await get_study_sets(user_id=user_id, db=db)
    
    @strawberry.field
    async def flashcards(
        self, 
        set_id: strawberry.ID,
        db: AsyncSession = strawberry.Private[AsyncSession]
    ) -> List[Flashcard]:
        """Get flashcards for a study set"""
        return await get_flashcards(set_id=set_id, db=db)
    
    @strawberry.field
    async def quick_access(
        self, 
        user_id: strawberry.ID,
        db: AsyncSession = strawberry.Private[AsyncSession]
    ) -> List[QuickAccess]:
        """Get quick access items for a user"""
        return await get_quick_access(user_id=user_id, db=db)
    
    @strawberry.field
    async def mantras(
        self, 
        user_id: strawberry.ID,
        db: AsyncSession = strawberry.Private[AsyncSession]
    ) -> List[Mantra]:
        """Get mantras for a user"""
        return await get_mantras(user_id=user_id, db=db)
    
    @strawberry.field
    async def journal_collections(
        self, 
        user_id: strawberry.ID,
        db: AsyncSession = strawberry.Private[AsyncSession]
    ) -> List[JournalCollection]:
        """Get journal collections for a user"""
        return await get_journal_collections(user_id=user_id, db=db)
    
    @strawberry.field
    async def journal_entries(
        self, 
        collection_id: strawberry.ID,
        db: AsyncSession = strawberry.Private[AsyncSession]
    ) -> List[JournalEntry]:
        """Get journal entries for a collection"""
        return await get_journal_entries(collection_id=collection_id, db=db)

# Mutation type
@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_goal(
        self, 
        user_id: strawberry.ID, 
        input: GoalInput,
        db: AsyncSession = strawberry.Private[AsyncSession]
    ) -> Goal:
        """Create a new goal for a user"""
        return await create_goal(user_id=user_id, input=input, db=db)
    
    @strawberry.mutation
    async def update_goal(
        self, 
        id: strawberry.ID, 
        input: GoalInput,
        db: AsyncSession = strawberry.Private[AsyncSession]
    ) -> Goal:
        """Update an existing goal"""
        return await update_goal(id=id, input=input, db=db)
    
    @strawberry.mutation
    async def delete_goal(
        self, 
        id: strawberry.ID,
        db: AsyncSession = strawberry.Private[AsyncSession]
    ) -> bool:
        """Delete a goal"""
        return await delete_goal(id=id, db=db)
    
    @strawberry.mutation
    async def create_habit(
        self, 
        user_id: strawberry.ID, 
        input: HabitInput,
        db: AsyncSession = strawberry.Private[AsyncSession]
    ) -> Habit:
        """Create a new habit for a user"""
        return await create_habit(user_id=user_id, input=input, db=db)
    
    @strawberry.mutation
    async def add_habit_streak(
        self, 
        input: HabitStreakInput,
        db: AsyncSession = strawberry.Private[AsyncSession]
    ) -> HabitStreak:
        """Add a streak for a habit"""
        return await add_habit_streak(input=input, db=db)
    
    @strawberry.mutation
    async def upsert_mood_entry(
        self, 
        user_id: strawberry.ID, 
        input: MoodEntryInput,
        db: AsyncSession = strawberry.Private[AsyncSession]
    ) -> MoodEntry:
        """Create or update a mood entry for a user"""
        return await upsert_mood_entry(user_id=user_id, input=input, db=db)
    
    @strawberry.mutation
    async def set_pomodoro(
        self, 
        user_id: strawberry.ID, 
        input: PomodoroSettingsInput,
        db: AsyncSession = strawberry.Private[AsyncSession]
    ) -> PomodoroSettings:
        """Create or update pomodoro settings for a user"""
        return await set_pomodoro(user_id=user_id, input=input, db=db)
    
    # Add more mutations as they're implemented

# Create schema
schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    config=strawberry.StrawberryConfig(
        auto_camel_case=True
    )
)

# Create GraphQL context with DB session
async def get_context(db=None):
    """Create context for Strawberry GraphQL with DB session"""
    if db is None:
        # If no DB is provided, use the generator
        async for session in get_db():
            yield {"db": session}
    else:
        # If DB is provided, just yield it
        yield {"db": db} 