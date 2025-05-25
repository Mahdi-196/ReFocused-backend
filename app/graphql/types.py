import strawberry
from typing import List, Optional

# from .enums import GoalDuration  # No longer needed
from .scalars import Date, DateTime

# Core types
@strawberry.type
class User:
    id: strawberry.ID
    email: str
    created_at: DateTime
    goals: List["Goal"]
    quick_access: List["QuickAccess"]
    habits: List["Habit"]
    mood_entries: List["MoodEntry"]
    pomodoro_settings: Optional["PomodoroSettings"] = None
    study_sets: List["StudySet"]
    mantras: List["Mantra"]
    journal_collections: List["JournalCollection"]

@strawberry.type
class Goal:
    id: strawberry.ID
    user: "User"
    title: str
    description: Optional[str] = None
    target_date: Optional[DateTime] = None
    is_completed: bool = False
    priority: str = "medium"  # low, medium, high
    category: Optional[str] = None
    created_at: DateTime
    updated_at: DateTime

@strawberry.type
class QuickAccess:
    id: strawberry.ID
    user: "User"
    name: str
    target_url: Optional[str] = None
    created_at: DateTime

@strawberry.type
class Habit:
    id: strawberry.ID
    user: "User"
    name: str
    streaks: List["HabitStreak"]
    created_at: DateTime

@strawberry.type
class HabitStreak:
    id: strawberry.ID
    habit: "Habit"
    date: Date

@strawberry.type
class MoodEntry:
    id: strawberry.ID
    user: "User"
    mood: int       # 1-10
    rating: int     # 1-5
    entry_date: Date
    note: Optional[str] = None
    created_at: DateTime

@strawberry.type
class PomodoroSettings:
    user: "User"
    work_minutes: int
    break_minutes: int
    long_break_minutes: int
    sessions_before_long: int
    updated_at: DateTime

@strawberry.type
class StudySet:
    id: strawberry.ID
    user: "User"
    title: str
    flashcards: List["Flashcard"]
    created_at: DateTime

@strawberry.type
class Flashcard:
    id: strawberry.ID
    set: "StudySet"
    question: str
    answer: str
    created_at: DateTime

@strawberry.type
class Mantra:
    id: strawberry.ID
    user: "User"
    text: str
    created_at: DateTime

@strawberry.type
class JournalCollection:
    id: strawberry.ID
    user: "User"
    title: str
    entries: List["JournalEntry"]
    created_at: DateTime

@strawberry.type
class JournalEntry:
    id: strawberry.ID
    collection: "JournalCollection"
    title: Optional[str] = None
    content: str
    created_at: DateTime
    updated_at: DateTime

# Input types for mutations
@strawberry.input
class GoalInput:
    title: str
    description: Optional[str] = None
    target_date: Optional[DateTime] = None
    priority: Optional[str] = "medium"
    category: Optional[str] = None

@strawberry.input
class HabitInput:
    name: str

@strawberry.input
class HabitStreakInput:
    habit_id: strawberry.ID
    date: Date

@strawberry.input
class MoodEntryInput:
    mood: int
    rating: int
    entry_date: Date
    note: Optional[str] = None

@strawberry.input
class PomodoroSettingsInput:
    work_minutes: Optional[int] = None
    break_minutes: Optional[int] = None
    long_break_minutes: Optional[int] = None
    sessions_before_long: Optional[int] = None

@strawberry.input
class StudySetInput:
    title: str

@strawberry.input
class FlashcardInput:
    set_id: strawberry.ID
    question: str
    answer: str

@strawberry.input
class QuickAccessInput:
    name: str
    target_url: Optional[str] = None

@strawberry.input
class MantraInput:
    text: str

@strawberry.input
class JournalCollectionInput:
    title: str

@strawberry.input
class JournalEntryInput:
    collection_id: strawberry.ID
    title: Optional[str] = None
    content: str 