from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class QuoteResponse(BaseModel):
    text: str = Field(..., description="The quote text")
    author: str = Field(..., description="The author of the quote")

class WordResponse(BaseModel):
    word: str = Field(..., description="The vocabulary word")
    pronunciation: str = Field(..., description="Phonetic pronunciation")
    definition: str = Field(..., description="Concise definition")
    example: str = Field(..., description="Example sentence")

class WeeklyFocus(BaseModel):
    focus: str = Field(..., description="Daily focus phrase")

class TipOfTheDay(BaseModel):
    tip: str = Field(..., description="Productivity tip")

class ProductivityHack(BaseModel):
    hack: str = Field(..., description="Productivity hack")

class BrainBoost(BaseModel):
    word: str = Field(..., description="Vocabulary word")
    definition: str = Field(..., description="Brief definition")

class MindfulnessMoment(BaseModel):
    moment: str = Field(..., description="Mindfulness exercise")

class MindFuelResponse(BaseModel):
    weeklyFocus: WeeklyFocus
    tipOfTheDay: TipOfTheDay
    productivityHack: ProductivityHack
    brainBoost: BrainBoost
    mindfulnessMoment: MindfulnessMoment

class ChatMessage(BaseModel):
    role: str = Field(..., description="Message role: user or assistant")
    content: str = Field(..., description="Message content")

class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    system_prompt: Optional[str] = Field(None, description="Custom system prompt")
    conversation_history: Optional[List[ChatMessage]] = Field(default=[], description="Previous messages")

class ChatResponse(BaseModel):
    response: str = Field(..., description="AI response")
    messages_remaining: int = Field(..., description="Messages remaining today")
    usage: Optional[Dict[str, Any]] = Field(None, description="Token usage information")
    ip_remaining: int = Field(..., description="Remaining messages for this IP today (max 50)")
    ip_reset_seconds: int = Field(..., description="Seconds until this IP quota resets")
    user_remaining: int = Field(..., description="Remaining messages for this user today")
    user_reset_seconds: int = Field(..., description="Seconds until this user quota resets")


class ChatQuotaResponse(BaseModel):
    user_remaining: int = Field(..., description="Remaining messages for this user today")
    user_reset_seconds: int = Field(..., description="Seconds until user quota resets")
    ip_remaining: int = Field(..., description="Remaining messages for this IP today")
    ip_reset_seconds: int = Field(..., description="Seconds until IP quota resets")

class ContentPopulationRequest(BaseModel):
    data_type: str = Field(
        ..., 
        description="Type of content to generate",
        pattern="^(journal-prompts|goals|affirmations|habits|meditation-sessions)$"
    )
    count: int = Field(default=1, ge=1, le=20, description="Number of items to generate")
    custom_prompt: Optional[str] = Field(None, description="Custom prompt override")

class ContentPopulationResponse(BaseModel):
    data_type: str = Field(..., description="Type of content generated")
    count: int = Field(..., description="Number of items generated")
    content: List[Dict[str, Any]] = Field(..., description="Generated content items")

class WritingPromptsResponse(BaseModel):
    prompts: List[str] = Field(..., description="List of 5 weekly writing prompts")

class AiSuggestion(BaseModel):
    title: str = Field(..., description="Suggestion title")
    category: str = Field(..., description="Suggestion category")
    prompt: str = Field(..., description="AI assistance prompt")
    color: str = Field(..., description="UI color for the suggestion")

class AiSuggestionsResponse(BaseModel):
    suggestions: List[AiSuggestion] = Field(..., description="List of 4 weekly AI suggestions")

class WeeklyThemeResponse(BaseModel):
    name: str = Field(..., description="Theme word")
    subtitle: str = Field(..., description="One line meaning or description")
    sentences: List[str] = Field(..., description="List of 3 insight sentences")
    fullText: str = Field(..., description="Complete formatted text")

class AIErrorResponse(BaseModel):
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    timestamp: Optional[str] = Field(None, description="Error timestamp")