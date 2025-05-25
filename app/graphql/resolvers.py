import strawberry
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import (
    User as UserModel,
    Goal as GoalModel,
    QuickAccess as QuickAccessModel,
    Habit as HabitModel,
    HabitStreak as HabitStreakModel,
    MoodEntry as MoodEntryModel,
    PomodoroSettings as PomodoroSettingsModel,
    StudySet as StudySetModel,
    Flashcard as FlashcardModel,
    Mantra as MantraModel,
    JournalCollection as JournalCollectionModel,
    JournalEntry as JournalEntryModel
)

from .types import (
    User, Goal, QuickAccess, Habit, HabitStreak, MoodEntry,
    PomodoroSettings, StudySet, Flashcard, Mantra,
    JournalCollection, JournalEntry,
    GoalInput, HabitInput, HabitStreakInput, MoodEntryInput,
    PomodoroSettingsInput
)
# from .enums import GoalDuration  # No longer needed
from datetime import date

# Utility function to convert SQLAlchemy models to Strawberry types
def model_to_strawberry(model, type_class):
    """Convert a SQLAlchemy model instance to a Strawberry type instance"""
    if model is None:
        return None
    
    # Get all attributes from the model that match the Strawberry type
    attrs = {}
    for field in strawberry.field.get_fields(type_class):
        field_name = field.name
        if hasattr(model, field_name):
            attrs[field_name] = getattr(model, field_name)
    
    return type_class(**attrs)

# Query resolvers
async def get_user(id: strawberry.ID, db: AsyncSession) -> Optional[User]:
    """Get a user by ID"""
    result = await db.execute(
        select(UserModel).where(UserModel.id == id)
    )
    user = result.scalars().first()
    if not user:
        return None
    return model_to_strawberry(user, User)

async def get_goals(user_id: strawberry.ID, db: AsyncSession, priority: Optional[str] = None) -> List[Goal]:
    """Get goals for a user, optionally filtered by priority"""
    query = select(GoalModel).where(GoalModel.user_id == user_id)
    if priority:
        query = query.where(GoalModel.priority == priority)
    
    result = await db.execute(query)
    goals = result.scalars().all()
    return [model_to_strawberry(goal, Goal) for goal in goals]

async def get_habits(user_id: strawberry.ID, db: AsyncSession) -> List[Habit]:
    """Get habits for a user"""
    result = await db.execute(
        select(HabitModel).where(HabitModel.user_id == user_id)
    )
    habits = result.scalars().all()
    return [model_to_strawberry(habit, Habit) for habit in habits]

async def get_habit_streaks(habit_id: strawberry.ID, db: AsyncSession) -> List[HabitStreak]:
    """Get streaks for a habit"""
    result = await db.execute(
        select(HabitStreakModel).where(HabitStreakModel.habit_id == habit_id)
    )
    streaks = result.scalars().all()
    return [model_to_strawberry(streak, HabitStreak) for streak in streaks]

async def get_mood_entries(user_id: strawberry.ID, db: AsyncSession, date: Optional[date] = None) -> List[MoodEntry]:
    """Get mood entries for a user, optionally filtered by date"""
    query = select(MoodEntryModel).where(MoodEntryModel.user_id == user_id)
    if date:
        query = query.where(MoodEntryModel.entry_date == date)
    
    result = await db.execute(query)
    entries = result.scalars().all()
    return [model_to_strawberry(entry, MoodEntry) for entry in entries]

async def get_pomodoro_settings(user_id: strawberry.ID, db: AsyncSession) -> Optional[PomodoroSettings]:
    """Get pomodoro settings for a user"""
    result = await db.execute(
        select(PomodoroSettingsModel).where(PomodoroSettingsModel.user_id == user_id)
    )
    settings = result.scalars().first()
    if not settings:
        return None
    return model_to_strawberry(settings, PomodoroSettings)

async def get_study_sets(user_id: strawberry.ID, db: AsyncSession) -> List[StudySet]:
    """Get study sets for a user"""
    result = await db.execute(
        select(StudySetModel).where(StudySetModel.user_id == user_id)
    )
    sets = result.scalars().all()
    return [model_to_strawberry(set_, StudySet) for set_ in sets]

async def get_flashcards(set_id: strawberry.ID, db: AsyncSession) -> List[Flashcard]:
    """Get flashcards for a study set"""
    result = await db.execute(
        select(FlashcardModel).where(FlashcardModel.set_id == set_id)
    )
    cards = result.scalars().all()
    return [model_to_strawberry(card, Flashcard) for card in cards]

async def get_quick_access(user_id: strawberry.ID, db: AsyncSession) -> List[QuickAccess]:
    """Get quick access items for a user"""
    result = await db.execute(
        select(QuickAccessModel).where(QuickAccessModel.user_id == user_id)
    )
    items = result.scalars().all()
    return [model_to_strawberry(item, QuickAccess) for item in items]

async def get_mantras(user_id: strawberry.ID, db: AsyncSession) -> List[Mantra]:
    """Get mantras for a user"""
    result = await db.execute(
        select(MantraModel).where(MantraModel.user_id == user_id)
    )
    mantras = result.scalars().all()
    return [model_to_strawberry(mantra, Mantra) for mantra in mantras]

