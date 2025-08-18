from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.crud.journal import JournalCollectionCRUD
from app.schemas.journal import JournalCollectionCreate
from app.db.models import JournalCollection


class JournalService:
    """Business logic for journal operations"""
    
    @staticmethod
    def setup_user_journal(db: Session, user_id: int) -> None:
        """Set up default journal structure for a new user (sync version)"""
        try:
            # Check if user already has collections
            existing_collections, _ = JournalCollectionCRUD.get_user_collections(db, user_id, 0, 1)
            
            if not existing_collections:
                # Create default "My Notes" collection
                default_collection = JournalCollectionCreate(
                    name="My Notes",
                    is_private=False
                )
                JournalCollectionCRUD.create(db, default_collection, user_id)
                
        except Exception as e:
            # Log error but don't break user registration
            pass
    
    @staticmethod
    async def setup_user_journal_async(db: AsyncSession, user_id: int) -> None:
        """Set up default journal structure for a new user (async version)"""
        try:
            # Check if user already has collections
            result = await db.execute(
                select(JournalCollection).where(JournalCollection.user_id == user_id).limit(1)
            )
            existing_collection = result.scalar_one_or_none()
            
            if not existing_collection:
                # Create default "My Notes" collection
                from datetime import datetime
                default_collection = JournalCollection(
                    user_id=user_id,
                    name="My Notes",
                    is_private=False,
                    password_hash=None,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(default_collection)
                await db.commit()
                
        except Exception as e:
            # Log error but don't break user registration
            pass
    
    @staticmethod
    def validate_collection_access(
        db: Session,
        collection_id: int,
        user_id: int,
        access_token: str = None
    ) -> bool:
        """Validate user access to a collection"""
        collection = JournalCollectionCRUD.get_by_id(db, collection_id, user_id)
        
        if not collection:
            return False
        
        # Public collections are always accessible by owner
        if not collection.is_private:
            return True
        
        # Private collections require valid access token
        if collection.is_private and access_token:
            from app.api.v1.endpoints.journal import verify_collection_access_token
            try:
                return verify_collection_access_token(access_token, collection_id, user_id)
            except:
                return False
        
        return False 