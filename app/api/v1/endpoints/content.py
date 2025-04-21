from fastapi import APIRouter, HTTPException
import httpx

router = APIRouter()

@router.get("/quote", summary="Get a random quote", tags=["content"])
async def get_random_quote():
    """
    Fetch a random quote from the external API and return it in a structured format.
    Handles errors gracefully and returns a 500 error if the fetch fails.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get("https://api.quotable.io/random")
            response.raise_for_status()
            data = response.json()
            return {
                "quote": data["content"],
                "author": data["author"],
                "tags": data["tags"]
            }
    except httpx.HTTPError as e:
        print(f"HTTP error fetching quote: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching quote: {str(e)}")
    except Exception as e:
        print(f"General error fetching quote: {e}")
        raise HTTPException(status_code=500, detail=f"General error fetching quote: {str(e)}") 