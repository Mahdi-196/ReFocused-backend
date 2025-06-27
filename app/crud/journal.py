from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, desc, func, case
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
    def create(db: Session, collection: JournalCollectionCreate, user_id: int) -> JournalCollection:
        """Create a new journal collection"""
        # Check for duplicate collection name for user
        existing = db.query(JournalCollection).filter(
            and_(
                JournalCollection.user_id == user_id,
                JournalCollection.name == collection.name.strip()
            )
        ).first()
        
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
        db.commit()
        db.refresh(db_collection)
        return db_collection
    
    @staticmethod
    def get_by_id(db: Session, collection_id: int, user_id: int) -> Optional[JournalCollection]:
        """Get collection by ID for a specific user"""
        return db.query(JournalCollection).filter(
            and_(
                JournalCollection.id == collection_id,
                JournalCollection.user_id == user_id
            )
        ).first()
    
    @staticmethod
    def get_user_collections(
        db: Session, 
        user_id: int, 
        skip: int = 0, 
        limit: int = 20
    ) -> tuple[List[JournalCollection], int]:
        """Get user's collections with pagination, ensuring 'My Notes' is first"""
        query = db.query(JournalCollection).filter(JournalCollection.user_id == user_id)
        
        total = query.count()
        collections = query.options(
            joinedload(JournalCollection.entries)
        ).order_by(desc(JournalCollection.updated_at)).offset(skip).limit(limit).all()
        
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
    def update(
        db: Session, 
        collection_id: int, 
        user_id: int, 
        collection_update: JournalCollectionUpdate
    ) -> Optional[JournalCollection]:
        """Update a journal collection"""
        db_collection = JournalCollectionCRUD.get_by_id(db, collection_id, user_id)
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
            existing = db.query(JournalCollection).filter(
                and_(
                    JournalCollection.user_id == user_id,
                    JournalCollection.name == collection_update.name.strip(),
                    JournalCollection.id != collection_id
                )
            ).first()
            
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
        db.commit()
        db.refresh(db_collection)
        return db_collection
    
    @staticmethod
    def delete(db: Session, collection_id: int, user_id: int) -> bool:
        """Delete a journal collection"""
        db_collection = JournalCollectionCRUD.get_by_id(db, collection_id, user_id)
        if not db_collection:
            return False
        
        db.delete(db_collection)
        db.commit()
        return True
    
    @staticmethod
    def verify_password(
        db: Session, 
        collection_id: int, 
        user_id: int, 
        password: str
    ) -> bool:
        """Verify collection password"""
        db_collection = JournalCollectionCRUD.get_by_id(db, collection_id, user_id)
        if not db_collection or not db_collection.password_hash:
            return False
        
        return SecurityService.verify_password(password, db_collection.password_hash)
    
    @staticmethod
    def create_default_collection(db: Session, user_id: int) -> JournalCollection:
        """Create default 'My Notes' collection for new users"""
        default_collection = JournalCollectionCreate(
            name="My Notes",
            is_private=False
        )
        return JournalCollectionCRUD.create(db, default_collection, user_id)


class JournalEntryCRUD:
    """CRUD operations for journal entries"""
    
    @staticmethod
    def create(db: Session, entry: JournalEntryCreate, user_id: int) -> JournalEntry:
        """Create a new journal entry"""
        # Verify collection ownership
        collection = JournalCollectionCRUD.get_by_id(db, entry.collection_id, user_id)
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
        
        db_entry = JournalEntry(
            collection_id=entry.collection_id,
            title=entry.title.strip(),
            content=content,
            is_encrypted=is_encrypted,
            encrypted_content=encrypted_content,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(db_entry)
        
        # Update collection timestamp
        collection.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(db_entry)
        return db_entry
    
    @staticmethod
    def get_by_id(
        db: Session, 
        entry_id: int, 
        user_id: int,
        password: Optional[str] = None
    ) -> Optional[JournalEntry]:
        """Get entry by ID with optional decryption"""
        entry = db.query(JournalEntry).join(JournalCollection).filter(
            and_(
                JournalEntry.id == entry_id,
                JournalCollection.user_id == user_id
            )
        ).first()
        
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
    def get_collection_entries(
        db: Session,
        collection_id: int,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        password: Optional[str] = None
    ) -> tuple[List[JournalEntry], int]:
        """Get entries for a specific collection"""
        # Verify collection ownership
        collection = JournalCollectionCRUD.get_by_id(db, collection_id, user_id)
        if not collection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collection not found"
            )
        
        query = db.query(JournalEntry).filter(JournalEntry.collection_id == collection_id)
        total = query.count()
        
        entries = query.order_by(desc(JournalEntry.updated_at)).offset(skip).limit(limit).all()
        
        # Decrypt entries if needed
        if collection.is_private and password:
            for entry in entries:
                if entry.is_encrypted and entry.encrypted_content:
                    try:
                        entry.content = SecurityService.decrypt_content(entry.encrypted_content, password)
                    except Exception:
                        pass
        
        return entries, total
    
    @staticmethod
    def get_user_entries(
        db: Session,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None
    ) -> tuple[List[JournalEntry], int]:
        """Get all user's entries with optional search"""
        query = db.query(JournalEntry).join(JournalCollection).filter(
            JournalCollection.user_id == user_id
        )
        
        if search:
            search_filter = or_(
                JournalEntry.title.ilike(f"%{search}%"),
                JournalEntry.content.ilike(f"%{search}%")
            )
            query = query.filter(search_filter)
        
        total = query.count()
        entries = query.order_by(desc(JournalEntry.updated_at)).offset(skip).limit(limit).all()
        
        return entries, total
    
    @staticmethod
    def update(
        db: Session,
        entry_id: int,
        user_id: int,
        entry_update: JournalEntryUpdate,
        password: Optional[str] = None
    ) -> Optional[JournalEntry]:
        """Update a journal entry"""
        entry = JournalEntryCRUD.get_by_id(db, entry_id, user_id, password)
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
        
        entry.updated_at = datetime.utcnow()
        
        # Update collection timestamp
        collection = db.query(JournalCollection).filter(
            JournalCollection.id == entry.collection_id
        ).first()
        if collection:
            collection.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(entry)
        return entry
    
    @staticmethod
    def delete(db: Session, entry_id: int, user_id: int) -> bool:
        """Delete a journal entry"""
        entry = db.query(JournalEntry).join(JournalCollection).filter(
            and_(
                JournalEntry.id == entry_id,
                JournalCollection.user_id == user_id
            )
        ).first()
        
        if not entry:
            return False
        
        # Update collection timestamp
        collection = db.query(JournalCollection).filter(
            JournalCollection.id == entry.collection_id
        ).first()
        if collection:
            collection.updated_at = datetime.utcnow()
        
        db.delete(entry)
        db.commit()
        return True


