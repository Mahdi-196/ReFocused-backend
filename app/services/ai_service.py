import httpx
import logging
import os
import sys
from typing import Dict, Any, Optional, List
from ..core.config import settings

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.base_url = "https://kzrybkpw5a.execute-api.us-east-1.amazonaws.com/api/ai"
        self.timeout = 30.0
        self.use_local_fallback = True  # Use local Lambda code when AWS fails
        
    async def get_quote_of_day(self) -> Optional[Dict[str, Any]]:
        """Get daily inspirational quote from AWS Lambda"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/quote-of-day",
                    headers={"Content-Type": "application/json"},
                    json={}  # Empty POST payload
                )
                logger.info(f"AWS Quote Response Status: {response.status_code}")
                logger.info(f"AWS Quote Response Headers: {dict(response.headers)}")
                logger.info(f"AWS Quote Response Text: {response.text}")
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"HTTP Error fetching quote: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Error response: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in get_quote_of_day: {e}")
            raise
    
    async def get_word_of_day(self) -> Optional[Dict[str, Any]]:
        """Get daily vocabulary word from AWS Lambda"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/word-of-day",
                    headers={"Content-Type": "application/json"},
                    json={}  # Empty POST payload
                )
                logger.info(f"AWS Word Response Status: {response.status_code}")
                logger.info(f"AWS Word Response Text: {response.text}")
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"HTTP Error fetching word: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Error response: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in get_word_of_day: {e}")
            raise
    
    async def get_mind_fuel(self) -> Optional[Dict[str, Any]]:
        """Get daily mind fuel content from AWS Lambda"""
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
            raise
        except Exception as e:
            logger.error(f"Unexpected error in get_mind_fuel: {e}")
            raise
    
    async def chat(
        self, 
        message: str, 
        user_id: str,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None
    ) -> Optional[Dict[str, Any]]:
        """Send chat message to AI via AWS Lambda"""
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