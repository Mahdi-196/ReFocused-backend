from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Date, 
    ForeignKey, Boolean, UniqueConstraint, Index, Float, CheckConstraint, JSON, DECIMAL
)
from sqlalchemy.orm import relationship, DeclarativeBase
from sqlalchemy.sql import func
from datetime import datetime, timedelta, timezone
from app.db.database import Base
from typing import Union

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
    
    # Mock date/time for testing - developer only features
    mock_date_enabled = Column(Boolean, default=False, nullable=False)  # Enable mock date functionality
    mock_datetime_override = Column(DateTime(timezone=True), nullable=True)  # Specific mock datetime (UTC)
    
    # Daily app interaction tracking
    current_streak = Column(Integer, default=0, nullable=False)  # Current daily interaction streak
    longest_streak = Column(Integer, default=0, nullable=False)  # All-time longest streak
    last_interaction_date = Column(Date, nullable=True)  # Last date user interacted with app (in user's timezone)
    streak_updated_at = Column(DateTime(timezone=True), nullable=True)  # When streak was last updated
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True))
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True))
    password_changed_at = Column(DateTime(timezone=True))
    password_history = relationship("PasswordHistory", back_populates="user")
    login_attempts = relationship("LoginAttempt", back_populates="user")
    security_logs = relationship("SecurityLog", back_populates="user")
    
    # Relationships
    goals_2_week = relationship("Goal2Week", back_populates="user", cascade="all, delete-orphan")
    goals_long_term = relationship("GoalLongTerm", back_populates="user", cascade="all, delete-orphan")
    quick_access = relationship("QuickAccess", back_populates="user", cascade="all, delete-orphan")
    habits = relationship("Habit", back_populates="user", cascade="all, delete-orphan")
    mood_entries = relationship("MoodEntry", back_populates="user", cascade="all, delete-orphan")
    pomodoro_settings = relationship("PomodoroSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    study_sets = relationship("StudySet", back_populates="user", cascade="all, delete-orphan")
    mantras = relationship("Mantra", back_populates="user", cascade="all, delete-orphan")
    journal_collections = relationship("JournalCollection", back_populates="user", cascade="all, delete-orphan")
    gratitude_entries = relationship("Gratitude", cascade="all, delete-orphan")
    statistics = relationship("UserStatistics", back_populates="user", cascade="all, delete-orphan")

# Base class for shared goal functionality
class GoalBase(Base):
    __abstract__ = True
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    goal_type = Column(String(20), nullable=False, index=True)  # percentage, counter, checklist
    target_value = Column(Integer, nullable=False)  # 100 for percentage, 2-999 for counter, 1 for checklist
    current_value = Column(Integer, default=0, nullable=False)  # Current progress
    is_completed = Column(Boolean, default=False, nullable=False, index=True)
    duration = Column(String(20), nullable=False, index=True)  # "2_week" or "long_term"
    
    # User relationship
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)  # Set when goal is completed
    
    # Computed property for progress percentage
    @property
    def progress_percentage(self) -> float:
        """Calculate progress as percentage (0-100)."""
        if self.target_value == 0:
            return 0.0
        return min(100.0, (self.current_value / self.target_value) * 100.0)
    
    # Base constraints for all goals
    __table_args__ = (
        CheckConstraint('goal_type IN ("percentage", "counter", "checklist")', name='chk_goal_type'),
        CheckConstraint('target_value >= 1 AND target_value <= 999', name='chk_target_value_range'),
        CheckConstraint('current_value >= 0', name='chk_current_value_positive'),
        CheckConstraint('duration IN ("two_week", "long_term")', name='chk_duration_type'),
        CheckConstraint(
            '(goal_type = "percentage" AND target_value = 100) OR '
            '(goal_type = "counter" AND target_value >= 2 AND target_value <= 999) OR '
            '(goal_type = "checklist" AND target_value = 1)',
            name='chk_goal_type_target_consistency'
        ),
    )