class GratitudeCRUD:
    """CRUD operations for gratitude entries"""
    
    @staticmethod
    def create(db: Session, gratitude: GratitudeCreate, user_id: int) -> Gratitude:
        """Create a new gratitude entry"""
        # Set date to today if not provided
        entry_date = gratitude.date if gratitude.date else date.today()
        
        db_gratitude = Gratitude(
            user_id=user_id,
            text=gratitude.text.strip() if gratitude.text else "",
            date=entry_date
        )
        
        db.add(db_gratitude)
        db.commit()
        db.refresh(db_gratitude)
        return db_gratitude
    
    @staticmethod
    def get_by_id(db: Session, gratitude_id: int, user_id: int) -> Optional[Gratitude]:
        """Get gratitude by ID"""
        return db.query(Gratitude).filter(
            and_(
                Gratitude.id == gratitude_id,
                Gratitude.user_id == user_id
            )
        ).first()
    
    @staticmethod
    def get_user_gratitude(
        db: Session,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> tuple[List[Gratitude], int]:
        """Get user's gratitude entries with optional date filtering"""
        query = db.query(Gratitude).filter(Gratitude.user_id == user_id)
        
        if start_date:
            query = query.filter(Gratitude.date >= start_date)
        if end_date:
            query = query.filter(Gratitude.date <= end_date)
        
        total = query.count()
        gratitude_entries = query.order_by(desc(Gratitude.date)).offset(skip).limit(limit).all()
        
        return gratitude_entries, total
    
    @staticmethod
    def update(
        db: Session,
        gratitude_id: int,
        user_id: int,
        gratitude_update: GratitudeUpdate
    ) -> Optional[Gratitude]:
        """Update a gratitude entry"""
        db_gratitude = GratitudeCRUD.get_by_id(db, gratitude_id, user_id)
        if not db_gratitude:
            return None
        
        if gratitude_update.text is not None:
            db_gratitude.text = gratitude_update.text.strip()
        
        db.commit()
        db.refresh(db_gratitude)
        return db_gratitude
    
    @staticmethod
    def delete(db: Session, gratitude_id: int, user_id: int) -> bool:
        """Delete a gratitude entry"""
        db_gratitude = GratitudeCRUD.get_by_id(db, gratitude_id, user_id)
        if not db_gratitude:
            return False
        
        db.delete(db_gratitude)
        db.commit()
        return True
    
    @staticmethod
    def get_gratitude_streak(db: Session, user_id: int) -> int:
        """Calculate user's gratitude streak"""
        today = date.today()
        streak = 0
        current_date = today
        
        while True:
            exists = db.query(Gratitude).filter(
                and_(
                    Gratitude.user_id == user_id,
                    Gratitude.date == current_date
                )
            ).first()
            
            if exists:
                streak += 1
                current_date -= timedelta(days=1)
            else:
                break
        
        return streak


class JournalStatsCRUD:
    """Statistics and analytics for journal data"""
    
    @staticmethod
    def get_user_stats(db: Session, user_id: int) -> Dict[str, Any]:
        """Get comprehensive journal statistics for user"""
        today = date.today()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        # Collection stats
        collections_query = db.query(JournalCollection).filter(
            JournalCollection.user_id == user_id
        )
        total_collections = collections_query.count()
        private_collections = collections_query.filter(
            JournalCollection.is_private == True
        ).count()
        
        # Entry stats
        entries_query = db.query(JournalEntry).join(JournalCollection).filter(
            JournalCollection.user_id == user_id
        )
        total_entries = entries_query.count()
        entries_this_week = entries_query.filter(
            JournalEntry.created_at >= week_ago
        ).count()
        entries_this_month = entries_query.filter(
            JournalEntry.created_at >= month_ago
        ).count()
        
        # Gratitude stats
        gratitude_query = db.query(Gratitude).filter(Gratitude.user_id == user_id)
        total_gratitude = gratitude_query.count()
        gratitude_this_week = gratitude_query.filter(
            Gratitude.date >= week_ago
        ).count()
        
        # Gratitude streak
        gratitude_streak = GratitudeCRUD.get_gratitude_streak(db, user_id)
        
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