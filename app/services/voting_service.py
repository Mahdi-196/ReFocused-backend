import logging
from typing import Any, Dict
import os

import httpx

from app.core.config import settings


logger = logging.getLogger(__name__)


class FeatureVotingService:
    """Proxy service for feature voting via API Gateway → Lambda.

    Mirrors the style used by email/ai services with optional API key and
    tolerant response shape (Gateway may wrap body).
    """

    def __init__(self) -> None:
        self.timeout_seconds: float = 20.0
        raw = os.getenv("FEATURE_VOTING")
        if raw:
            base = raw.rstrip('/')
            # FEATURE_VOTING may point directly to the vote endpoint
            self.vote_url: str = base
            if base.rsplit('/', 1)[-1] == 'vote':
                self.stats_url: str = base.rsplit('/', 1)[0] + '/stats'
            else:
                self.stats_url: str = base + '/stats'
            # Base URL (without trailing segment) for completeness
            self.base_url: str = base.rsplit('/', 1)[0]
        else:
            prefix = settings.VOTING_API_PREFIX.strip()
            if prefix and not prefix.startswith("/"):
                prefix = f"/{prefix}"
            base_root = settings.VOTING_API_BASE_URL.rstrip('/')
            self.base_url: str = f"{base_root}{prefix}"
            self.vote_url: str = f"{self.base_url}/vote"
            self.stats_url: str = f"{self.base_url}/stats"

        # Keep logger.info only; remove console debug spam
        logger.info("Voting service configured: vote_url=%s stats_url=%s", self.vote_url, self.stats_url)

    async def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                headers = {"Content-Type": "application/json"}
                if settings.VOTING_API_KEY:
                    headers["x-api-key"] = settings.VOTING_API_KEY
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict) and "body" in data:
                    try:
                        import json as _json
                        return _json.loads(data["body"]) if isinstance(data["body"], str) else data["body"]
                    except Exception:
                        return data
                return data
        except httpx.HTTPStatusError as e:
            body_preview = e.response.text if e.response is not None else ""
            logger.error("Feature voting API HTTP error on %s: %s | %s", path, e, body_preview)
            raise
        except httpx.HTTPError as e:
            logger.error("Feature voting API transport error on %s: %s", path, e)
            raise

    async def _post_full(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # Debug logging (single channel)
            redacted_key = "[REDACTED]" if settings.VOTING_API_KEY else None
            logger.info("Voting upstream request: url=%s payload=%s api_key=%s", url, payload, redacted_key)
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                headers = {"Content-Type": "application/json"}
                if settings.VOTING_API_KEY:
                    headers["x-api-key"] = settings.VOTING_API_KEY
                logger.info("Voting upstream headers: %s", {**headers, **({"x-api-key": "[REDACTED]"} if "x-api-key" in headers else {})})
                response = await client.post(url, headers=headers, json=payload)
                logger.info("Voting upstream response status: %s", response.status_code)
                logger.info("Voting upstream response body preview: %s", response.text[:500])
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict) and "body" in data:
                    try:
                        import json as _json
                        return _json.loads(data["body"]) if isinstance(data["body"], str) else data["body"]
                    except Exception:
                        return data
                return data
        except httpx.HTTPStatusError as e:
            body_preview = e.response.text if e.response is not None else ""
            logger.error("Feature voting API HTTP error on %s: %s | %s", url, e, body_preview)
            raise
        except httpx.HTTPError as e:
            logger.error("Feature voting API transport error on %s: %s", url, e)
            raise

    async def cast_vote(self, vote_id: str) -> Dict[str, Any]:
        # Send both keys for compatibility with differing upstream expectations
        payload: Dict[str, Any] = {"voteId": vote_id, "featureId": vote_id}
        return await self._post_full(self.vote_url, payload)

    async def stats(self) -> Dict[str, Any]:
        return await self._post_full(self.stats_url, {})


voting_service = FeatureVotingService()


