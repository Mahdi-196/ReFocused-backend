from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, validator

class FlashcardBase(BaseModel):
    """Base model for flashcard data."""
    # Support both frontend and backend field names
    front_content: Optional[str] = Field(None, min_length=1, max_length=10000)
    back_content: Optional[str] = Field(None, min_length=1, max_length=10000)
    question: Optional[str] = Field(None, min_length=1, max_length=10000)
    answer: Optional[str] = Field(None, min_length=1, max_length=10000)
    id: Optional[int] = None

    @validator('front_content', 'back_content', 'question', 'answer')
    def validate_content(cls, v, values):
        if v is None:
            return v
        if not v or v.isspace():
            raise ValueError('Cannot be empty or whitespace')
        return v

    @validator('question', always=True)
    def map_front_to_question(cls, v, values):
        if v is None and 'front_content' in values and values['front_content'] is not None:
            return values['front_content']
        return v

    @validator('answer', always=True)
    def map_back_to_answer(cls, v, values):
        if v is None and 'back_content' in values and values['back_content'] is not None:
            return values['back_content']
        return v

class FlashcardCreate(FlashcardBase):
    """Model for creating a flashcard."""
    # At least one pair of fields must be provided
    @validator('front_content', 'question', always=True)
    def check_question_exists(cls, v, values):
        if v is None and ('question' not in values or values.get('question') is None) and ('front_content' not in values or values.get('front_content') is None):
            raise ValueError('Either question or front_content must be provided')
        return v

    @validator('back_content', 'answer', always=True)
    def check_answer_exists(cls, v, values):
        if v is None and ('answer' not in values or values.get('answer') is None) and ('back_content' not in values or values.get('back_content') is None):
            raise ValueError('Either answer or back_content must be provided')
        return v

class FlashcardResponse(BaseModel):
    """Response model for a flashcard."""
    id: int
    front_content: str  # Map from question
    back_content: str   # Map from answer
    created_at: datetime

    class Config:
        from_attributes = True

class StudySetBase(BaseModel):
    """Base model for study set data."""
    title: str = Field(..., min_length=1, max_length=255)
    id: Optional[int] = None

    @validator('title')
    def validate_title(cls, v):
        if not v or v.isspace():
            raise ValueError('Title cannot be empty or whitespace')
        return v

class StudySetCreate(StudySetBase):
    """Model for creating a study set."""
    # Make flashcards optional for the create endpoint
    flashcards: Optional[List[FlashcardBase]] = Field(None, max_items=500)

class StudySetUpdate(StudySetBase):
    """Model for updating a study set."""
    # For updates, we require an ID
    id: int
    flashcards: Optional[List[FlashcardBase]] = Field(None, max_items=500)

class SingleCardCreate(BaseModel):
    """Model for adding a single card to a study set."""
    front_content: str = Field(..., min_length=1, max_length=10000)
    back_content: str = Field(..., min_length=1, max_length=10000)
    study_set_id: Optional[int] = None  # Optional as it may be determined from URL path

    @validator('front_content', 'back_content')
    def validate_content(cls, v):
        if not v or v.isspace():
            raise ValueError('Cannot be empty or whitespace')
        return v

class StudySetResponse(StudySetBase):
    """Response model for a study set."""
    id: int
    created_at: datetime
    cards: List[FlashcardResponse]  # Changed from flashcards to cards to match frontend

    class Config:
        from_attributes = True

class BulkStudySetCreate(BaseModel):
    """Model for bulk creating study sets."""
    study_sets: List[StudySetCreate] = Field(..., max_items=100)

class BulkStudySetResponse(BaseModel):
    """Response model for bulk operations."""
    study_sets: List[StudySetResponse] 