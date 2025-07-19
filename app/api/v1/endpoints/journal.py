from datetime import date, datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt, JWTError
import logging

from app.db.database import get_db
from app.core.auth import get_current_user
from app.db.models import User
from app.schemas.journal import (
    JournalCollection, JournalCollectionCreate, JournalCollectionUpdate, 
    JournalCollectionList, JournalCollectionPasswordVerify, CollectionAccessToken,
    JournalEntry, JournalEntryCreate, JournalEntryUpdate, JournalEntryList,
    Gratitude, GratitudeCreate, GratitudeUpdate, GratitudeList,
    JournalStats
)
from app.crud.journal import (
    JournalCollectionCRUD, JournalEntryCRUD, GratitudeCRUD, JournalStatsCRUD
)
from app.utils.rate_limiter import rate_limit
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


def generate_collection_access_token(collection_id: int, user_id: int) -> str:
    """Generate temporary access token for private collection"""
    payload = {
        "collection_id": collection_id,
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=1)  # 1 hour expiry
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def verify_collection_access_token(token: str, collection_id: int, user_id: int) -> bool:
    """Verify collection access token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return (
            payload.get("collection_id") == collection_id and 
            payload.get("user_id") == user_id
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired collection access token"
        )


# Collection endpoints
@router.get("/collections", response_model=JournalCollectionList)
@rate_limit()
async def get_collections(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's journal collections with pagination"""
    collections, total = await JournalCollectionCRUD.get_user_collections(
        db, current_user.id, skip, limit
    )
    
    return JournalCollectionList(
        collections=collections,
        total=total,
        page=skip // limit + 1,
        size=limit,
        has_next=skip + limit < total,
        has_prev=skip > 0
    )


