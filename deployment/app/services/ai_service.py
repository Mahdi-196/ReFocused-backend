import httpx
import logging
import os
import sys
from typing import Dict, Any, Optional, List
from ..core.config import settings

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.base_url = settings.AI_API_BASE_URL
        self.timeout = 30.0
        self.use_local_fallback = True  # Use local Lambda code when AWS fails
        # AI services re-enabled - will work once App Runner is removed from VPC
        # See AI_SERVICES_STATUS.md for instructions to restore functionality
        self.disabled_for_testing = False

    async def get_quote_of_day(self) -> Optional[Dict[str, Any]]:
        """Get daily inspirational quote from AWS Lambda"""
        # TEMPORARY DISABLE - Testing auth without external calls
        if self.disabled_for_testing:
            logger.info("AI Service temporarily disabled - returning fallback quote")
            return {
                "text": "The journey of a thousand miles begins with a single step.",
                "author": "Lao Tzu"
            }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/quote-of-day",
                    headers={"Content-Type": "application/json"},
                    json={}  # Empty POST payload
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Quote service error: {type(e).__name__}")
            return {
                "text": "The journey of a thousand miles begins with a single step.",
                "author": "Lao Tzu"
            }
    
    async def get_word_of_day(self) -> Optional[Dict[str, Any]]:
        """Get daily vocabulary word from AWS Lambda"""
        # TEMPORARY DISABLE - Testing auth without external calls
        if self.disabled_for_testing:
            logger.info("AI Service temporarily disabled - returning fallback word")
            return {
                "word": "resilience",
                "pronunciation": "ri-ˈzil-yən(t)s",
                "definition": "The capacity to withstand or to recover quickly from difficulties",
                "example": "Her resilience helped her overcome every challenge."
            }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/word-of-day",
                    headers={"Content-Type": "application/json"},
                    json={}  # Empty POST payload
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Word service error: {type(e).__name__}")
            return {
                "word": "resilience",
                "pronunciation": "ri-ˈzil-yən(t)s",
                "definition": "The capacity to withstand or to recover quickly from difficulties",
                "example": "Her resilience helped her overcome every challenge."
            }
    
    async def get_mind_fuel(self) -> Optional[Dict[str, Any]]:
        """Get daily mind fuel content from AWS Lambda"""
        # TEMPORARY DISABLE - Testing auth without external calls
        if self.disabled_for_testing:
            logger.info("AI Service temporarily disabled - returning fallback mind fuel")
            return {
                "weeklyFocus": {"focus": "Progress over perfection"},
                "tipOfTheDay": {"tip": "Start your day with one small win"},
                "productivityHack": {"hack": "Use the 2-minute rule for quick tasks"},
                "brainBoost": {"word": "focus", "definition": "Concentrated attention or effort"},
                "mindfulnessMoment": {"moment": "Take 3 deep breaths and notice how you feel"}
            }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/mind-fuel",
                    headers={"Content-Type": "application/json"},
                    json={}  # Empty POST payload
                )
                logger.info(f"AWS MindFuel Response Status: {response.status_code}")
                logger.info(f"AWS MindFuel Response Text: {response.text}")
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"HTTP Error fetching mind fuel: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Error response: {e.response.text}")
            return {
                "weeklyFocus": {"focus": "Progress over perfection"},
                "tipOfTheDay": {"tip": "Start your day with one small win"},
                "productivityHack": {"hack": "Use the 2-minute rule for quick tasks"},
                "brainBoost": {"word": "focus", "definition": "Concentrated attention or effort"},
                "mindfulnessMoment": {"moment": "Take 3 deep breaths and notice how you feel"}
            }
        except Exception as e:
            logger.error(f"Unexpected error in get_mind_fuel: {e}")
            return {
                "weeklyFocus": {"focus": "Progress over perfection"},
                "tipOfTheDay": {"tip": "Start your day with one small win"},
                "productivityHack": {"hack": "Use the 2-minute rule for quick tasks"},
                "brainBoost": {"word": "focus", "definition": "Concentrated attention or effort"},
                "mindfulnessMoment": {"moment": "Take 3 deep breaths and notice how you feel"}
            }
    
    async def chat(
        self,
        message: str,
        user_id: str,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None
    ) -> Optional[Dict[str, Any]]:
        """Send chat message to AI via AWS Lambda"""
        # TEMPORARY DISABLE - Testing auth without external calls
        if self.disabled_for_testing:
            logger.info("AI Service temporarily disabled - returning fallback chat response")
            return {
                "response": "AI chat is temporarily disabled for testing. This feature will be restored soon.",
                "messages_remaining": 100,
                "usage": {},
                "ip_remaining": 50,
                "ip_reset_seconds": 86400,
                "user_remaining": 100,
                "user_reset_seconds": 86400
            }

        try:
            payload = {
                "message": message,
                "systemPrompt": system_prompt,
                "conversationHistory": conversation_history or []
            }
            
            headers = {
                "Content-Type": "application/json",
                "X-User-ID": user_id
            }
            
            logger.info(f"Sending chat request to: {self.base_url}/chat")
            logger.info(f"Payload: {payload}")
            logger.info(f"Headers: {headers}")
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat",
                    json=payload,
                    headers=headers
                )
                logger.info(f"AWS Chat Response Status: {response.status_code}")
                logger.info(f"AWS Chat Response Text: {response.text}")
                
                if response.status_code == 429:
                    return {"error": "rate_limit_exceeded", "message": "Daily message limit exceeded"}
                response.raise_for_status()
                
                # Parse Lambda response and extract the body
                result = response.json()
                
                # Lambda returns the response directly, not wrapped in a body
                if "body" in result:
                    # If Lambda wrapped response in body, extract it
                    if isinstance(result["body"], str):
                        import json
                        body_data = json.loads(result["body"])
                    else:
                        body_data = result["body"]
                else:
                    # Direct response from Lambda
                    body_data = result
                
                # Extract the actual response data
                if "response" in body_data:
                    return {
                        "response": body_data["response"],
                        "messages_remaining": body_data.get("messages_remaining", 0),
                        "usage": body_data.get("usage", {})
                    }
                else:
                    # Fallback for different response format
                    return body_data
                    
        except httpx.HTTPError as e:
            logger.error(f"HTTP Error in AI chat: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Error response: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in chat: {e}")
            raise
    
    async def populate_content(
        self,
        data_type: str,
        count: int = 1,
        custom_prompt: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Generate bulk content via AWS Lambda"""
        # TEMPORARY DISABLE - Testing auth without external calls
        if self.disabled_for_testing:
            logger.info("AI Service temporarily disabled - returning fallback populate content")
            return {
                "success": True,
                "count": 0,
                "message": "Content population temporarily disabled for testing"
            }

        try:
            payload = {
                "dataType": data_type,
                "count": min(max(count, 1), 20),
                "customPrompt": custom_prompt
            }
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/populate-data",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                logger.info(f"AWS PopulateContent Response Status: {response.status_code}")
                logger.info(f"AWS PopulateContent Response Text: {response.text}")
                response.raise_for_status()
                
                result = response.json()
                # Handle Lambda response format
                if "body" in result:
                    if isinstance(result["body"], str):
                        import json
                        return json.loads(result["body"])
                    return result["body"]
                return result
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP Error in content population: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Error response: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in populate_content: {e}")
            raise
    
    async def generate_content(self, data_type: str, custom_prompt: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Generate single content item via AWS Lambda"""
        try:
            return await self.populate_content(data_type, count=1, custom_prompt=custom_prompt)
        except Exception as e:
            logger.error(f"Error generating content: {e}")
            raise
    
    async def get_writing_prompts(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """Get weekly writing prompts from AWS Lambda"""
        # TEMPORARY DISABLE - Testing auth without external calls
        if self.disabled_for_testing:
            logger.info("AI Service temporarily disabled - returning fallback writing prompts")
            return {
                "prompts": [
                    "What moment this week made you feel most alive?",
                    "Describe a challenge you overcame recently.",
                    "What are you grateful for today?",
                    "What lesson did you learn this week?",
                    "How did you grow as a person this week?"
                ]
            }

        try:
            url = f"{self.base_url}/writing-prompts"
            if force_refresh:
                url += "?refresh=true"
                
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json={}  # Empty POST payload
                )
                logger.info(f"AWS WritingPrompts Response Status: {response.status_code}")
                logger.info(f"AWS WritingPrompts Response Text: {response.text}")
                response.raise_for_status()
                
                result = response.json()
                # Handle Lambda response format
                if "body" in result:
                    if isinstance(result["body"], str):
                        import json
                        return json.loads(result["body"])
                    return result["body"]
                return result
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP Error fetching writing prompts: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Error response: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in get_writing_prompts: {e}")
            raise
    
    async def get_ai_suggestions(self) -> Optional[Dict[str, Any]]:
        """Get weekly AI suggestions from AWS Lambda"""
        # TEMPORARY DISABLE - Testing auth without external calls
        if self.disabled_for_testing:
            logger.info("AI Service temporarily disabled - returning fallback AI suggestions")
            return {
                "suggestions": [
                    {
                        "title": "Morning Meditation",
                        "category": "Mindfulness",
                        "prompt": "Try a 5-minute meditation to start your day with clarity",
                        "color": "blue"
                    },
                    {
                        "title": "Daily Goal",
                        "category": "Productivity",
                        "prompt": "Set one small achievable goal for today",
                        "color": "green"
                    },
                    {
                        "title": "Movement Break",
                        "category": "Wellness",
                        "prompt": "Take a break and stretch every hour",
                        "color": "purple"
                    },
                    {
                        "title": "Gratitude Practice",
                        "category": "Mindfulness",
                        "prompt": "List three things you're grateful for",
                        "color": "orange"
                    }
                ]
            }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/ai-suggestions",
                    headers={"Content-Type": "application/json"},
                    json={}  # Empty POST payload
                )
                logger.info(f"AWS AISuggestions Response Status: {response.status_code}")
                logger.info(f"AWS AISuggestions Response Text: {response.text}")
                response.raise_for_status()
                
                result = response.json()
                # Handle Lambda response format
                if "body" in result:
                    if isinstance(result["body"], str):
                        import json
                        return json.loads(result["body"])
                    return result["body"]
                return result
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP Error fetching AI suggestions: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Error response: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in get_ai_suggestions: {e}")
            raise

    async def get_weekly_theme(self) -> Optional[Dict[str, Any]]:
        """Get weekly theme from AWS Lambda"""
        # TEMPORARY DISABLE - Testing auth without external calls
        if self.disabled_for_testing:
            logger.info("AI Service temporarily disabled - returning fallback weekly theme")
            return {
                "name": "Mindful Progress",
                "subtitle": "Focus on being present while moving forward",
                "sentences": [
                    "Small steps taken with awareness create lasting change.",
                    "Progress isn't about perfection, it's about persistence.",
                    "Being present in each moment amplifies your growth."
                ],
                "fullText": "Mindful Progress: Focus on being present while moving forward. Small steps taken with awareness create lasting change. Progress isn't about perfection, it's about persistence. Being present in each moment amplifies your growth."
            }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/weekly-theme",
                    headers={"Content-Type": "application/json"},
                    json={}  # Empty POST payload
                )
                logger.info(f"AWS WeeklyTheme Response Status: {response.status_code}")
                logger.info(f"AWS WeeklyTheme Response Text: {response.text}")
                response.raise_for_status()
                
                result = response.json()
                # Handle Lambda response format
                if "body" in result:
                    if isinstance(result["body"], str):
                        import json
                        return json.loads(result["body"])
                    return result["body"]
                return result
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP Error fetching weekly theme: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Error response: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in get_weekly_theme: {e}")
            raise

ai_service = AIService()