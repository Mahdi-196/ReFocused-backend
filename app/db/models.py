from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Date, 
    ForeignKey, Boolean, UniqueConstraint, Index, Float, CheckConstraint
)
from sqlalchemy.orm import relationship, DeclarativeBase
from sqlalchemy.sql import func
from datetime import datetime, timedelta, timezone
from app.db.database import Base

# Base class for all models
class Base(DeclarativeBase):
    pass

# Remove unused enum
# class GoalDurationType(str, enum.Enum):
#     SHORT = "SHORT"
#     LONG = "LONG"

# User model
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True)  # Allow null for OAuth users
    name = Column(String)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    
    # OAuth fields
    google_id = Column(String, unique=True, nullable=True, index=True)
    auth_provider = Column(String, default="local", nullable=False)  # 'local', 'google'
    profile_picture = Column(String, nullable=True)
    
    # Timezone support for global users
    timezone = Column(String, default="UTC", nullable=False)  # IANA timezone identifier like "America/New_York"
    timezone_detected_method = Column(String, default="auto", nullable=False)  # 'auto', 'manual', 'ip_geo'
    timezone_confidence = Column(Float, default=0.5, nullable=False)  # 0.0-1.0 confidence score
    timezone_updated_at = Column(DateTime(timezone=True), server_default=func.now())
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True))
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True))
    password_changed_at = Column(DateTime(timezone=True))
    password_history = relationship("PasswordHistory", back_populates="user")
    login_attempts = relationship("LoginAttempt", back_populates="user")
    security_logs = relationship("SecurityLog", back_populates="user")
    
    # Relationships
    goals = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    quick_access = relationship("QuickAccess", back_populates="user", cascade="all, delete-orphan")
    habits = relationship("Habit", back_populates="user", cascade="all, delete-orphan")
    mood_entries = relationship("MoodEntry", back_populates="user", cascade="all, delete-orphan")
    pomodoro_settings = relationship("PomodoroSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    study_sets = relationship("StudySet", back_populates="user", cascade="all, delete-orphan")
    mantras = relationship("Mantra", back_populates="user", cascade="all, delete-orphan")
    journal_collections = relationship("JournalCollection", back_populates="user", cascade="all, delete-orphan")
    statistics = relationship("UserStatistics", back_populates="user", cascade="all, delete-orphan")

# Goal model
class Goal(Base):
    __tablename__ = "goals"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    target_date = Column(DateTime, nullable=True)
    is_completed = Column(Boolean, default=False, nullable=False)
    priority = Column(String(20), default="medium", nullable=False)  # low, medium, high
    category = Column(String(100), nullable=True)
    
    # User relationship
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="goals")
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

# QuickAccess model
class QuickAccess(Base):
    __tablename__ = "quick_access"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    target_url = Column(String)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="quick_access")

# Habit model
class Habit(Base):
    __tablename__ = "habits"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    is_favorite = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_updated_utc = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    streak = Column(Integer, default=0, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="habits")
    completions = relationship("HabitCompletion", back_populates="habit", cascade="all, delete-orphan")
    
    # Legacy relationship for backward compatibility (deprecated)
    streaks = relationship("HabitStreak", back_populates="habit", cascade="all, delete-orphan")
    
    # Unique constraint for user + name
    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uix_user_habit_name'),
        CheckConstraint("LENGTH(TRIM(name)) > 0", name='chk_habit_name_not_empty'),
        Index('idx_habits_user_active', 'user_id', 'is_active'),
        Index('idx_habits_user_favorite', 'user_id', 'is_favorite'),
    )