# 2-week goals with expiration
class Goal2Week(GoalBase):
    __tablename__ = "goals_2_week"
    
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Relationships
    user = relationship("User", back_populates="goals_2_week")
    
    # Additional constraints and indexes specific to 2-week goals
    __table_args__ = GoalBase.__table_args__ + (
        CheckConstraint('duration = "two_week"', name='chk_2week_duration'),
        Index('idx_goals_2week_user_type', 'user_id', 'goal_type'),
        Index('idx_goals_2week_user_completed', 'user_id', 'is_completed'),
        Index('idx_goals_2week_user_expires', 'user_id', 'expires_at'),
        Index('idx_goals_2week_expires_active', 'expires_at', 'is_completed'),
    )

# Long-term goals without expiration
class GoalLongTerm(GoalBase):
    __tablename__ = "goals_long_term"
    
    # Relationships
    user = relationship("User", back_populates="goals_long_term")
    
    # Additional constraints and indexes specific to long-term goals
    __table_args__ = GoalBase.__table_args__ + (
        CheckConstraint('duration = "long_term"', name='chk_longterm_duration'),
        Index('idx_goals_longterm_user_type', 'user_id', 'goal_type'),
        Index('idx_goals_longterm_user_completed', 'user_id', 'is_completed'),
    )



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
    focus = Column(Integer, nullable=False)  # 1-5
    stress = Column(Integer, nullable=False)  # 1-5
    entry_date = Column(Date, nullable=False, index=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="mood_entries")
    
    # Constraints - Removed unique constraint to allow multiple entries per day
    __table_args__ = (
        Index('idx_mood_entries_user_date', 'user_id', 'entry_date'),
        Index('idx_mood_entries_user_date_created', 'user_id', 'entry_date', 'created_at'),  # For finding most recent
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

# JournalCollection model - Enhanced version
class JournalCollection(Base):
    __tablename__ = "journal_collections"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    is_private = Column(Boolean, default=False, nullable=False)
    password_hash = Column(String, nullable=True)  # Bcrypt hashed password for private collections
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="journal_collections")
    entries = relationship("JournalEntry", back_populates="collection", cascade="all, delete-orphan")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uix_user_collection_name'),
        CheckConstraint("LENGTH(TRIM(name)) > 0 AND LENGTH(TRIM(name)) <= 100", name='chk_collection_name_length'),
        Index('idx_collections_user_id', 'user_id'),
        Index('idx_collections_user_private', 'user_id', 'is_private'),
    )

