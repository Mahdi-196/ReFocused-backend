from pydantic import BaseModel, Field, validator, root_validator
from typing import Optional, Literal, List


FeatureSlug = Literal[
    "develop-ai",
    "collaboration",
    "gamification-system",
]


class VoteRequest(BaseModel):
    feature: Optional[FeatureSlug] = Field(
        None,
        description="One of the predefined features: develop-ai, collaboration, gamification-system.",
    )
    custom: Optional[str] = Field(
        None,
        description="Optional custom feature suggestion, up to 600 characters.",
    )

    @validator('custom')
    def validate_custom_length(cls, v):
        if v is None:
            return v
        if len(v) > 600:
            raise ValueError("Custom suggestion must be 600 characters or less")
        return v

    @root_validator(skip_on_failure=True)
    def at_least_one_field(cls, values):
        feature = values.get('feature')
        custom = values.get('custom')
        if not feature and not custom:
            raise ValueError("Either 'feature' or 'custom' must be provided")
        return values


class VoteResponse(BaseModel):
    status: str = Field(..., description="Result status, e.g., 'ok'")
    message: Optional[str] = Field(None, description="Optional message from gateway")
    vote_id: Optional[str] = Field(None, description="Identifier for recorded vote")


class FeatureTallyItem(BaseModel):
    key: str
    votes: int


class VoteStatsResponse(BaseModel):
    total: int
    items: List[FeatureTallyItem]


