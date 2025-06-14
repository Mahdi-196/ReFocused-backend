from typing import List, Optional, Dict, Any, Union
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import StudySet, Flashcard
from app.repositories.base_repository import BaseRepository
from app.schemas.study import StudySetCreate, StudySetUpdate


class StudySetRepository(BaseRepository[StudySet]):
    """Repository for study set operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(StudySet, session)
    
    async def get_by_user_id(self, user_id: int, skip: int = 0, limit: int = 100) -> List[StudySet]:
        """
        Get study sets for a specific user.
        
        Args:
            user_id: User ID
            skip: Number of items to skip
            limit: Maximum number of items to return
            
        Returns:
            List of study sets
        """
        query = select(self.model) \
            .where(self.model.user_id == user_id) \
            .options(selectinload(self.model.flashcards)) \
            .offset(skip) \
            .limit(limit)
            
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def get_by_id_and_user_id(self, id: int, user_id: int) -> Optional[StudySet]:
        """
        Get a study set by ID and user ID.
        
        Args:
            id: Study set ID
            user_id: User ID
            
        Returns:
            Study set or None
        """
        query = select(self.model) \
            .where(self.model.id == id, self.model.user_id == user_id) \
            .options(selectinload(self.model.flashcards))
            
        result = await self.session.execute(query)
        return result.scalars().first()
    
    async def create_with_flashcards(self, 
                                    user_id: int, 
                                    study_set_data: StudySetCreate) -> StudySet:
        """
        Create a study set with flashcards.
        
        Args:
            user_id: User ID
            study_set_data: Study set data
            
        Returns:
            Created study set
        """
        # Create study set
        study_set = StudySet(user_id=user_id, title=study_set_data.title)
        
        # Add flashcards if provided
        if study_set_data.flashcards:
            for card_data in study_set_data.flashcards:
                # Map front_content/back_content to question/answer if needed
                question = card_data.question or card_data.front_content
                answer = card_data.answer or card_data.back_content
                
                if question and answer:
                    study_set.flashcards.append(
                        Flashcard(question=question, answer=answer)
                    )
        
        self.session.add(study_set)
        await self.session.flush()
        return study_set
    
    async def update_with_flashcards(self, 
                                    study_set: StudySet, 
                                    study_set_data: StudySetUpdate) -> StudySet:
        """
        Update a study set and its flashcards.
        
        Args:
            study_set: Study set to update
            study_set_data: Updated study set data
            
        Returns:
            Updated study set
        """
        # Update title
        study_set.title = study_set_data.title
        
        # Update flashcards if provided
        if study_set_data.flashcards is not None:
            # Clear existing flashcards
            study_set.flashcards.clear()
            
            # Add new flashcards
            for card_data in study_set_data.flashcards:
                # Map front_content/back_content to question/answer if needed
                question = card_data.question or card_data.front_content
                answer = card_data.answer or card_data.back_content
                
                if question and answer:
                    study_set.flashcards.append(
                        Flashcard(question=question, answer=answer)
                    )
        
        self.session.add(study_set)
        await self.session.flush()
        return study_set
    
    async def delete_all_by_user_id(self, user_id: int) -> int:
        """
        Delete all study sets for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Number of deleted study sets
        """
        # Get all study set IDs for the user
        query = select(self.model.id).where(self.model.user_id == user_id)
        result = await self.session.execute(query)
        study_set_ids = result.scalars().all()
        
        if not study_set_ids:
            return 0
            
        # Delete flashcards first
        flashcard_query = select(Flashcard).where(Flashcard.set_id.in_(study_set_ids))
        flashcard_result = await self.session.execute(flashcard_query)
        flashcards = flashcard_result.scalars().all()
        
        for flashcard in flashcards:
            await self.session.delete(flashcard)
        
        # Delete study sets
        count = 0
        for study_set_id in study_set_ids:
            db_obj = await self.get_by_id(study_set_id)
            if db_obj:
                await self.session.delete(db_obj)
                count += 1
                
        return count 