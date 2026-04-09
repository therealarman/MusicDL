from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from ..services.spotify import spotify_service

router = APIRouter()


@router.get("/spotify/login")
async def spotify_login():
    """Redirect the user to Spotify's authorization page."""
    try:
        url = spotify_service.get_auth_url()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return RedirectResponse(url)


@router.get("/spotify/callback")
async def spotify_callback(code: str = "", error: str = ""):
    """Handle Spotify's redirect, exchange the code for tokens, then go home."""
    if error:
        raise HTTPException(status_code=400, detail=f"Spotify authorization denied: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    try:
        spotify_service.handle_callback(code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {e}")

    return RedirectResponse("/")