# New timezone-aware habit completion model
class HabitCompletion(Base):
    __tablename__ = "habit_completions"
    
    id = Column(Integer, primary_key=True)
    habit_id = Column(Integer, ForeignKey("habits.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)  # User's local date
    completed = Column(Boolean, default=True, nullable=False)
    completed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    timezone = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    habit = relationship("Habit", back_populates="completions")
    user = relationship("User")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('habit_id', 'date', name='uix_habit_completion_date'),
        Index('idx_habit_completions_user_date', 'user_id', 'date'),
        Index('idx_habit_completions_habit', 'habit_id'),
    )

# Legacy HabitStreak model (deprecated but kept for backward compatibility)
class HabitStreak(Base):
    __tablename__ = "habit_streaks"
    
    id = Column(Integer, primary_key=True)
    habit_id = Column(Integer, ForeignKey("habits.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    
    # Relationships
    habit = relationship("Habit", back_populates="streaks")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('habit_id', 'date', name='uix_habit_date'),
    )

# MoodEntry model
class MoodEntry(Base):
    __tablename__ = "mood_entries"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    happiness = Column(Integer, nullable=False)  # 1-5
    satisfaction = Column(Integer, nullable=False)  # 1-5
    stress = Column(Integer, nullable=False)  # 1-5
    day_rating = Column(Integer, nullable=False)  # 1-10
    entry_date = Column(Date, nullable=False, index=True)
    note = Column(Text)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="mood_entries")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'entry_date', name='uix_user_entry_date'),
        Index('idx_mood_entries_user_date', 'user_id', 'entry_date')
    )

# PomodoroSettings model
class PomodoroSettings(Base):
    __tablename__ = "pomodoro_settings"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    work_minutes = Column(Integer, nullable=False, default=25)
    break_minutes = Column(Integer, nullable=False, default=5)
    long_break_minutes = Column(Integer, nullable=False, default=15)
    sessions_before_long = Column(Integer, nullable=False, default=4)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="pomodoro_settings")

# StudySet model
class StudySet(Base):
    __tablename__ = "study_sets"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="study_sets")
    flashcards = relationship("Flashcard", back_populates="set", cascade="all, delete-orphan")

# Flashcard model
class Flashcard(Base):
    __tablename__ = "flashcards"
    
    id = Column(Integer, primary_key=True)
    set_id = Column(Integer, ForeignKey("study_sets.id"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Relationships
    set = relationship("StudySet", back_populates="flashcards")

# Mantra model
class Mantra(Base):
    __tablename__ = "mantras"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="mantras")

# JournalCollection model
class JournalCollection(Base):
    __tablename__ = "journal_collections"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="journal_collections")
    entries = relationship("JournalEntry", back_populates="collection", cascade="all, delete-orphan")

# JournalEntry model
class JournalEntry(Base):
    __tablename__ = "journal_entries"
    
    id = Column(Integer, primary_key=True)
    collection_id = Column(Integer, ForeignKey("journal_collections.id"), nullable=False, index=True)
    title = Column(String)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    collection = relationship("JournalCollection", back_populates="entries")

class PasswordHistory(Base):
    __tablename__ = "password_history"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="password_history")

class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ip_address = Column(String, nullable=False)
    success = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="login_attempts")
    
    @classmethod
    def get_recent_attempts(cls, db, user_id: int, minutes: int):
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        return db.query(cls).filter(
            cls.user_id == user_id,
            cls.created_at >= cutoff
        ).all()

class TokenBlacklist(Base):
    __tablename__ = "token_blacklist"
    
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True, nullable=False)
    blacklisted_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    
    @classmethod
    async def is_blacklisted(cls, db, token: str) -> bool:
        from sqlalchemy import select
        result = await db.execute(
            select(cls).where(
                cls.token == token,
                cls.expires_at > datetime.now(timezone.utc)
            )
        )
        return result.scalar_one_or_none() is not None
    
    @classmethod
    async def add_token(cls, db, token: str, expires_at: datetime):
        blacklisted_token = cls(token=token, expires_at=expires_at)
        db.add(blacklisted_token)
        await db.commit()
        return blacklisted_token