# JournalEntry model - Enhanced version
class JournalEntry(Base):
    __tablename__ = "journal_entries"
    
    id = Column(Integer, primary_key=True)
    collection_id = Column(Integer, ForeignKey("journal_collections.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)  # Rich text content
    is_encrypted = Column(Boolean, default=False, nullable=False)
    encrypted_content = Column(Text, nullable=True)  # AES encrypted content for private collections
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    collection = relationship("JournalCollection", back_populates="entries")
    
    # Constraints
    __table_args__ = (
        CheckConstraint("LENGTH(TRIM(title)) > 0 AND LENGTH(TRIM(title)) <= 200", name='chk_entry_title_length'),
        CheckConstraint("LENGTH(content) <= 50000", name='chk_entry_content_length'),
        Index('idx_entries_collection_id', 'collection_id'),
        Index('idx_entries_created_at', 'created_at'),
        Index('idx_entries_updated_at', 'updated_at'),
    )

# Gratitude model - New addition
class Gratitude(Base):
    __tablename__ = "gratitude_entries"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    text = Column(String(500), nullable=False)
    date = Column(Date, nullable=False, default=func.current_date(), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", overlaps="gratitude_entries")
    
    # Constraints
    __table_args__ = (
        CheckConstraint("LENGTH(TRIM(text)) > 0 AND LENGTH(TRIM(text)) <= 500", name='chk_gratitude_text_length'),
        Index('idx_gratitude_user_date', 'user_id', 'date'),
        Index('idx_gratitude_date', 'date'),
    )

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
    async def get_recent_attempts(cls, db, user_id: int, minutes: int):
        from sqlalchemy import select
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        result = await db.execute(
            select(cls).where(
                cls.user_id == user_id,
                cls.created_at >= cutoff
            )
        )
        return result.scalars().all()

    @classmethod
    async def create(cls, db, user_id: int, success: bool, ip_address: str):
        attempt = cls(
            user_id=user_id,
            success=success,
            ip_address=ip_address
        )
        db.add(attempt)
        await db.commit()
        return attempt

    @classmethod  
    async def record_attempt(cls, db, user_id: int, success: bool, ip_address: str):
        return await cls.create(db, user_id, success, ip_address)

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

class DeletedEmail(Base):
    __tablename__ = "deleted_emails"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    deleted_at = Column(DateTime(timezone=True), server_default=func.now())
    original_user_id = Column(Integer, nullable=False)  # Store the original user ID for reference
    
    @classmethod
    async def is_email_recently_deleted(cls, db, email: str) -> Union[bool, dict]:
        """Check if an email was deleted within the last 72 hours"""
        from sqlalchemy import select
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=72)
        result = await db.execute(
            select(cls).where(
                cls.email == email,
                cls.deleted_at > cutoff_time
            )
        )
        deleted_email = result.scalar_one_or_none()
        if deleted_email:
            # Calculate hours remaining until the email can be used again
            hours_since_deletion = (datetime.now(timezone.utc) - deleted_email.deleted_at).total_seconds() / 3600
            hours_remaining = 72 - hours_since_deletion
            return {
                "is_deleted": True,
                "hours_remaining": max(0, round(hours_remaining, 1)),
                "deleted_at": deleted_email.deleted_at.isoformat(),
                "available_at": (deleted_email.deleted_at + timedelta(hours=72)).isoformat()
            }
        return {"is_deleted": False}
    
    @classmethod
    async def add_deleted_email(cls, db, email: str, user_id: int):
        """Record a deleted email address"""
        deleted_email = cls(email=email, original_user_id=user_id)
        db.add(deleted_email)
        await db.commit()
        return deleted_email
    
    @classmethod
    async def cleanup_expired_entries(cls, db):
        """Remove entries older than 72 hours"""
        from sqlalchemy import delete
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=72)
        await db.execute(
            delete(cls).where(cls.deleted_at <= cutoff_time)
        )
        await db.commit()

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
    async def log_event(cls, db, event_type: str, ip_address: str, user_id: int = None,
                 user_agent: str = None, details: str = None):
        log = cls(
            user_id=user_id,
            event_type=event_type,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details
        )
        db.add(log)
        await db.commit()
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
    async def create_alert(cls, db, alert_type: str, severity: str, description: str,
                    ip_address: str = None, user_id: int = None):
        alert = cls(
            alert_type=alert_type,
            severity=severity,
            description=description,
            ip_address=ip_address,
            user_id=user_id
        )
        db.add(alert)
        await db.commit()
        return alert
    
    async def resolve(self, db):
        self.resolved = True
        self.resolved_at = datetime.utcnow()
        await db.commit()
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
    focus = Column(Integer, CheckConstraint("focus >= 1 AND focus <= 5"), nullable=False)
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

# UserDailyStreak model - tracks detailed daily interaction history
class UserDailyStreak(Base):
    __tablename__ = "user_daily_streaks"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)  # User's local date
    interaction_count = Column(Integer, default=0, nullable=False)  # Number of meaningful interactions that day
    first_interaction = Column(DateTime(timezone=True), nullable=True)  # First interaction of the day
    last_interaction = Column(DateTime(timezone=True), nullable=True)  # Last interaction of the day
    interaction_types = Column(JSON, nullable=False, default=list)  # List of interaction types that day
    timezone = Column(String(50), nullable=False)  # User's timezone when interaction occurred
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'date', name='uix_user_daily_streak_date'),
        Index('idx_user_daily_streaks_user_date', 'user_id', 'date'),
    )

 