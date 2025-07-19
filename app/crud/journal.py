from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import and_, or_, desc, func, case, select
from fastapi import HTTPException, status
import bcrypt
from cryptography.fernet import Fernet
import base64
import hashlib

from app.db.models import JournalCollection, JournalEntry, Gratitude, User
from app.schemas.journal import (
    JournalCollectionCreate, JournalCollectionUpdate,
    JournalEntryCreate, JournalEntryUpdate,
    GratitudeCreate, GratitudeUpdate
)


class SecurityService:
    """Handle encryption and password hashing for journal security"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    
    @staticmethod
    def generate_key_from_password(password: str, salt: bytes = None) -> bytes:
        """Generate encryption key from password"""
        if salt is None:
            salt = b'journal_salt_2024'  # Use consistent salt for same password
        key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        return base64.urlsafe_b64encode(key)
    
    @staticmethod
    def encrypt_content(content: str, password: str) -> str:
        """Encrypt content using password-derived key"""
        key = SecurityService.generate_key_from_password(password)
        fernet = Fernet(key)
        encrypted_data = fernet.encrypt(content.encode())
        return base64.b64encode(encrypted_data).decode()
    
    @staticmethod
    def decrypt_content(encrypted_content: str, password: str) -> str:
        """Decrypt content using password-derived key"""
        try:
            key = SecurityService.generate_key_from_password(password)
            fernet = Fernet(key)
            encrypted_data = base64.b64decode(encrypted_content.encode())
            decrypted_data = fernet.decrypt(encrypted_data)
            return decrypted_data.decode()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password or corrupted data"
            )


class JournalCollectionCRUD:
    """CRUD operations for journal collections"""
    
    @staticmethod
    async def create(db: AsyncSession, collection: JournalCollectionCreate, user_id: int) -> JournalCollection:
        """Create a new journal collection"""
        # Check for duplicate collection name for user
        stmt = select(JournalCollection).where(
            and_(
                JournalCollection.user_id == user_id,
                JournalCollection.name == collection.name.strip()
            )
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Collection with this name already exists"
            )
        
        # Hash password if collection is private
        password_hash = None
        if collection.is_private and collection.password:
            password_hash = SecurityService.hash_password(collection.password)
        
        db_collection = JournalCollection(
            user_id=user_id,
            name=collection.name.strip(),
            is_private=collection.is_private,
            password_hash=password_hash
        )
        
        db.add(db_collection)
        await db.commit()
        await db.refresh(db_collection)
        return db_collection
    
    @staticmethod
    async def get_by_id(db: AsyncSession, collection_id: int, user_id: int) -> Optional[JournalCollection]:
        """Get collection by ID for a specific user"""
        stmt = select(JournalCollection).where(
            and_(
                JournalCollection.id == collection_id,
                JournalCollection.user_id == user_id
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_collections(
        db: AsyncSession, 
        user_id: int, 
        skip: int = 0, 
        limit: int = 20
    ) -> tuple[List[JournalCollection], int]:
        """Get user's collections with pagination, ensuring 'My Notes' is first"""
        # Get total count
        count_stmt = select(func.count(JournalCollection.id)).where(JournalCollection.user_id == user_id)
        count_result = await db.execute(count_stmt)
        total = count_result.scalar()
        
        # Get collections with entries
        stmt = select(JournalCollection).options(
            selectinload(JournalCollection.entries)
        ).where(JournalCollection.user_id == user_id).order_by(
            desc(JournalCollection.updated_at)
        ).offset(skip).limit(limit)
        
        result = await db.execute(stmt)
        collections = result.scalars().all()
        
        # Add entry count to each collection
        for collection in collections:
            collection.entry_count = len(collection.entries)
        
        # Ensure "My Notes" is always first (only for first page)
        if skip == 0:
            my_notes = [c for c in collections if c.name == "My Notes"]
            others = [c for c in collections if c.name != "My Notes"]
            collections = my_notes + others
        
        return collections, total
    
    @staticmethod
    async def update(
        db: AsyncSession, 
        collection_id: int, 
        user_id: int, 
        collection_update: JournalCollectionUpdate
    ) -> Optional[JournalCollection]:
        """Update a journal collection"""
        db_collection = await JournalCollectionCRUD.get_by_id(db, collection_id, user_id)
        if not db_collection:
            return None
        
        # Verify current password if changing private settings or password
        if collection_update.current_password and db_collection.password_hash:
            if not SecurityService.verify_password(
                collection_update.current_password, 
                db_collection.password_hash
            ):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Current password is incorrect"
                )
        
        # Update fields
        if collection_update.name is not None:
            # Check for duplicate name
            stmt = select(JournalCollection).where(
                and_(
                    JournalCollection.user_id == user_id,
                    JournalCollection.name == collection_update.name.strip(),
                    JournalCollection.id != collection_id
                )
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Collection with this name already exists"
                )
            
            db_collection.name = collection_update.name.strip()
        
        if collection_update.is_private is not None:
            db_collection.is_private = collection_update.is_private
        
        # Update password if provided
        if collection_update.new_password:
            db_collection.password_hash = SecurityService.hash_password(collection_update.new_password)
        elif collection_update.is_private is False:
            db_collection.password_hash = None
        
        db_collection.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(db_collection)
        return db_collection
    
    @staticmethod
    async def delete(db: AsyncSession, collection_id: int, user_id: int) -> bool:
        """Delete a journal collection"""
        db_collection = await JournalCollectionCRUD.get_by_id(db, collection_id, user_id)
        if not db_collection:
            return False
        
        await db.delete(db_collection)
        await db.commit()
        return True
    
    @staticmethod
    async def verify_password(
        db: AsyncSession, 
        collection_id: int, 
        user_id: int, 
        password: str
    ) -> bool:
        """Verify collection password"""
        db_collection = await JournalCollectionCRUD.get_by_id(db, collection_id, user_id)
        if not db_collection or not db_collection.password_hash:
            return False
        
        return SecurityService.verify_password(password, db_collection.password_hash)
    
    @staticmethod
    async def create_default_collection(db: AsyncSession, user_id: int) -> JournalCollection:
        """Create default 'My Notes' collection for new users"""
        default_collection = JournalCollectionCreate(
            name="My Notes",
            is_private=False
        )
        return await JournalCollectionCRUD.create(db, default_collection, user_id)


