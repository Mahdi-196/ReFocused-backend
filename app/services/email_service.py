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
        logger.info(
            "📧 EmailSubscriptionService initialized | base_url=%s | timeout=%ss | has_api_key=%s",
            self.base_url,
            self.timeout_seconds,
            bool(settings.EMAIL_API_KEY)
        )

    async def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        import time
        start_time = time.time()
        url = f"{self.base_url}{path}"

        logger.info(
            "📤 Email API Request START | endpoint=%s | url=%s | payload=%s",
            path, url, payload
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                headers = {"Content-Type": "application/json"}
                # Include API key if configured (API Gateway usage plans / custom authorizers)
                if settings.EMAIL_API_KEY:
                    headers["x-api-key"] = settings.EMAIL_API_KEY
                    logger.debug("🔑 API key included in request headers")

                logger.debug("📋 Request headers: %s", {k: v if k != "x-api-key" else "***" for k, v in headers.items()})

                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                )

                elapsed_ms = (time.time() - start_time) * 1000
                logger.info(
                    "📥 Email API Response | endpoint=%s | status=%s | elapsed_ms=%.2f",
                    path, response.status_code, elapsed_ms
                )

                response.raise_for_status()
                data = response.json()

                logger.debug("📦 Response data: %s", data)

                # API Gateway Lambdas sometimes wrap in { body: string }
                if isinstance(data, dict) and "body" in data:
                    logger.debug("🔄 Unwrapping API Gateway body wrapper")
                    try:
                        import json as _json
                        unwrapped = _json.loads(data["body"]) if isinstance(data["body"], str) else data["body"]
                        logger.debug("📦 Unwrapped data: %s", unwrapped)
                        return unwrapped
                    except Exception as parse_err:
                        logger.warning("⚠️ Failed to unwrap body, returning as-is: %s", parse_err)
                        return data

                logger.info("✅ Email API call SUCCESS | endpoint=%s | elapsed_ms=%.2f", path, elapsed_ms)
                return data

        except httpx.HTTPStatusError as e:
            elapsed_ms = (time.time() - start_time) * 1000
            body_preview = e.response.text if e.response is not None else ""
            status_code = e.response.status_code if e.response is not None else "N/A"
            logger.error(
                "❌ Email API HTTP Error | endpoint=%s | status=%s | elapsed_ms=%.2f | error=%s | response_body=%s",
                path, status_code, elapsed_ms, str(e), body_preview[:500]
            )
            raise
        except httpx.HTTPError as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(
                "❌ Email API Transport Error | endpoint=%s | elapsed_ms=%.2f | error_type=%s | error=%s",
                path, elapsed_ms, type(e).__name__, str(e)
            )
            raise
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(
                "❌ Email API Unexpected Error | endpoint=%s | elapsed_ms=%.2f | error_type=%s | error=%s",
                path, elapsed_ms, type(e).__name__, str(e),
                exc_info=True
            )
            raise

    async def subscribe(self, email: str) -> Dict[str, Any]:
        logger.info("🔔 SUBSCRIBE requested for email: %s", email)
        result = await self._post("/refocusedSubscribe", {"email": email, "action": "subscribe"})
        logger.info("🔔 SUBSCRIBE completed for email: %s | result: %s", email, result)
        return result

    async def unsubscribe(self, email: str) -> Dict[str, Any]:
        logger.info("🔕 UNSUBSCRIBE requested for email: %s", email)
        result = await self._post("/unsubscribe", {"email": email, "action": "unsubscribe"})
        logger.info("🔕 UNSUBSCRIBE completed for email: %s | result: %s", email, result)
        return result

    async def status(self, email: str) -> Dict[str, Any]:
        logger.info("❓ STATUS CHECK requested for email: %s", email)
        result = await self._post("/status", {"email": email})
        logger.info("❓ STATUS CHECK completed for email: %s | result: %s", email, result)
        return result


email_service = EmailSubscriptionService()