async def get_journal_collections(user_id: strawberry.ID, db: AsyncSession) -> List[JournalCollection]:
    """Get journal collections for a user"""
    result = await db.execute(
        select(JournalCollectionModel).where(JournalCollectionModel.user_id == user_id)
    )
    collections = result.scalars().all()
    return [model_to_strawberry(collection, JournalCollection) for collection in collections]

async def get_journal_entries(collection_id: strawberry.ID, db: AsyncSession) -> List[JournalEntry]:
    """Get journal entries for a collection"""
    result = await db.execute(
        select(JournalEntryModel).where(JournalEntryModel.collection_id == collection_id)
    )
    entries = result.scalars().all()
    return [model_to_strawberry(entry, JournalEntry) for entry in entries]

# Mutation resolvers (implemented examples)
async def create_goal(user_id: strawberry.ID, input: GoalInput, db: AsyncSession) -> Goal:
    """Create a new goal for a user"""
    # Create a new goal model
    new_goal = GoalModel(
        user_id=user_id,
        title=input.title,
        description=input.description,
        target_date=input.target_date,
        priority=input.priority or "medium",
        category=input.category
    )
    
    # Add to session and commit
    db.add(new_goal)
    await db.commit()
    await db.refresh(new_goal)
    
    # Convert to Strawberry type and return
    return model_to_strawberry(new_goal, Goal)

async def update_goal(id: strawberry.ID, input: GoalInput, db: AsyncSession) -> Goal:
    """Update an existing goal"""
    result = await db.execute(select(GoalModel).where(GoalModel.id == id))
    goal = result.scalars().first()
    
    if goal is None:
        raise ValueError(f"Goal with ID {id} not found")
    
    # Update fields
    if input.title is not None:
        goal.title = input.title
    if input.description is not None:
        goal.description = input.description
    if input.target_date is not None:
        goal.target_date = input.target_date
    if input.priority is not None:
        goal.priority = input.priority
    if input.category is not None:
        goal.category = input.category
    
    await db.commit()
    await db.refresh(goal)
    
    return model_to_strawberry(goal, Goal)

async def delete_goal(id: strawberry.ID, db: AsyncSession) -> bool:
    """Delete a goal"""
    result = await db.execute(select(GoalModel).where(GoalModel.id == id))
    goal = result.scalars().first()
    
    if goal is None:
        return False
    
    await db.delete(goal)
    await db.commit()
    
    return True

async def create_habit(user_id: strawberry.ID, input: HabitInput, db: AsyncSession) -> Habit:
    """Create a new habit for a user"""
    new_habit = HabitModel(
        user_id=user_id,
        name=input.name
    )
    
    db.add(new_habit)
    await db.commit()
    await db.refresh(new_habit)
    
    return model_to_strawberry(new_habit, Habit)

async def add_habit_streak(input: HabitStreakInput, db: AsyncSession) -> HabitStreak:
    """Add a streak for a habit"""
    new_streak = HabitStreakModel(
        habit_id=input.habit_id,
        date=input.date
    )
    
    db.add(new_streak)
    await db.commit()
    await db.refresh(new_streak)
    
    return model_to_strawberry(new_streak, HabitStreak)

async def upsert_mood_entry(user_id: strawberry.ID, input: MoodEntryInput, db: AsyncSession) -> MoodEntry:
    """Create or update a mood entry for a user on a specific date"""
    # Check if an entry already exists for this date
    result = await db.execute(
        select(MoodEntryModel).where(
            MoodEntryModel.user_id == user_id,
            MoodEntryModel.entry_date == input.entry_date
        )
    )
    entry = result.scalars().first()
    
    if entry:
        # Update existing entry
        entry.mood = input.mood
        entry.rating = input.rating
        entry.note = input.note
    else:
        # Create new entry
        entry = MoodEntryModel(
            user_id=user_id,
            mood=input.mood,
            rating=input.rating,
            entry_date=input.entry_date,
            note=input.note
        )
        db.add(entry)
    
    await db.commit()
    await db.refresh(entry)
    
    return model_to_strawberry(entry, MoodEntry)

async def set_pomodoro(user_id: strawberry.ID, input: PomodoroSettingsInput, db: AsyncSession) -> PomodoroSettings:
    """Create or update pomodoro settings for a user"""
    # Check if settings exist
    result = await db.execute(
        select(PomodoroSettingsModel).where(PomodoroSettingsModel.user_id == user_id)
    )
    settings = result.scalars().first()
    
    if settings:
        # Update existing settings
        if input.work_minutes is not None:
            settings.work_minutes = input.work_minutes
        if input.break_minutes is not None:
            settings.break_minutes = input.break_minutes
        if input.long_break_minutes is not None:
            settings.long_break_minutes = input.long_break_minutes
        if input.sessions_before_long is not None:
            settings.sessions_before_long = input.sessions_before_long
    else:
        # Create default settings and apply any provided values
        settings = PomodoroSettingsModel(
            user_id=user_id,
            work_minutes=input.work_minutes if input.work_minutes is not None else 25,
            break_minutes=input.break_minutes if input.break_minutes is not None else 5,
            long_break_minutes=input.long_break_minutes if input.long_break_minutes is not None else 15,
            sessions_before_long=input.sessions_before_long if input.sessions_before_long is not None else 4
        )
        db.add(settings)
    
    await db.commit()
    await db.refresh(settings)
    
    return model_to_strawberry(settings, PomodoroSettings) 