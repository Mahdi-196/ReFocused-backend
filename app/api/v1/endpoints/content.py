from fastapi import APIRouter, HTTPException
import httpx
import random

router = APIRouter()

# Fallback quotes in case the API is unavailable
FALLBACK_QUOTES = [
    {
        "content": "The only way to do great work is to love what you do.",
        "author": "Steve Jobs",
        "tags": ["work", "passion"]
    },
    {
        "content": "Life is what happens when you're busy making other plans.",
        "author": "John Lennon",
        "tags": ["life", "wisdom"]
    },
    {
        "content": "The future belongs to those who believe in the beauty of their dreams.",
        "author": "Eleanor Roosevelt",
        "tags": ["future", "dreams"]
    }
]

@router.get("/quote", summary="Get a random quote", tags=["content"])
async def get_random_quote():
    """
    Fetch a random quote from the Quotable API and return it in a structured format.
    If the API is unavailable, returns a fallback quote.
    """
    try:
        # Try the main API first
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get("https://api.quotable.io/quotes/random")
                response.raise_for_status()
                data = response.json()
                quote = data[0]
                return {
                    "quote": quote["content"],
                    "author": quote["author"],
                    "tags": quote["tags"]
                }
            except (httpx.HTTPError, httpx.RequestError):
                # If main API fails, try the backup API
                response = await client.get("https://zenquotes.io/api/random")
                response.raise_for_status()
                data = response.json()
                return {
                    "quote": data[0]["q"],
                    "author": data[0]["a"],
                    "tags": ["wisdom"]
                }
    except Exception as e:
        print(f"Error fetching quote: {e}")
        # Return a random fallback quote
        fallback_quote = random.choice(FALLBACK_QUOTES)
        return {
            "quote": fallback_quote["content"],
            "author": fallback_quote["author"],
            "tags": fallback_quote["tags"],
            "note": "Using fallback quote as the external APIs are currently unavailable"
        } 