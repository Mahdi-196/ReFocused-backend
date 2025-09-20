from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel


# Simple journal collection schemas
class JournalCollectionBase(BaseModel):
    name: str
    is_private: bool = False

class JournalCollectionCreate(JournalCollectionBase):
    password: Optional[str] = None

class JournalCollectionUpdate(BaseModel):
    name: Optional[str] = None
    is_private: Optional[bool] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None

class JournalCollectionPasswordVerify(BaseModel):
    password: str

class JournalCollection(JournalCollectionBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    entry_count: int = 0
    
    model_config = {"from_attributes": True}


# Simple journal entry schemas  
class JournalEntryBase(BaseModel):
    title: str
    content: Optional[str] = None

class JournalEntryCreate(JournalEntryBase):
    collection_id: int
    is_encrypted: Optional[bool] = None

class JournalEntryUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None

class JournalEntry(JournalEntryBase):
    id: int
    collection_id: int
    is_encrypted: bool
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}


# Simple gratitude schemas
class GratitudeBase(BaseModel):
    text: str
    date: Optional[date] = None

class GratitudeCreate(GratitudeBase):
    pass

class GratitudeUpdate(BaseModel):
    text: Optional[str] = None

class Gratitude(GratitudeBase):
    id: int
    user_id: int
    date: date
    created_at: datetime
    
    model_config = {"from_attributes": True}


# Response schemas
class JournalCollectionList(BaseModel):
    collections: List[JournalCollection]
    total: int
    page: int
    size: int
    has_next: bool
    has_prev: bool

class JournalEntryList(BaseModel):
    entries: List[JournalEntry]
    total: int
    page: int
    size: int
    has_next: bool
    has_prev: bool

class GratitudeList(BaseModel):
    gratitude_entries: List[Gratitude]
    total: int
    page: int
    size: int
    has_next: bool
    has_prev: bool

class CollectionAccessToken(BaseModel):
    valid: bool = True
    access_token: str
    expires_in: int
    collection_id: int

class JournalStats(BaseModel):
    total_collections: int
    total_entries: int
    total_gratitude: int
    private_collections: int
    entries_this_week: int
    entries_this_month: int
    gratitude_this_week: int
    gratitude_streak: int