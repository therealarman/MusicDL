import re
import uuid
from typing import Tuple

from fastapi import APIRouter, HTTPException

from ..models.schemas import FetchRequest, FetchResponse, SourceType, TrackInfo
from ..services.spotify import spotify_service
from ..services.youtube import youtube_service

router = APIRouter()


def _detect_source(url: str) -> str:
    if "spotify.com" in url or url.startswith("spotify:"):
        return "spotify"
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    return "unknown"


def _is_collection(url: str) -> bool:
    return any(kw in url for kw in ("playlist", "album", "list="))


def _assign_ids(tracks):
    for t in tracks:
        t.id = str(uuid.uuid4())
    return tracks


@router.post("/fetch", response_model=FetchResponse)
async def fetch_url(request: FetchRequest) -> FetchResponse:
    url = request.url.strip()
    source = _detect_source(url)

    if source == "unknown":
        raise HTTPException(
            400,
            detail=(
                "Unsupported URL. Please provide a Spotify or YouTube URL. "
                "Examples: https://open.spotify.com/track/... or https://www.youtube.com/watch?v=..."
            ),
        )

    try:
        if source == "spotify":
            content_type, spotify_id = spotify_service.parse_url(url)

            if content_type == "track":
                track = spotify_service.get_track(spotify_id)
                track.id = str(uuid.uuid4())
                return FetchResponse(
                    tracks=[track],
                    source_type=SourceType.SPOTIFY,
                    playlist_name="",
                    total_count=1,
                )
            elif content_type == "album":
                tracks, name = spotify_service.get_album(spotify_id)
                _assign_ids(tracks)
                return FetchResponse(
                    tracks=tracks,
                    source_type=SourceType.SPOTIFY,
                    playlist_name=name,
                    total_count=len(tracks),
                )
            elif content_type == "playlist":
                tracks, name = spotify_service.get_playlist(spotify_id)
                _assign_ids(tracks)
                return FetchResponse(
                    tracks=tracks,
                    source_type=SourceType.SPOTIFY,
                    playlist_name=name,
                    total_count=len(tracks),
                )
            else:
                raise HTTPException(400, f"Unsupported Spotify content type: {content_type}")

        else:  # youtube
            if _is_collection(url):
                tracks, name = youtube_service.get_playlist_info(url)
                _assign_ids(tracks)
                return FetchResponse(
                    tracks=tracks,
                    source_type=SourceType.YOUTUBE,
                    playlist_name=name,
                    total_count=len(tracks),
                )
            else:
                track = youtube_service.get_video_info(url)
                track.id = str(uuid.uuid4())
                return FetchResponse(
                    tracks=[track],
                    source_type=SourceType.YOUTUBE,
                    playlist_name="",
                    total_count=1,
                )

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Error fetching URL: {exc}")