class JournalEntryCRUD:
    """CRUD operations for journal entries"""
    
    @staticmethod
    async def create(db: AsyncSession, entry: JournalEntryCreate, user_id: int, user: User) -> JournalEntry:
        """Create a new journal entry"""
        # Validate input
        if not entry.title or not entry.title.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Title cannot be empty"
            )
        
        if not entry.content or not entry.content.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Content cannot be empty"
            )
        
        # Verify collection ownership
        collection = await JournalCollectionCRUD.get_by_id(db, entry.collection_id, user_id)
        if not collection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collection not found"
            )
        
        # Handle encryption for private collections
        is_encrypted = False
        encrypted_content = None
        content = entry.content
        
        # Use frontend's preference if provided, otherwise auto-determine based on collection
        if entry.is_encrypted is not None:
            is_encrypted = entry.is_encrypted
        elif collection.is_private and collection.password_hash:
            # For now, we'll store unencrypted but mark as encrypted
            # Real encryption would need the password from frontend
            is_encrypted = True
        
        from app.services.time_service import TimeService
        current_time = TimeService.get_current_time_for_user(user)
        
        db_entry = JournalEntry(
            collection_id=entry.collection_id,
            title=entry.title.strip() if entry.title else None,
            content=content,
            encrypted_content=encrypted_content,
            is_encrypted=is_encrypted,
            created_at=current_time,
            updated_at=current_time
        )
        
        db.add(db_entry)
        await db.commit()
        await db.refresh(db_entry)
        return db_entry
    
    @staticmethod
    async def get_by_id(
        db: AsyncSession, 
        entry_id: int, 
        user_id: int,
        password: Optional[str] = None
    ) -> Optional[JournalEntry]:
        """Get entry by ID with optional decryption"""
        stmt = select(JournalEntry).join(JournalCollection).options(
            joinedload(JournalEntry.collection)
        ).where(
            and_(
                JournalEntry.id == entry_id,
                JournalCollection.user_id == user_id
            )
        )
        result = await db.execute(stmt)
        entry = result.scalar_one_or_none()
        
        if not entry:
            return None
        
        # Decrypt content if needed
        if entry.is_encrypted and entry.encrypted_content and password:
            try:
                entry.content = SecurityService.decrypt_content(entry.encrypted_content, password)
            except Exception:
                # Return entry with encrypted content if decryption fails
                pass
        
        return entry
    
    @staticmethod
    async def get_collection_entries(
        db: AsyncSession,
        collection_id: int,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        password: Optional[str] = None
    ) -> tuple[List[JournalEntry], int]:
        """Get entries for a specific collection"""
        # Verify collection ownership
        collection = await JournalCollectionCRUD.get_by_id(db, collection_id, user_id)
        if not collection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collection not found"
            )
        
        stmt = select(JournalEntry).filter(JournalEntry.collection_id == collection_id).order_by(
            desc(JournalEntry.updated_at)
        ).offset(skip).limit(limit)
        
        result = await db.execute(stmt)
        entries = result.scalars().all()
        
        # Decrypt entries if needed
        if collection.is_private and password:
            for entry in entries:
                if entry.is_encrypted and entry.encrypted_content:
                    try:
                        entry.content = SecurityService.decrypt_content(entry.encrypted_content, password)
                    except Exception:
                        pass
        
        return entries, len(entries)
    
    @staticmethod
    async def get_user_entries(
        db: AsyncSession,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None
    ) -> tuple[List[JournalEntry], int]:
        """Get all user's entries with optional search"""
        stmt = select(JournalEntry).join(JournalCollection).filter(
            JournalCollection.user_id == user_id
        )
        
        if search:
            search_filter = or_(
                JournalEntry.title.ilike(f"%{search}%"),
                JournalEntry.content.ilike(f"%{search}%")
            )
            stmt = stmt.filter(search_filter)
        
        result = await db.execute(stmt.order_by(desc(JournalEntry.updated_at)).offset(skip).limit(limit))
        entries = result.scalars().all()
        
        return entries, len(entries)
    
    @staticmethod
    async def update(
        db: AsyncSession,
        entry_id: int,
        user_id: int,
        entry_update: JournalEntryUpdate,
        user: User,
        password: Optional[str] = None
    ) -> Optional[JournalEntry]:
        """Update a journal entry"""
        entry = await JournalEntryCRUD.get_by_id(db, entry_id, user_id, password)
        if not entry:
            return None
        
        # Update fields
        if entry_update.title is not None:
            entry.title = entry_update.title.strip()
        
        if entry_update.content is not None:
            entry.content = entry_update.content
            
            # Re-encrypt if needed
            if entry.is_encrypted and password:
                entry.encrypted_content = SecurityService.encrypt_content(
                    entry_update.content, password
                )
        
        from app.services.time_service import TimeService
        entry.updated_at = TimeService.get_current_time_for_user(user)
        
        # Update collection timestamp
        collection_stmt = select(JournalCollection).where(JournalCollection.id == entry.collection_id)
        collection_result = await db.execute(collection_stmt)
        collection = collection_result.scalar_one_or_none()
        if collection:
            collection.updated_at = TimeService.get_current_time_for_user(user)
        
        await db.commit()
        await db.refresh(entry)
        return entry
    
    @staticmethod
    async def delete(db: AsyncSession, entry_id: int, user_id: int) -> bool:
        """Delete a journal entry"""
        entry_stmt = select(JournalEntry).join(JournalCollection).where(
            and_(
                JournalEntry.id == entry_id,
                JournalCollection.user_id == user_id
            )
        )
        entry_result = await db.execute(entry_stmt)
        entry = entry_result.scalar_one_or_none()
        
        if not entry:
            return False
        
        # Update collection timestamp
        collection_stmt = select(JournalCollection).where(JournalCollection.id == entry.collection_id)
        collection_result = await db.execute(collection_stmt)
        collection = collection_result.scalar_one_or_none()
        if collection:
            collection.updated_at = datetime.utcnow()
        
        await db.delete(entry)
        await db.commit()
        return True