@router.post("/collections", response_model=JournalCollection, status_code=status.HTTP_201_CREATED)
@rate_limit()
async def create_collection(
    collection: JournalCollectionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new journal collection"""
    return await JournalCollectionCRUD.create(db, collection, current_user.id)


@router.get("/collections/{collection_id}", response_model=JournalCollection)
async def get_collection(
    collection_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific collection"""
    collection = await JournalCollectionCRUD.get_by_id(db, collection_id, current_user.id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )
    return collection


@router.put("/collections/{collection_id}", response_model=JournalCollection)
@rate_limit()
async def update_collection(
    collection_id: int,
    collection_update: JournalCollectionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a journal collection"""
    collection = await JournalCollectionCRUD.update(
        db, collection_id, current_user.id, collection_update
    )
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )
    return collection


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a journal collection"""
    success = await JournalCollectionCRUD.delete(db, collection_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )


@router.post("/collections/{collection_id}/verify-password", response_model=CollectionAccessToken)
@rate_limit()
async def verify_collection_password(
    collection_id: int,
    password_data: JournalCollectionPasswordVerify,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Verify password for private collection and return access token"""
    if not await JournalCollectionCRUD.verify_password(
        db, collection_id, current_user.id, password_data.password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password"
        )
    
    access_token = generate_collection_access_token(collection_id, current_user.id)
    
    return CollectionAccessToken(
        access_token=access_token,
        expires_in=3600,  # 1 hour
        collection_id=collection_id
    )


@router.get("/collections/{collection_id}/entries", response_model=JournalEntryList)
async def get_collection_entries(
    collection_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    access_token: Optional[str] = Header(None, alias="X-Collection-Access-Token"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get entries for a specific collection"""
    # Check if collection exists and user has access
    collection = await JournalCollectionCRUD.get_by_id(db, collection_id, current_user.id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )
    
    # Verify access token for private collections
    if collection.is_private:
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access token required for private collection"
            )
        verify_collection_access_token(access_token, collection_id, current_user.id)
    
    entries, total = await JournalEntryCRUD.get_collection_entries(
        db, collection_id, current_user.id, skip, limit
    )
    
    return JournalEntryList(
        entries=entries,
        total=total,
        page=skip // limit + 1,
        size=limit,
        has_next=skip + limit < total,
        has_prev=skip > 0
    )


# Entry endpoints
@router.get("/entries", response_model=JournalEntryList)
async def get_entries(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, max_length=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's journal entries with optional search"""
    entries, total = await JournalEntryCRUD.get_user_entries(
        db, current_user.id, skip, limit, search
    )
    
    return JournalEntryList(
        entries=entries,
        total=total,
        page=skip // limit + 1,
        size=limit,
        has_next=skip + limit < total,
        has_prev=skip > 0
    )


@router.post("/entries", response_model=JournalEntry, status_code=status.HTTP_201_CREATED)
async def create_entry(
    entry: JournalEntryCreate,
    access_token: Optional[str] = Header(None, alias="X-Collection-Access-Token"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new journal entry"""
    # Check if collection exists and user has access
    collection = await JournalCollectionCRUD.get_by_id(db, entry.collection_id, current_user.id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )
    
    # Verify access token for private collections
    if collection.is_private:
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access token required for private collection"
            )
        verify_collection_access_token(access_token, entry.collection_id, current_user.id)
    
    return await JournalEntryCRUD.create(db, entry, current_user.id, current_user)


@router.get("/entries/{entry_id}", response_model=JournalEntry)
async def get_entry(
    entry_id: int,
    access_token: Optional[str] = Header(None, alias="X-Collection-Access-Token"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific journal entry"""
    entry = await JournalEntryCRUD.get_by_id(db, entry_id, current_user.id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found"
        )
    
    # Check access for private collection
    if entry.collection.is_private:
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access token required for private collection"
            )
        verify_collection_access_token(access_token, entry.collection_id, current_user.id)
    
    return entry


@router.put("/entries/{entry_id}", response_model=JournalEntry)
async def update_entry(
    entry_id: int,
    entry_update: JournalEntryUpdate,
    access_token: Optional[str] = Header(None, alias="X-Collection-Access-Token"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a journal entry"""
    # Get entry first to check collection access
    existing_entry = await JournalEntryCRUD.get_by_id(db, entry_id, current_user.id)
    if not existing_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found"
        )
    
    # Check access for private collection
    if existing_entry.collection.is_private:
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access token required for private collection"
            )
        verify_collection_access_token(access_token, existing_entry.collection_id, current_user.id)
    
    entry = await JournalEntryCRUD.update(db, entry_id, current_user.id, entry_update, current_user)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found"
        )
    return entry


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(
    entry_id: int,
    access_token: Optional[str] = Header(None, alias="X-Collection-Access-Token"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a journal entry"""
    # Get entry first to check collection access
    existing_entry = await JournalEntryCRUD.get_by_id(db, entry_id, current_user.id)
    if not existing_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found"
        )
    
    # Check access for private collection
    if existing_entry.collection.is_private:
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access token required for private collection"
            )
        verify_collection_access_token(access_token, existing_entry.collection_id, current_user.id)
    
    success = await JournalEntryCRUD.delete(db, entry_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found"
        )


# Gratitude endpoints
@router.get("/gratitude", response_model=GratitudeList)
async def get_gratitude(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's gratitude entries"""
    gratitude_entries, total = await GratitudeCRUD.get_user_gratitude(
        db, current_user.id, skip, limit, start_date, end_date
    )
    
    return GratitudeList(
        gratitude_entries=gratitude_entries,
        total=total,
        page=skip // limit + 1,
        size=limit,
        has_next=skip + limit < total,
        has_prev=skip > 0
    )


@router.post("/gratitude", response_model=Gratitude, status_code=status.HTTP_201_CREATED)
@rate_limit()
async def create_gratitude(
    gratitude: GratitudeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new gratitude entry"""
    try:
        # Validate the input
        if not gratitude.text or not gratitude.text.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Gratitude text cannot be empty"
            )
        
        if len(gratitude.text.strip()) > 500:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Gratitude text cannot exceed 500 characters"
            )
        
        # Create the gratitude entry
        result = await GratitudeCRUD.create(db, gratitude, current_user.id)
        
        # Log successful creation in development
        if settings.is_development():
            logger.info(f"Created gratitude entry for user {current_user.id}: {gratitude.text[:50]}...")
        
        return result
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log unexpected errors
        logger.error(f"Error creating gratitude entry: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create gratitude entry"
        )


@router.put("/gratitude/{gratitude_id}", response_model=Gratitude)
@rate_limit()
async def update_gratitude(
    gratitude_id: int,
    gratitude_update: GratitudeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a gratitude entry"""
    gratitude = await GratitudeCRUD.update(
        db, gratitude_id, current_user.id, gratitude_update
    )
    if not gratitude:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gratitude entry not found"
        )
    return gratitude


@router.delete("/gratitude/{gratitude_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_gratitude(
    gratitude_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a gratitude entry"""
    success = await GratitudeCRUD.delete(db, gratitude_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gratitude entry not found"
        )


# Statistics endpoint
@router.get("/stats", response_model=JournalStats)
async def get_journal_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get journal statistics for the user"""
    stats = await JournalStatsCRUD.get_user_stats(db, current_user.id)
    return JournalStats(**stats)


# Health check endpoint
@router.get("/health")
async def journal_health_check():
    """Health check endpoint for journal service"""
    return {"status": "healthy", "service": "journal"} 