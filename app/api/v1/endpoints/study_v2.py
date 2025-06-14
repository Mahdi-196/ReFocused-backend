from typing import List
from fastapi import APIRouter, status, Request

from app.dependencies import StudyService, CurrentUser, ClientIP
from app.schemas.study import (
    StudySetResponse, StudySetCreate, StudySetUpdate,
    SingleCardCreate, FlashcardResponse
)
from app.core.error_handling import AppError, NotFoundError

router = APIRouter()

@router.get("", response_model=List[StudySetResponse])
async def get_study_sets(
    current_user: CurrentUser,
    study_service: StudyService
):
    """
    Get all study sets belonging to the current user
    """
    return await study_service.get_user_study_sets(current_user.id)

@router.get("/{study_set_id}", response_model=StudySetResponse)
async def get_study_set(
    study_set_id: int,
    current_user: CurrentUser,
    study_service: StudyService
):
    """
    Get a specific study set by ID
    """
    return await study_service.get_study_set(study_set_id, current_user.id)

@router.post("", response_model=StudySetResponse, status_code=status.HTTP_201_CREATED)
async def create_study_set(
    study_set: StudySetCreate,
    current_user: CurrentUser,
    client_ip: ClientIP,
    study_service: StudyService
):
    """
    Create a new study set
    """
    # Check if this is an update request
    if study_set.id:
        return await study_service.update_study_set(
            study_set_id=study_set.id,
            user_id=current_user.id,
            study_set_data=StudySetUpdate(**study_set.dict()),
            ip_address=client_ip
        )
    
    # Create new study set
    return await study_service.create_study_set(
        user_id=current_user.id,
        study_set_data=study_set,
        ip_address=client_ip
    )

@router.put("/{study_set_id}", response_model=StudySetResponse)
async def update_study_set(
    study_set_id: int,
    study_set: StudySetUpdate,
    current_user: CurrentUser,
    client_ip: ClientIP,
    study_service: StudyService
):
    """
    Update a study set
    """
    # Ensure the study_set_id in path matches the one in the payload
    if study_set.id and study_set.id != study_set_id:
        raise AppError(
            message="Study set ID in path does not match ID in payload",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="ID_MISMATCH"
        )
    
    # Set the ID from the path if not provided in the payload
    if not study_set.id:
        study_set.id = study_set_id
    
    return await study_service.update_study_set(
        study_set_id=study_set_id,
        user_id=current_user.id,
        study_set_data=study_set,
        ip_address=client_ip
    )

@router.post("/{study_set_id}/cards", response_model=FlashcardResponse)
async def add_card_to_study_set(
    study_set_id: int,
    card: SingleCardCreate,
    current_user: CurrentUser,
    client_ip: ClientIP,
    study_service: StudyService
):
    """
    Add a card to an existing study set
    """
    return await study_service.add_card_to_study_set(
        study_set_id=study_set_id,
        user_id=current_user.id,
        question=card.front_content,
        answer=card.back_content,
        ip_address=client_ip
    )

@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_study_sets(
    current_user: CurrentUser,
    client_ip: ClientIP,
    study_service: StudyService
):
    """
    Delete all study sets for the authenticated user
    """
    await study_service.delete_all_user_study_sets(current_user.id, client_ip)
    return None

@router.delete("/{study_set_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_study_set(
    study_set_id: int,
    current_user: CurrentUser,
    client_ip: ClientIP,
    study_service: StudyService
):
    """
    Delete a study set and all its flashcards
    """
    await study_service.delete_study_set(study_set_id, current_user.id, client_ip)
    return None 