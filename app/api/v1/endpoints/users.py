from typing import Any, Optional
from datetime import datetime
import traceback
import logging

# FastAPI imports
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Body, Response, Request
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer

# Database imports
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

# Pydantic imports
from pydantic import BaseModel

# App imports
from app.core.config import settings
from app.core.security import log_security_event
from app.core.auth import get_current_user, jwt_required, oauth2_scheme
from app.db.database import get_db
from app.db.models import User, Goal2Week, GoalLongTerm, Habit, MoodEntry
from app.schemas.user import UserResponse, UserProfile, UserUpdate, AccountDeleteRequest, AvatarUpdateRequest, AvatarResponse, AvatarConfig
from datetime import date
from app.core.security import verify_password
from app.crud.activity import crud_activity
from app.services.export_service import export_service

# Initialize logger
logger = logging.getLogger(__name__)

router = APIRouter()


class ProfileUpdate(BaseModel):
    """Schema for profile update requests."""
    name: Optional[str] = None
    profile_picture: Optional[str] = None


class UserStats(BaseModel):
    """Schema for user statistics response."""
    goals_total: int
    goals_completed: int
    habits_total: int
    mood_entries_count: int
    account_age_days: int


@router.get("/me", response_model=UserProfile)
async def read_own_profile(
    current_user: User = Depends(get_current_user)
) -> UserProfile:
    """
    Get the profile of the currently authenticated user.
    """
    return UserProfile(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        profile_picture=current_user.profile_picture,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None
    )