class SecurityLog(Base):
    __tablename__ = "security_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    event_type = Column(String, nullable=False)
    ip_address = Column(String, nullable=False)
    user_agent = Column(String)
    details = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="security_logs")
    
    @classmethod
    def log_event(cls, db, event_type: str, ip_address: str, user_id: int = None,
                 user_agent: str = None, details: str = None):
        log = cls(
            user_id=user_id,
            event_type=event_type,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details
        )
        db.add(log)
        db.commit()
        return log

class SecurityAlert(Base):
    __tablename__ = "security_alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)  # low, medium, high, critical
    description = Column(Text, nullable=False)
    ip_address = Column(String)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True))
    
    @classmethod
    def create_alert(cls, db, alert_type: str, severity: str, description: str,
                    ip_address: str = None, user_id: int = None):
        alert = cls(
            alert_type=alert_type,
            severity=severity,
            description=description,
            ip_address=ip_address,
            user_id=user_id
        )
        db.add(alert)
        db.commit()
        return alert
    
    def resolve(self, db):
        self.resolved = True
        self.resolved_at = datetime.utcnow()
        db.commit()
        return self

# UserStatistics model
class UserStatistics(Base):
    __tablename__ = "user_statistics"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, default=func.current_date())
    focus_time_minutes = Column(Integer, default=0)
    completed_sessions = Column(Integer, default=0)
    completed_tasks = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="statistics")
    
    # Unique constraint to ensure one record per user per date
    __table_args__ = (
        UniqueConstraint('user_id', 'date', name='user_date_unique'),
    )

# Calendar models for enhanced calendar implementation
class CalendarEntry(Base):
    __tablename__ = "calendar_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)  # User's local date
    notes = Column(Text, nullable=True)
    is_locked = Column(Boolean, default=False, nullable=False)  # Read-only protection for past dates
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User")
    habit_completions = relationship("CalendarHabitCompletion", back_populates="calendar_entry", cascade="all, delete-orphan")
    mood_entry = relationship("CalendarMoodEntry", back_populates="calendar_entry", uselist=False, cascade="all, delete-orphan")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'date', name='uix_calendar_user_date'),
        Index('idx_calendar_entries_user_date', 'user_id', 'date'),
        Index('idx_calendar_entries_locked', 'is_locked'),
    )

class CalendarHabitCompletion(Base):
    __tablename__ = "calendar_habit_completions"
    
    id = Column(Integer, primary_key=True, index=True)
    calendar_entry_id = Column(Integer, ForeignKey("calendar_entries.id"), nullable=False, index=True)
    habit_id = Column(Integer, nullable=False, index=True)  # Reference to original habit (may be deleted)
    habit_name = Column(String(255), nullable=False)  # Historical name preservation
    completed = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    was_active_on_date = Column(Boolean, default=True, nullable=False)  # Track if habit was active on this date
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    calendar_entry = relationship("CalendarEntry", back_populates="habit_completions")
    
    # Constraints
    __table_args__ = (
        Index('idx_calendar_habit_completions_entry', 'calendar_entry_id'),
        Index('idx_calendar_habit_completions_habit', 'habit_id'),
    )

class CalendarMoodEntry(Base):
    __tablename__ = "calendar_mood_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    calendar_entry_id = Column(Integer, ForeignKey("calendar_entries.id"), nullable=False, unique=True, index=True)
    happiness = Column(Integer, CheckConstraint("happiness >= 1 AND happiness <= 5"), nullable=False)
    satisfaction = Column(Integer, CheckConstraint("satisfaction >= 1 AND satisfaction <= 5"), nullable=False)
    stress = Column(Integer, CheckConstraint("stress >= 1 AND stress <= 5"), nullable=False)
    day_rating = Column(Integer, CheckConstraint("day_rating >= 1 AND day_rating <= 10"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    calendar_entry = relationship("CalendarEntry", back_populates="mood_entry")
    
    # Constraints
    __table_args__ = (
        Index('idx_calendar_mood_entries_entry', 'calendar_entry_id'),
    ) 