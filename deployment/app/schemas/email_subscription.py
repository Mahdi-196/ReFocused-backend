"""
Email subscription schemas for the ReFocused API.
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class EmailSubscriptionRequest(BaseModel):
    """Request model for email subscription."""
    email: EmailStr = Field(..., description="Email address to subscribe")
    source: Optional[str] = Field("website", description="Source of the subscription")
    referrer: Optional[str] = Field(None, description="Referrer URL")
    utm_source: Optional[str] = Field(None, description="UTM source parameter")
    utm_medium: Optional[str] = Field(None, description="UTM medium parameter")
    utm_campaign: Optional[str] = Field(None, description="UTM campaign parameter")


class EmailSubscriptionResponse(BaseModel):
    """Response model for email subscription."""
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Human-readable message")
    status: str = Field(..., description="Subscription status")
    email: str = Field(..., description="The email address")
    subscribed_at: Optional[datetime] = Field(None, description="When the email was subscribed")
    subscription_id: Optional[int] = Field(None, description="Internal subscription ID")


class EmailUnsubscribeRequest(BaseModel):
    """Request model for email unsubscription."""
    email: EmailStr = Field(..., description="Email address to unsubscribe")


class EmailUnsubscribeResponse(BaseModel):
    """Response model for email unsubscription."""
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Human-readable message")
    status: str = Field(..., description="Unsubscription status")
    email: str = Field(..., description="The email address")
    unsubscribed_at: Optional[datetime] = Field(None, description="When the email was unsubscribed")


class EmailStatusRequest(BaseModel):
    """Request model for checking email subscription status."""
    email: EmailStr = Field(..., description="Email address to check status for")


class EmailStatusResponse(BaseModel):
    """Response model for email subscription status."""
    success: bool = Field(..., description="Whether the operation was successful")
    isSubscribed: bool = Field(..., description="Whether the email is currently subscribed")
    email: str = Field(..., description="The email address")
    data: Optional[dict] = Field(None, description="Subscription data if subscribed")
    message: str = Field(..., description="Human-readable message")