class GratitudeCRUD:
    """CRUD operations for gratitude entries"""
    
    @staticmethod
    async def create(db: AsyncSession, gratitude: GratitudeCreate, user_id: int) -> Gratitude:
        """Create a new gratitude entry"""
        # Set date to today if not provided
        entry_date = gratitude.date if gratitude.date else date.today()
        
        db_gratitude = Gratitude(
            user_id=user_id,
            text=gratitude.text.strip() if gratitude.text else "",
            date=entry_date
        )
        
        db.add(db_gratitude)
        await db.commit()
        await db.refresh(db_gratitude)
        return db_gratitude
    
    @staticmethod
    async def get_by_id(db: AsyncSession, gratitude_id: int, user_id: int) -> Optional[Gratitude]:
        """Get gratitude by ID"""
        stmt = select(Gratitude).where(
            and_(
                Gratitude.id == gratitude_id,
                Gratitude.user_id == user_id
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_gratitude(
        db: AsyncSession,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> tuple[List[Gratitude], int]:
        """Get user's gratitude entries with optional date filtering"""
        stmt = select(Gratitude).filter(Gratitude.user_id == user_id)
        
        if start_date:
            stmt = stmt.filter(Gratitude.date >= start_date)
        if end_date:
            stmt = stmt.filter(Gratitude.date <= end_date)
        
        result = await db.execute(stmt.order_by(desc(Gratitude.date)).offset(skip).limit(limit))
        gratitude_entries = result.scalars().all()
        
        return gratitude_entries, len(gratitude_entries)
    
    @staticmethod
    async def update(
        db: AsyncSession,
        gratitude_id: int,
        user_id: int,
        gratitude_update: GratitudeUpdate
    ) -> Optional[Gratitude]:
        """Update a gratitude entry"""
        db_gratitude = await GratitudeCRUD.get_by_id(db, gratitude_id, user_id)
        if not db_gratitude:
            return None
        
        if gratitude_update.text is not None:
            db_gratitude.text = gratitude_update.text.strip()
        
        await db.commit()
        await db.refresh(db_gratitude)
        return db_gratitude
    
    @staticmethod
    async def delete(db: AsyncSession, gratitude_id: int, user_id: int) -> bool:
        """Delete a gratitude entry"""
        db_gratitude = await GratitudeCRUD.get_by_id(db, gratitude_id, user_id)
        if not db_gratitude:
            return False
        
        await db.delete(db_gratitude)
        await db.commit()
        return True
    
    @staticmethod
    async def get_gratitude_streak(db: AsyncSession, user_id: int) -> int:
        """Calculate user's gratitude streak"""
        today = date.today()
        streak = 0
        current_date = today
        
        while True:
            stmt = select(Gratitude).where(
                and_(
                    Gratitude.user_id == user_id,
                    Gratitude.date == current_date
                )
            )
            result = await db.execute(stmt)
            exists = result.scalar_one_or_none()
            
            if exists:
                streak += 1
                current_date -= timedelta(days=1)
            else:
                break
        
        return streak


class JournalStatsCRUD:
    """Statistics and analytics for journal data"""
    
    @staticmethod
    async def get_user_stats(db: AsyncSession, user_id: int) -> Dict[str, Any]:
        """Get comprehensive journal statistics for user"""
        today = date.today()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        # Collection stats
        total_collections_stmt = select(func.count(JournalCollection.id)).where(
            JournalCollection.user_id == user_id
        )
        total_collections_result = await db.execute(total_collections_stmt)
        total_collections = total_collections_result.scalar()
        
        private_collections_stmt = select(func.count(JournalCollection.id)).where(
            and_(
                JournalCollection.user_id == user_id,
                JournalCollection.is_private == True
            )
        )
        private_collections_result = await db.execute(private_collections_stmt)
        private_collections = private_collections_result.scalar()
        
        # Entry stats
        total_entries_stmt = select(func.count(JournalEntry.id)).join(JournalCollection).where(
            JournalCollection.user_id == user_id
        )
        total_entries_result = await db.execute(total_entries_stmt)
        total_entries = total_entries_result.scalar()
        
        entries_this_week_stmt = select(func.count(JournalEntry.id)).join(JournalCollection).where(
            and_(
                JournalCollection.user_id == user_id,
                JournalEntry.created_at >= week_ago
            )
        )
        entries_this_week_result = await db.execute(entries_this_week_stmt)
        entries_this_week = entries_this_week_result.scalar()
        
        entries_this_month_stmt = select(func.count(JournalEntry.id)).join(JournalCollection).where(
            and_(
                JournalCollection.user_id == user_id,
                JournalEntry.created_at >= month_ago
            )
        )
        entries_this_month_result = await db.execute(entries_this_month_stmt)
        entries_this_month = entries_this_month_result.scalar()
        
        # Gratitude stats
        total_gratitude_stmt = select(func.count(Gratitude.id)).where(Gratitude.user_id == user_id)
        total_gratitude_result = await db.execute(total_gratitude_stmt)
        total_gratitude = total_gratitude_result.scalar()
        
        gratitude_this_week_stmt = select(func.count(Gratitude.id)).where(
            and_(
                Gratitude.user_id == user_id,
                Gratitude.date >= week_ago
            )
        )
        gratitude_this_week_result = await db.execute(gratitude_this_week_stmt)
        gratitude_this_week = gratitude_this_week_result.scalar()
        
        # Gratitude streak
        gratitude_streak = await GratitudeCRUD.get_gratitude_streak(db, user_id)
        
        return {
            "total_collections": total_collections,
            "total_entries": total_entries,
            "total_gratitude": total_gratitude,
            "private_collections": private_collections,
            "entries_this_week": entries_this_week,
            "entries_this_month": entries_this_month,
            "gratitude_this_week": gratitude_this_week,
            "gratitude_streak": gratitude_streak
        } 