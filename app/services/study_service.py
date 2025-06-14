from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.db.models import StudySet, Flashcard, SecurityLog
from app.repositories.study_repository import StudySetRepository
from app.schemas.study import StudySetCreate, StudySetUpdate, StudySetResponse, FlashcardResponse


class StudySetService:
    """Service for study set operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = StudySetRepository(session)
    
    async def get_user_study_sets(self, user_id: int) -> List[StudySetResponse]:
        """
        Get all study sets for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            List of study set responses
        """
        study_sets = await self.repository.get_by_user_id(user_id)
        return [self._to_response(study_set) for study_set in study_sets]
    
    async def get_study_set(self, study_set_id: int, user_id: int) -> StudySetResponse:
        """
        Get a specific study set.
        
        Args:
            study_set_id: Study set ID
            user_id: User ID
            
        Returns:
            Study set response
            
        Raises:
            HTTPException: If study set not found or not owned by user
        """
        study_set = await self.repository.get_by_id_and_user_id(study_set_id, user_id)
        
        if not study_set:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Study set not found or not owned by current user"
            )
            
        return self._to_response(study_set)
    
    async def create_study_set(self, user_id: int, study_set_data: StudySetCreate, ip_address: str) -> StudySetResponse:
        """
        Create a new study set.
        
        Args:
            user_id: User ID
            study_set_data: Study set data
            ip_address: Client IP address for logging
            
        Returns:
            Created study set response
        """
        # Create study set
        study_set = await self.repository.create_with_flashcards(user_id, study_set_data)
        
        # Log operation
        await self._log_operation(
            event_type="CREATE",
            user_id=user_id,
            ip_address=ip_address,
            details=f"Created study set ID {study_set.id}"
        )
        
        return self._to_response(study_set)
    
    async def update_study_set(self, 
                            study_set_id: int, 
                            user_id: int, 
                            study_set_data: StudySetUpdate,
                            ip_address: str) -> StudySetResponse:
        """
        Update a study set.
        
        Args:
            study_set_id: Study set ID
            user_id: User ID
            study_set_data: Updated study set data
            ip_address: Client IP address for logging
            
        Returns:
            Updated study set response
            
        Raises:
            HTTPException: If study set not found or not owned by user
        """
        # Get study set
        study_set = await self.repository.get_by_id_and_user_id(study_set_id, user_id)
        
        if not study_set:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Study set not found or not owned by current user"
            )
            
        # Update study set
        updated_study_set = await self.repository.update_with_flashcards(study_set, study_set_data)
        
        # Log operation
        await self._log_operation(
            event_type="UPDATE",
            user_id=user_id,
            ip_address=ip_address,
            details=f"Updated study set ID {study_set_id}"
        )
        
        return self._to_response(updated_study_set)
    
    async def delete_study_set(self, study_set_id: int, user_id: int, ip_address: str) -> None:
        """
        Delete a study set.
        
        Args:
            study_set_id: Study set ID
            user_id: User ID
            ip_address: Client IP address for logging
            
        Raises:
            HTTPException: If study set not found or not owned by user
        """
        # Get study set
        study_set = await self.repository.get_by_id_and_user_id(study_set_id, user_id)
        
        if not study_set:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Study set not found or not owned by current user"
            )
            
        # Delete study set
        deleted = await self.repository.delete(study_set_id)
        
        if deleted:
            # Log operation
            await self._log_operation(
                event_type="DELETE",
                user_id=user_id,
                ip_address=ip_address,
                details=f"Deleted study set ID {study_set_id}"
            )
    
    async def delete_all_user_study_sets(self, user_id: int, ip_address: str) -> None:
        """
        Delete all study sets for a user.
        
        Args:
            user_id: User ID
            ip_address: Client IP address for logging
        """
        count = await self.repository.delete_all_by_user_id(user_id)
        
        # Log operation
        await self._log_operation(
            event_type="DELETE_ALL",
            user_id=user_id,
            ip_address=ip_address,
            details=f"Deleted all study sets ({count} sets)"
        )
    
    async def add_card_to_study_set(self, 
                                   study_set_id: int, 
                                   user_id: int, 
                                   question: str, 
                                   answer: str,
                                   ip_address: str) -> FlashcardResponse:
        """
        Add a card to a study set.
        
        Args:
            study_set_id: Study set ID
            user_id: User ID
            question: Card question
            answer: Card answer
            ip_address: Client IP address for logging
            
        Returns:
            Created flashcard response
            
        Raises:
            HTTPException: If study set not found or not owned by user
        """
        # Get study set
        study_set = await self.repository.get_by_id_and_user_id(study_set_id, user_id)
        
        if not study_set:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Study set not found or not owned by current user"
            )
            
        # Create flashcard
        flashcard = Flashcard(set_id=study_set_id, question=question, answer=answer)
        self.session.add(flashcard)
        await self.session.flush()
        
        # Log operation
        await self._log_operation(
            event_type="ADD_CARD",
            user_id=user_id,
            ip_address=ip_address,
            details=f"Added card to study set ID {study_set_id}"
        )
        
        # Convert to response
        return FlashcardResponse(
            id=flashcard.id,
            front_content=flashcard.question,
            back_content=flashcard.answer,
            created_at=flashcard.created_at
        )
    
    def _to_response(self, study_set: StudySet) -> StudySetResponse:
        """Convert a study set model to a response."""
        return StudySetResponse(
            id=study_set.id,
            title=study_set.title,
            created_at=study_set.created_at,
            cards=[
                FlashcardResponse(
                    id=card.id,
                    front_content=card.question,
                    back_content=card.answer,
                    created_at=card.created_at
                )
                for card in study_set.flashcards
            ]
        )
    
    async def _log_operation(self, event_type: str, user_id: int, ip_address: str, details: str = None) -> None:
        """Log a study set operation."""
        security_log = SecurityLog(
            user_id=user_id,
            event_type=f"STUDY_SET_{event_type}",
            ip_address=ip_address,
            details=details
        )
        self.session.add(security_log) 