from typing import List, Optional
from sqlalchemy import select, and_, extract, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, datetime, timedelta
from app.db.models import MoodEntry, User
from app.schemas.mood import MoodCreate, MoodUpdate
from app.services.time_service import TimeService

class MoodCRUD:
    @staticmethod
    async def get_mood_entries(
        db: AsyncSession, 
        user_id: int, 
        start_date: Optional[date] = None, 
        end_date: Optional[date] = None, 
        month: Optional[str] = None
    ) -> List[MoodEntry]:
        """Get most recent mood entry for each day within the date range"""
        # Base query for most recent entry per day
        subquery = select(
            MoodEntry.user_id,
            MoodEntry.entry_date,
            func.max(MoodEntry.created_at).label('max_created_at')
        ).where(
            MoodEntry.user_id == user_id
        ).group_by(
            MoodEntry.user_id, MoodEntry.entry_date
        )
        
        # Apply date filtering to subquery
        if start_date and end_date:
            subquery = subquery.where(
                and_(
                    MoodEntry.entry_date >= start_date,
                    MoodEntry.entry_date <= end_date
                )
            )
        elif start_date:
            subquery = subquery.where(MoodEntry.entry_date >= start_date)
        elif end_date:
            subquery = subquery.where(MoodEntry.entry_date <= end_date)
        elif month:
            try:
                year, month_num = map(int, month.split('-'))
                subquery = subquery.where(
                    and_(
                        extract('year', MoodEntry.entry_date) == year,
                        extract('month', MoodEntry.entry_date) == month_num
                    )
                )
            except (ValueError, AttributeError):
                pass
        
        subquery = subquery.subquery()
        
        # Join back to get full mood entry data
        query = select(MoodEntry).join(
            subquery,
            and_(
                MoodEntry.user_id == subquery.c.user_id,
                MoodEntry.entry_date == subquery.c.entry_date,
                MoodEntry.created_at == subquery.c.max_created_at
            )
        ).order_by(MoodEntry.entry_date.desc())
        
        result = await db.execute(query)
        return result.scalars().all()
    
    @staticmethod
    async def get_mood_entry(db: AsyncSession, user_id: int, entry_date: date) -> Optional[MoodEntry]:
        """Get the most recent mood entry for a specific date"""
        result = await db.execute(
            select(MoodEntry).where(
                and_(
                    MoodEntry.user_id == user_id,
                    MoodEntry.entry_date == entry_date
                )
            ).order_by(MoodEntry.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_today_mood_entry(db: AsyncSession, user: User) -> Optional[MoodEntry]:
        """Get the most recent mood entry for today in user's timezone"""
        time_service = TimeService()
        today = time_service.get_user_current_date(user)
        
        result = await db.execute(
            select(MoodEntry).where(
                and_(
                    MoodEntry.user_id == user.id,
                    MoodEntry.entry_date == today
                )
            ).order_by(MoodEntry.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def create_mood_entry(db: AsyncSession, mood: MoodCreate, user_id: int) -> MoodEntry:
        """Create a new mood entry (allows multiple per day)"""
        db_mood = MoodEntry(
            user_id=user_id,
            happiness=mood.happiness,
            focus=mood.focus,
            stress=mood.stress,
            entry_date=mood.date
        )
        db.add(db_mood)
        await db.commit()
        await db.refresh(db_mood)
        return db_mood
    
    @staticmethod
    async def create_today_mood_entry(db: AsyncSession, mood_data: dict, user: User) -> MoodEntry:
        """Create a new mood entry for today in user's timezone (allows multiple per day)"""
        time_service = TimeService()
        today = time_service.get_user_current_date(user)
        
        db_mood = MoodEntry(
            user_id=user.id,
            happiness=mood_data["happiness"],
            focus=mood_data["focus"],
            stress=mood_data["stress"],
            entry_date=today
        )
        db.add(db_mood)
        await db.commit()
        await db.refresh(db_mood)
        return db_mood
    
    @staticmethod
    async def update_mood_entry(db: AsyncSession, entry_date: date, mood: MoodUpdate, user_id: int) -> Optional[MoodEntry]:
        """Create a new mood entry (update = create new entry for the day)"""
        # Convert update data to create data
        mood_data = mood.dict(exclude_unset=True)
        if not mood_data:
            return None
            
        # Get existing entry to fill in missing values
        existing = await MoodCRUD.get_mood_entry(db, user_id, entry_date)
        if existing:
            # Fill in missing values from existing entry
            mood_data.setdefault("happiness", existing.happiness)
            mood_data.setdefault("focus", existing.focus)
            mood_data.setdefault("stress", existing.stress)
        else:
            # No existing entry, all fields required
            if not all(field in mood_data for field in ["happiness", "focus", "stress"]):
                return None
        
        # Create new entry
        db_mood = MoodEntry(
            user_id=user_id,
            happiness=mood_data["happiness"],
            focus=mood_data["focus"],
            stress=mood_data["stress"],
            entry_date=entry_date
        )
        db.add(db_mood)
        await db.commit()
        await db.refresh(db_mood)
        return db_mood
    
    @staticmethod
    async def update_today_mood_entry(db: AsyncSession, mood_data: dict, user: User) -> Optional[MoodEntry]:
        """Create a new mood entry for today (update = create new entry)"""
        time_service = TimeService()
        today = time_service.get_user_current_date(user)
        
        # Get existing entry to fill in missing values
        existing = await MoodCRUD.get_today_mood_entry(db, user)
        if existing:
            # Fill in missing values from existing entry
            mood_data.setdefault("happiness", existing.happiness)
            mood_data.setdefault("focus", existing.focus)
            mood_data.setdefault("stress", existing.stress)
        
        # Create new entry
        db_mood = MoodEntry(
            user_id=user.id,
            happiness=mood_data.get("happiness", existing.happiness if existing else 3),
            focus=mood_data.get("focus", existing.focus if existing else 3),
            stress=mood_data.get("stress", existing.stress if existing else 3),
            entry_date=today
        )
        db.add(db_mood)
        await db.commit()
        await db.refresh(db_mood)
        return db_mood
    
    @staticmethod
    async def upsert_mood_entry(db: AsyncSession, mood: MoodCreate, user_id: int) -> MoodEntry:
        """Create a new mood entry (always creates new, never updates)"""
        return await MoodCRUD.create_mood_entry(db, mood, user_id)
    
    @staticmethod
    async def delete_mood_entry(db: AsyncSession, entry_date: date, user_id: int) -> bool:
        """Delete all mood entries for a specific date"""
        result = await db.execute(
            select(MoodEntry).where(
                and_(
                    MoodEntry.user_id == user_id,
                    MoodEntry.entry_date == entry_date
                )
            )
        )
        entries = result.scalars().all()
        
        if not entries:
            return False
        
        for entry in entries:
            await db.delete(entry)
        await db.commit()
        return True
    
    @staticmethod
    async def cleanup_old_mood_entries(db: AsyncSession, user_id: int, cutoff_date: date) -> int:
        """
        Clean up old mood entries, keeping only the most recent entry per day for dates before cutoff_date.
        Returns the number of entries deleted.
        """
        # Find most recent entry per day for this user before cutoff date
        subquery = select(
            MoodEntry.user_id,
            MoodEntry.entry_date,
            func.max(MoodEntry.created_at).label('max_created_at')
        ).where(
            and_(
                MoodEntry.user_id == user_id,
                MoodEntry.entry_date < cutoff_date
            )
        ).group_by(
            MoodEntry.user_id, MoodEntry.entry_date
        ).subquery()
        
        # Get IDs of entries to keep (most recent per day)
        keep_ids_query = select(MoodEntry.id).join(
            subquery,
            and_(
                MoodEntry.user_id == subquery.c.user_id,
                MoodEntry.entry_date == subquery.c.entry_date,
                MoodEntry.created_at == subquery.c.max_created_at
            )
        )
        
        keep_ids_result = await db.execute(keep_ids_query)
        keep_ids = [row[0] for row in keep_ids_result.fetchall()]
        
        # Delete all other entries for this user before cutoff date
        if keep_ids:
            delete_query = select(MoodEntry).where(
                and_(
                    MoodEntry.user_id == user_id,
                    MoodEntry.entry_date < cutoff_date,
                    ~MoodEntry.id.in_(keep_ids)
                )
            )
        else:
            delete_query = select(MoodEntry).where(
                and_(
                    MoodEntry.user_id == user_id,
                    MoodEntry.entry_date < cutoff_date
                )
            )
        
        delete_result = await db.execute(delete_query)
        entries_to_delete = delete_result.scalars().all()
        
        deleted_count = len(entries_to_delete)
        for entry in entries_to_delete:
            await db.delete(entry)
        
        await db.commit()
        return deleted_count
    
    @staticmethod
    async def cleanup_all_users_old_entries(db: AsyncSession, cutoff_date: date) -> int:
        """
        Clean up old mood entries for all users, keeping only the most recent entry per day 
        for dates before cutoff_date. Returns total number of entries deleted.
        """
        # Get all user IDs that have mood entries
        users_result = await db.execute(
            select(MoodEntry.user_id).distinct()
        )
        user_ids = [row[0] for row in users_result.fetchall()]
        
        total_deleted = 0
        for user_id in user_ids:
            deleted = await MoodCRUD.cleanup_old_mood_entries(db, user_id, cutoff_date)
            total_deleted += deleted
        
        return total_deleted 