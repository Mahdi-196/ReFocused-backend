import httpx
import logging
from typing import Any, Dict, Optional

from app.core.config import settings


logger = logging.getLogger(__name__)


class EmailSubscriptionService:
    """Proxy service that forwards email-list actions to AWS API Gateway (Lambda)."""

    def __init__(self) -> None:
        # Base URL for API Gateway stage that fronts the Lambda
        # Allow optional stage prefix ("/v1" or empty)
        prefix = settings.EMAIL_API_PREFIX.strip()
        if prefix and not prefix.startswith("/"):
            prefix = f"/{prefix}"
        self.base_url: str = f"{settings.EMAIL_API_BASE_URL.rstrip('/')}{prefix}"
        self.timeout_seconds: float = 20.0
        logger.info("Email service initialized with base_url: %s", self.base_url)

    async def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        logger.debug("Calling email API URL: %s with payload: %s", url, payload)
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                headers = {"Content-Type": "application/json"}
                # Include API key if configured (API Gateway usage plans / custom authorizers)
                if settings.EMAIL_API_KEY:
                    headers["x-api-key"] = settings.EMAIL_API_KEY
                logger.debug("Request headers: %s", headers)
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                )
                logger.info("✅ Email API call %s -> %s", path, response.status_code)
                response.raise_for_status()
                data = response.json()
                # API Gateway Lambdas sometimes wrap in { body: string }
                if isinstance(data, dict) and "body" in data:
                    try:
                        import json as _json
                        return _json.loads(data["body"]) if isinstance(data["body"], str) else data["body"]
                    except Exception:
                        return data
                return data
        except httpx.HTTPStatusError as e:
            body_preview = e.response.text if e.response is not None else ""
            logger.error("❌ Email API HTTP error on %s: %s | %s", path, e, body_preview)
            raise
        except httpx.HTTPError as e:
            logger.error("❌ Email API transport error on %s: %s", path, e)
            raise
        except Exception as e:
            logger.error("❌ Email API unexpected error on %s: %s", path, e)
            raise

    async def subscribe(self, email: str) -> Dict[str, Any]:
        # Call the correct /refocusedSubscribe endpoint for subscription
        return await self._post("/refocusedSubscribe", {"email": email, "action": "subscribe"})

    async def unsubscribe(self, email: str) -> Dict[str, Any]:
        return await self._post("/unsubscribe", {"email": email, "action": "unsubscribe"})

    async def status(self, email: str) -> Dict[str, Any]:
        return await self._post("/status", {"email": email})


email_service = EmailSubscriptionService()


