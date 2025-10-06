import logging
from typing import Any, Dict

import httpx

from app.core.config import settings


logger = logging.getLogger(__name__)


class FeedbackService:
    def __init__(self) -> None:
        # Endpoint resolved lazily to avoid import-time failures in tests
        self.endpoint: str | None = None
        self.timeout_seconds: float = 20.0

    async def submit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Resolve endpoint on first use
        if not self.endpoint:
            # Use settings instead of direct os.getenv
            raw = getattr(settings, 'FEEDBACK_API_ENDPOINT', None) or getattr(settings, 'FEEDBACK_API_BASE_URL', None)
            if not raw:
                raise RuntimeError("Feedback endpoint not configured. Set FEEDBACK_API_ENDPOINT or FEEDBACK_API_BASE_URL in settings")
            self.endpoint = raw.rstrip('/')
        try:
            # Log upstream target and payload (both structured and console via uvicorn.error)
            logger.info("Feedback upstream POST %s", self.endpoint)
            logger.info("Feedback payload: %s", payload)
            console_logger = logging.getLogger("uvicorn.error")
            console_logger.info("[FEEDBACK DEBUG] POST %s", self.endpoint)
            console_logger.info("[FEEDBACK DEBUG] payload=%s", payload)
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                headers = {"Content-Type": "application/json"}
                if settings.FEEDBACK_API_KEY:
                    headers["x-api-key"] = settings.FEEDBACK_API_KEY
                # Log headers with API key redacted if present
                log_headers = dict(headers)
                if "x-api-key" in log_headers:
                    log_headers["x-api-key"] = "[REDACTED]"
                logger.info("Feedback headers: %s", log_headers)
                console_logger.info("[FEEDBACK DEBUG] headers=%s", log_headers)

                resp = await client.post(self.endpoint, headers=headers, json=payload)
                logger.info("Feedback upstream response status: %s", resp.status_code)
                console_logger.info("[FEEDBACK DEBUG] status=%s", resp.status_code)
                try:
                    preview = resp.text[:500]
                    logger.info("Feedback upstream response text (preview): %s", preview)
                    console_logger.info("[FEEDBACK DEBUG] body_preview=%s", preview)
                except Exception:
                    pass
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict) and "body" in data:
                    try:
                        import json as _json
                        return _json.loads(data["body"]) if isinstance(data["body"], str) else data["body"]
                    except Exception:
                        return data
                return data
        except httpx.HTTPStatusError as e:
            try:
                body_preview = e.response.text if e.response is not None else ""
                status_code = e.response.status_code if e.response is not None else "?"
                logger.error("Feedback API HTTP error status=%s body=%s", status_code, body_preview[:500])
                console_logger = logging.getLogger("uvicorn.error")
                console_logger.error("[FEEDBACK DEBUG] HTTP error status=%s body_preview=%s", status_code, body_preview[:500])
            except Exception:
                logger.error("Feedback API HTTP error: %s", e)
            raise
        except httpx.HTTPError as e:
            try:
                req_url = getattr(getattr(e, 'request', None), 'url', None)
                logger.error("Feedback API transport error: %s | url=%s", e, req_url)
                console_logger = logging.getLogger("uvicorn.error")
                console_logger.error("[FEEDBACK DEBUG] transport error: %s | url=%s", e, req_url)
            except Exception:
                logger.error("Feedback API transport error: %s", e)
            raise


feedback_service = FeedbackService()


