from typing import List, Optional
from sqlalchemy import select, and_, extract
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, datetime
from app.db.models import MoodEntry
from app.schemas.mood import MoodCreate, MoodUpdate

class MoodCRUD:
    @staticmethod
    async def get_mood_entries(
        db: AsyncSession, 
        user_id: int, 
        start_date: Optional[date] = None, 
        end_date: Optional[date] = None, 
        month: Optional[str] = None
    ) -> List[MoodEntry]:
        """Get mood entries for a user with optional date range filtering"""
        query = select(MoodEntry).where(MoodEntry.user_id == user_id)
        
        # Date range filtering takes priority over month filtering
        if start_date and end_date:
            query = query.where(
                and_(
                    MoodEntry.entry_date >= start_date,
                    MoodEntry.entry_date <= end_date
                )
            )
        elif start_date:
            query = query.where(MoodEntry.entry_date >= start_date)
        elif end_date:
            query = query.where(MoodEntry.entry_date <= end_date)
        elif month:
            # Fallback to month filtering if no date range provided
            try:
                year, month_num = map(int, month.split('-'))
                query = query.where(
                    and_(
                        extract('year', MoodEntry.entry_date) == year,
                        extract('month', MoodEntry.entry_date) == month_num
                    )
                )
            except (ValueError, AttributeError):
                # Invalid month format, return all entries
                pass
        
        result = await db.execute(query.order_by(MoodEntry.entry_date.desc()))
        return result.scalars().all()
    
    @staticmethod
    async def get_mood_entry(db: AsyncSession, user_id: int, entry_date: date) -> Optional[MoodEntry]:
        """Get mood entry for a specific date"""
        result = await db.execute(
            select(MoodEntry).where(
                and_(
                    MoodEntry.user_id == user_id,
                    MoodEntry.entry_date == entry_date
                )
            )
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def create_mood_entry(db: AsyncSession, mood: MoodCreate, user_id: int) -> MoodEntry:
        """Create a new mood entry with default values for optional fields"""
        db_mood = MoodEntry(
            user_id=user_id,
            happiness=mood.happiness,
            satisfaction=mood.satisfaction,
            stress=mood.stress,
            day_rating=3,  # Default middle value
            entry_date=mood.date,
            note=""  # Default empty note
        )
        db.add(db_mood)
        await db.commit()
        await db.refresh(db_mood)
        return db_mood
    
    @staticmethod
    async def update_mood_entry(db: AsyncSession, entry_date: date, mood: MoodUpdate, user_id: int) -> Optional[MoodEntry]:
        """Update a mood entry for a specific date"""
        result = await db.execute(
            select(MoodEntry).where(
                and_(
                    MoodEntry.user_id == user_id,
                    MoodEntry.entry_date == entry_date
                )
            )
        )
        db_mood = result.scalar_one_or_none()
        
        if not db_mood:
            return None
        
        # Only update fields that are provided
        update_data = mood.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_mood, field, value)
        
        await db.commit()
        await db.refresh(db_mood)
        return db_mood
    
    @staticmethod
    async def upsert_mood_entry(db: AsyncSession, mood: MoodCreate, user_id: int) -> MoodEntry:
        """Create or update a mood entry for a specific date"""
        # Try to get existing entry
        existing = await MoodCRUD.get_mood_entry(db, user_id, mood.date)
        
        if existing:
            # Update existing entry
            existing.happiness = mood.happiness
            existing.satisfaction = mood.satisfaction
            existing.stress = mood.stress
            # Keep existing day_rating and note if they exist
            
            await db.commit()
            await db.refresh(existing)
            return existing
        else:
            # Create new entry
            return await MoodCRUD.create_mood_entry(db, mood, user_id)
    
    @staticmethod
    async def delete_mood_entry(db: AsyncSession, entry_date: date, user_id: int) -> bool:
        """Delete a mood entry for a specific date"""
        result = await db.execute(
            select(MoodEntry).where(
                and_(
                    MoodEntry.user_id == user_id,
                    MoodEntry.entry_date == entry_date
                )
            )
        )
        db_mood = result.scalar_one_or_none()
        
        if not db_mood:
            return False
        
        await db.delete(db_mood)
        await db.commit()
        return True 