@router.get("/profile", response_model=UserResponse)
async def get_user_profile(
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Alternative endpoint for getting user profile.
    """
    return current_user


@router.patch("/profile", response_model=UserProfile)
async def update_user_profile(
    profile_data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> UserProfile:
    """
    Update current user profile information.
    Supports updating name, profile_picture, and avatar fields.
    Uses standard JWT authentication (consistent with other endpoints).
    """
    
    # Track which fields are being updated
    updated_fields = []
    
    # Update user fields
    if profile_data.name is not None:
        current_user.name = profile_data.name
        updated_fields.append("name")
        
    # Handle both profile_picture and avatar fields (for frontend compatibility)
    avatar_url = None
    if profile_data.profile_picture is not None:
        avatar_url = profile_data.profile_picture
        updated_fields.append("profile_picture")
    elif profile_data.avatar is not None:
        avatar_url = profile_data.avatar
        updated_fields.append("avatar")
    
    if avatar_url is not None:
        current_user.profile_picture = avatar_url
    
    # Save changes to database
    await db.commit()
    await db.refresh(current_user)
    
    # Log profile update for security tracking
    log_security_event(
        event_type="profile_update",
        details={"updated_fields": updated_fields},
        level="info",
        user_id=current_user.id
    )
    
    # Return updated profile
    return UserProfile(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        profile_picture=current_user.profile_picture,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None
    )


@router.put("/profile", response_model=UserProfile)
async def update_user_profile_put(
    profile_data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> UserProfile:
    """
    Update current user profile information (PUT method).
    Supports updating name and profile_picture fields.
    Uses standard JWT authentication (consistent with other endpoints).
    """
    return await update_user_profile(profile_data, current_user, db)


@router.get("/avatar", response_model=AvatarResponse)
async def get_user_avatar(
    current_user: User = Depends(get_current_user)
) -> AvatarResponse:
    """
    Get current user's avatar configuration.
    Returns the avatar URL and attempts to parse configuration from the URL.
    """
    try:
        if not current_user.profile_picture:
            return AvatarResponse(
                success=True,
                message="No avatar configured",
                avatar_url=None,
                avatar_config=None
            )
        
        # Try to parse avatar configuration from the URL
        avatar_config = _parse_avatar_from_url(current_user.profile_picture)
        
        return AvatarResponse(
            success=True,
            message="Avatar retrieved successfully",
            avatar_url=current_user.profile_picture,
            avatar_config=avatar_config
        )
        
    except Exception as e:
        logger.error(f"Failed to retrieve avatar for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve avatar"
        )

@router.put("/avatar", response_model=AvatarResponse)
async def update_user_avatar(
    avatar_data: AvatarUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> AvatarResponse:
    """
    Update user's avatar configuration and profile picture.
    Supports all avatar styles: Open Peeps, Adventurer, Lorelei, Croodles, 
    Notionists, Pixel Art, RoboHash Robots, RoboHash Monsters.
    """
    try:
        # Generate avatar URL based on style and configuration
        avatar_url = _generate_avatar_url(avatar_data.avatar_config)
        
        # Store the avatar URL in the user's profile_picture field
        current_user.profile_picture = avatar_url
        
        # Commit changes to database
        await db.commit()
        await db.refresh(current_user)
        
        # Log avatar update for security tracking
        log_security_event(
            event_type="avatar_update",
            details={
                "avatar_style": avatar_data.avatar_config.style,
                "avatar_seed": avatar_data.avatar_config.seed
            },
            level="info",
            user_id=current_user.id
        )
        
        return AvatarResponse(
            success=True,
            message="Avatar updated successfully",
            avatar_url=avatar_url,
            avatar_config=avatar_data.avatar_config
        )
        
    except Exception as e:
        logger.error(f"Failed to update avatar for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update avatar"
        )

def _parse_avatar_from_url(url: str) -> Optional[AvatarConfig]:
    """
    Parse avatar configuration from DiceBear URL.
    Best effort parsing - returns None if URL format is unexpected.
    """
    try:
        from urllib.parse import urlparse, parse_qs
        
        parsed = urlparse(url)
        
        # Extract style from path (e.g., /7.x/open-peeps/svg -> open-peeps)
        path_parts = parsed.path.strip('/').split('/')
        if len(path_parts) >= 3 and path_parts[0] == '7.x':
            dicebear_style = path_parts[1]
            
            # Reverse map DiceBear style to frontend style
            reverse_style_mapping = {
                "open-peeps": "open-peeps",
                "adventurer": "adventurer", 
                "lorelei": "lorelei",
                "croodles": "croodles",
                "notionists": "notionists",
                "pixel-art": "pixel-art",
                "bottts": "robohash-robots",
                "monsters": "robohash-monsters"
            }
            
            frontend_style = reverse_style_mapping.get(dicebear_style, dicebear_style)
            
            # Parse query parameters
            query_params = parse_qs(parsed.query)
            seed = query_params.get('seed', [''])[0]
            
            # Build options from remaining parameters
            options = {}
            for key, values in query_params.items():
                if key != 'seed' and values:
                    options[key] = values[0]
            
            return AvatarConfig(
                style=frontend_style,
                seed=seed,
                options=options if options else None
            )
    except Exception:
        # If parsing fails, return None
        pass
    
    return None

def _generate_avatar_url(avatar_config: AvatarConfig) -> str:
    """
    Generate avatar URL based on configuration.
    Maps frontend avatar styles to DiceBear API endpoints.
    """
    # Map frontend style names to DiceBear API styles
    style_mapping = {
        "open-peeps": "open-peeps",
        "adventurer": "adventurer", 
        "lorelei": "lorelei",
        "croodles": "croodles",
        "notionists": "notionists",
        "pixel-art": "pixel-art",
        "robohash-robots": "bottts",  # RoboHash robots -> bottts
        "robohash-monsters": "monsters"  # RoboHash monsters -> monsters
    }
    
    # Get DiceBear style name
    dicebear_style = style_mapping.get(avatar_config.style.lower(), "open-peeps")
    
    # Base URL for DiceBear API v7
    base_url = f"https://api.dicebear.com/7.x/{dicebear_style}/svg"
    
    # Build query parameters
    params = [f"seed={avatar_config.seed}"]
    
    # Add any additional options
    if avatar_config.options:
        for key, value in avatar_config.options.items():
            if value is not None:
                params.append(f"{key}={value}")
    
    # Construct final URL
    if params:
        return f"{base_url}?{'&'.join(params)}"
    else:
        return f"{base_url}?seed={avatar_config.seed}"


@router.get("/stats", response_model=UserStats)
async def get_user_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> UserStats:
    """
    Get user-specific statistics.
    Provides comprehensive analytics about user activity.
    """
    
    # Count goals from both tables
    # Count 2-week goals (excluding expired)
    from datetime import timezone
    current_time = datetime.now(timezone.utc)
    
    goals_2week_total_result = await db.execute(
        select(func.count(Goal2Week.id)).where(
            Goal2Week.user_id == current_user.id,
            Goal2Week.expires_at > current_time
        )
    )
    goals_2week_total = goals_2week_total_result.scalar() or 0
    
    goals_2week_completed_result = await db.execute(
        select(func.count(Goal2Week.id)).where(
            Goal2Week.user_id == current_user.id,
            Goal2Week.is_completed == True,
            Goal2Week.expires_at > current_time
        )
    )
    goals_2week_completed = goals_2week_completed_result.scalar() or 0
    
    # Count long-term goals
    goals_longterm_total_result = await db.execute(
        select(func.count(GoalLongTerm.id)).where(GoalLongTerm.user_id == current_user.id)
    )
    goals_longterm_total = goals_longterm_total_result.scalar() or 0
    
    goals_longterm_completed_result = await db.execute(
        select(func.count(GoalLongTerm.id)).where(
            GoalLongTerm.user_id == current_user.id,
            GoalLongTerm.is_completed == True
        )
    )
    goals_longterm_completed = goals_longterm_completed_result.scalar() or 0
    
    # Combine totals
    goals_total = goals_2week_total + goals_longterm_total
    goals_completed = goals_2week_completed + goals_longterm_completed
    
    # Count habits
    habits_total_result = await db.execute(
        select(func.count(Habit.id)).where(Habit.user_id == current_user.id)
    )
    habits_total = habits_total_result.scalar() or 0
    
    # Count mood entries
    mood_entries_result = await db.execute(
        select(func.count(MoodEntry.id)).where(MoodEntry.user_id == current_user.id)
    )
    mood_entries_count = mood_entries_result.scalar() or 0
    
    # Calculate account age
    account_age_days = 0
    if current_user.created_at:
        account_age_days = (date.today() - current_user.created_at.date()).days
    
    return UserStats(
        goals_total=goals_total,
        goals_completed=goals_completed,
        habits_total=habits_total,
        mood_entries_count=mood_entries_count,
        account_age_days=account_age_days
    ) 


@router.post("/me/export", status_code=status.HTTP_200_OK)
async def request_data_export(
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Request a complete export of all user data.
    
    This endpoint performs a synchronous export of all user data
    into a comprehensive, human-readable JSON file. The export includes:
    
    - Account information and settings
    - Goals (2-week and long-term) with progress tracking
    - Habits with completion history and streaks
    - Mood tracking data with trends and analytics
    - Journal collections, entries, and gratitude entries
    - Study materials (study sets and flashcards)
    - Personal content (mantras, quick access links)
    - Activity history and usage statistics
    - Calendar entries with associated data
    - Settings and preferences
    
    Security Features:
    - Requires JWT authentication
    - User-scoped data export (users can only export their own data)
    - Encrypted journal entries are marked as protected in the export
    - Comprehensive audit logging
    
    Returns:
        HTTP 200 OK with export completion information and download details
    """
    
    try:
        # Log export request for security audit
        log_security_event(
            event_type="data_export_requested",
            details={
                "user_id": current_user.id,
                "email": current_user.email,
                "request_timestamp": datetime.utcnow().isoformat()
            },
            level="info",
            user_id=current_user.id
        )
        
        # Perform synchronous export using service
        try:
            task_info = export_service.initiate_export(current_user.id)
            task_id = task_info["task_id"]
            export_result = task_info["result"]
        except Exception as e:
            logger.error(f"Failed to complete export: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to complete export. Please try again."
            )
        
        # Log task completion
        log_security_event(
            event_type="data_export_completed",
            details={
                "user_id": current_user.id,
                "email": current_user.email,
                "task_id": task_id,
                "completion_timestamp": datetime.utcnow().isoformat(),
                "file_path": export_result.get("file_path")
            },
            level="info",
            user_id=current_user.id
        )
        
        return {
            "message": "Data export has been completed successfully",
            "status": "completed",
            "task_id": task_id,
            "user_id": current_user.id,
            "completed_at": datetime.utcnow().isoformat(),
            "file_path": export_result.get("file_path"),
            "data_summary": export_result.get("data_summary"),
            "download_info": {
                "description": "Your complete data export is ready for download",
                "instructions": f"Use the download endpoint: GET /api/v1/users/me/export/{task_id}/download"
            }
        }
        
    except Exception as e:
        # Log export request failure
        log_security_event(
            event_type="data_export_request_failed",
            details={
                "user_id": current_user.id,
                "email": current_user.email,
                "error": str(e),
                "error_type": type(e).__name__,
                "request_timestamp": datetime.utcnow().isoformat()
            },
            level="error",
            user_id=current_user.id
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete data export. Please try again or contact support."
        )


@router.get("/me/export/{task_id}/status")
async def get_export_status(
    task_id: str,
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Check the status of a data export task.
    
    This endpoint allows users to check the progress of their data export request.
    
    Args:
        task_id: The task ID returned from the export request
        
    Returns:
        Dictionary containing task status and results (if completed)
    """
    
    try:
        # Get task status using service
        response_data = export_service.get_export_status(task_id)
        response_data.update({
            "user_id": current_user.id,
            "checked_at": datetime.utcnow().isoformat()
        })
        
        # Add additional information based on status
        if response_data.get("status") == "SUCCESS":
            response_data["download_instructions"] = "Your export file is ready for download"
            
            # Log successful export completion check
            log_security_event(
                event_type="data_export_status_checked_success",
                details={
                    "user_id": current_user.id,
                    "task_id": task_id,
                    "completion_timestamp": response_data.get("completed_at")
                },
                level="info",
                user_id=current_user.id
            )
            
        elif response_data.get("status") == "FAILURE":
            response_data["retry_instructions"] = "You can request a new export if needed"
            
            # Log export failure check
            log_security_event(
                event_type="data_export_status_checked_failure",
                details={
                    "user_id": current_user.id,
                    "task_id": task_id,
                    "error": response_data.get("error", "Unknown error")
                },
                level="error",
                user_id=current_user.id
            )
        
        return response_data
        
    except Exception as e:
        log_security_event(
            event_type="data_export_status_check_failed",
            details={
                "user_id": current_user.id,
                "task_id": task_id,
                "error": str(e)
            },
            level="error",
            user_id=current_user.id
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check export status. Please try again."
        )


@router.get("/me/export/{task_id}/download")
async def download_export_file(
    task_id: str,
    current_user: User = Depends(get_current_user)
) -> FileResponse:
    """
    Download the exported data file for a completed export task.
    
    This endpoint allows users to download their completed data export files.
    
    Args:
        task_id: The task ID returned from the export request
        
    Returns:
        FileResponse containing the exported data file
    """
    
    try:
        # Get task status to verify it's completed and get file path
        response_data = export_service.get_export_status(task_id)
        
        # Check if export was successful
        if response_data.get("status") != "SUCCESS":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Export not found or failed. Please request a new export."
            )
        
        # Get file path from response
        file_path = response_data.get("file_path")
        if not file_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Export file not found."
            )
        
        # Verify file exists
        from pathlib import Path
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Export file not found on disk."
            )
        
        # Log download attempt for security audit
        log_security_event(
            event_type="data_export_download_requested",
            details={
                "user_id": current_user.id,
                "task_id": task_id,
                "file_path": file_path,
                "download_timestamp": datetime.utcnow().isoformat()
            },
            level="info",
            user_id=current_user.id
        )
        
        # Return file as download
        return FileResponse(
            path=str(file_path_obj),
            filename=file_path_obj.name,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename={file_path_obj.name}",
                "Content-Type": "application/json; charset=utf-8"
            }
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
        
    except Exception as e:
        # Log download failure for security audit
        log_security_event(
            event_type="data_export_download_failed",
            details={
                "user_id": current_user.id,
                "task_id": task_id,
                "error": str(e),
                "download_timestamp": datetime.utcnow().isoformat()
            },
            level="error",
            user_id=current_user.id
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to download export file. Please try again."
        )


@router.delete("/me/activity", status_code=status.HTTP_200_OK)
async def clear_user_activity_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Clear all activity data for the authenticated user while preserving the account.
    
    This endpoint permanently deletes all user activity history including:
    - Goals (2-week and long-term)
    - Habits and habit completions
    - Mood entries
    - Journal collections and entries
    - Gratitude entries
    - Study sets and flashcards
    - Mantras and user statistics
    - Calendar entries and associated data
    - Quick access links
    - Pomodoro settings
    
    The core user account remains active and untouched.
    This operation cannot be undone - all activity data will be permanently lost.
    
    Security Features:
    - Requires JWT authentication
    - Scoped to authenticated user only (cannot delete other users' data)
    - Uses parameterized queries to prevent SQL injection
    - Comprehensive audit logging
    - Transaction rollback on any error
    
    Returns:
        JSON response with deletion confirmation and summary of deleted data
    """
    
    try:
        # Log activity deletion request for security audit
        log_security_event(
            event_type="activity_deletion_requested",
            details={
                "user_id": current_user.id,
                "email": current_user.email,
                "request_timestamp": datetime.utcnow().isoformat()
            },
            level="warning",
            user_id=current_user.id
        )
        
        # Perform secure bulk deletion of all activity data
        deletion_result = await crud_activity.delete_all_activity_data(db, current_user.id)
        
        # Log successful deletion
        log_security_event(
            event_type="activity_deletion_completed",
            details={
                "user_id": current_user.id,
                "email": current_user.email,
                "deletion_summary": deletion_result["deletion_summary"],
                "completion_timestamp": deletion_result["deleted_at"],
                "status": "success"
            },
            level="info",
            user_id=current_user.id
        )
        
        return {
            "message": "All activity data has been permanently cleared",
            "status": "success",
            "user_account_preserved": True,
            "deleted_at": deletion_result["deleted_at"],
            "deletion_summary": deletion_result["deletion_summary"]
        }
        
    except ValueError as ve:
        # Handle user validation errors
        log_security_event(
            event_type="activity_deletion_failed",
            details={
                "user_id": current_user.id,
                "error": str(ve),
                "error_type": "validation_error",
                "request_timestamp": datetime.utcnow().isoformat()
            },
            level="error",
            user_id=current_user.id
        )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user or user account is inactive"
        )
        
    except Exception as e:
        # Log deletion failure for security audit
        log_security_event(
            event_type="activity_deletion_failed",
            details={
                "user_id": current_user.id,
                "email": current_user.email,
                "error": str(e),
                "error_type": type(e).__name__,
                "request_timestamp": datetime.utcnow().isoformat()
            },
            level="error",
            user_id=current_user.id
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear activity data. Please try again or contact support."
        )


@router.delete("/me", status_code=status.HTTP_200_OK)
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Delete the current user's account and all associated data permanently.
    
    This endpoint:
    - Deletes the user account and all related data (goals, habits, mood entries, etc.)
    - Uses CASCADE relationships to ensure complete data removal
    - Logs the deletion event for security audit
    - Cannot be undone - all data will be permanently lost
    
    Requires authentication via JWT token.
    """
    
    try:
        # Get user ID for logging (before deletion)
        user_id = current_user.id
        user_email = current_user.email
        
        # Log the account deletion attempt for security audit
        log_security_event(
            event_type="account_deletion_initiated",
            details={
                "user_id": user_id,
                "email": user_email,
                "deletion_timestamp": datetime.utcnow().isoformat()
            },
            level="warning",
            user_id=user_id
        )
        
        # Delete the user - CASCADE relationships will handle all related data
        await db.delete(current_user)
        await db.commit()
        
        # Log successful deletion (using user_id since user no longer exists)
        log_security_event(
            event_type="account_deletion_completed",
            details={
                "user_id": user_id,
                "email": user_email,
                "deletion_timestamp": datetime.utcnow().isoformat(),
                "status": "success"
            },
            level="info"
        )
        
        return {
            "message": "Account and all associated data have been permanently deleted",
            "status": "success",
            "deleted_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        # Rollback any partial changes
        await db.rollback()
        
        # Log deletion failure for security audit
        log_security_event(
            event_type="account_deletion_failed",
            details={
                "user_id": current_user.id,
                "email": current_user.email,
                "error": str(e),
                "deletion_timestamp": datetime.utcnow().isoformat()
            },
            level="error",
            user_id=current_user.id
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete account. Please try again or contact support."
        ) 


@router.delete("/account/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_own_account(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    user_id = current_user.id  # Cache before deletion to avoid MissingGreenlet error
    print(f"[DEBUG] Account deletion requested for user_id={user_id}")
    try:
        from app.core.security import log_security_event
        from app.core.enhanced_auth import enhanced_auth_service
        from app.db.models import TokenBlacklist, DeletedEmail
        from jose import jwt, JWTError
        
        log_security_event(
            event_type="account_deletion_requested",
            details={"user_id": user_id, "timestamp": datetime.utcnow().isoformat()},
            level="info",
            user_id=user_id
        )
        
        # Blacklist current tokens before deleting user
        access_token = enhanced_auth_service.extract_token_from_request(request)
        refresh_token = enhanced_auth_service.extract_refresh_token_from_request(request)
        
        if access_token:
            try:
                payload = jwt.decode(access_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                expires_at = datetime.fromtimestamp(payload["exp"])
                await TokenBlacklist.add_token(db, access_token, expires_at)
                print(f"[DEBUG] Blacklisted access token for user_id={user_id}")
            except JWTError:
                pass
        
        if refresh_token:
            try:
                payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                expires_at = datetime.fromtimestamp(payload["exp"])
                await TokenBlacklist.add_token(db, refresh_token, expires_at)
                print(f"[DEBUG] Blacklisted refresh token for user_id={user_id}")
            except JWTError:
                pass
        
        # Record the deleted email before deleting the user
        user_email = current_user.email
        await DeletedEmail.add_deleted_email(db, user_email, user_id)
        print(f"[DEBUG] Recorded deleted email: {user_email}")
        
        print(f"[DEBUG] Deleting user_id={user_id} from database...")
        await db.delete(current_user)
        await db.commit()
        print(f"[DEBUG] Account deletion successful for user_id={user_id}")
        log_security_event(
            event_type="account_deletion_completed",
            details={"user_id": user_id, "timestamp": datetime.utcnow().isoformat()},
            level="info",
            user_id=user_id
        )
        
        # Create response and clear auth cookies
        response = Response(status_code=204)
        enhanced_auth_service.clear_auth_cookies(response)
        return response
    except Exception as e:
        await db.rollback()
        from app.core.security import log_security_event
        print(f"[ERROR] Account deletion error for user_id={user_id}: {e} ({type(e)})")
        print(traceback.format_exc())
        log_security_event(
            event_type="account_deletion_failed",
            details={"user_id": user_id, "error": str(e)},
            level="error",
            user_id=user_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete account. Please try again or contact support."
        ) 