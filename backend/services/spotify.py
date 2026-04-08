import re
from typing import List, Tuple, Optional

from ..config import settings
from ..models.schemas import TrackInfo, SourceType


class SpotifyService:
    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if not settings.SPOTIFY_CLIENT_ID or not settings.SPOTIFY_CLIENT_SECRET:
                raise ValueError(
                    "Spotify API credentials not configured. "
                    "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in your .env file."
                )
            import spotipy
            from spotipy.oauth2 import SpotifyClientCredentials
            self._client = spotipy.Spotify(
                auth_manager=SpotifyClientCredentials(
                    client_id=settings.SPOTIFY_CLIENT_ID,
                    client_secret=settings.SPOTIFY_CLIENT_SECRET,
                )
            )
        return self._client

    def parse_url(self, url: str) -> Tuple[str, str]:
        """Parse Spotify URL and return (type, id)."""
        patterns = [
            r'spotify\.com/(track|album|playlist)/([A-Za-z0-9]+)',
            r'spotify:(track|album|playlist):([A-Za-z0-9]+)',
        ]
        for pattern in patterns:
            m = re.search(pattern, url)
            if m:
                return m.group(1), m.group(2)
        raise ValueError(f"Invalid Spotify URL: {url}")

    def _parse_track_data(
        self,
        data: dict,
        playlist_name: str = "",
        playlist_index: int = 0,
    ) -> Optional[TrackInfo]:
        """Convert raw Spotify track dict to TrackInfo."""
        track = data.get("track", data)
        if not track or not track.get("id"):
            return None

        artists = [a["name"] for a in track.get("artists", [])]
        album = track.get("album", {})
        release_date = album.get("release_date", "")
        year = release_date[:4] if release_date else ""

        images = album.get("images", [])
        album_art_url = images[0]["url"] if images else None
        album_artists = album.get("artists", [])
        album_artist = album_artists[0]["name"] if album_artists else (artists[0] if artists else "")

        return TrackInfo(
            id=track.get("id", ""),
            title=track.get("name", ""),
            artist=artists[0] if artists else "",
            artists=artists,
            album=album.get("name", ""),
            album_artist=album_artist,
            album_art_url=album_art_url,
            track_number=track.get("track_number", 0),
            disc_number=track.get("disc_number", 1),
            year=year,
            date=release_date,
            duration_ms=track.get("duration_ms", 0),
            isrc=track.get("external_ids", {}).get("isrc", ""),
            source=SourceType.SPOTIFY,
            url=track.get("external_urls", {}).get("spotify", ""),
            playlist_name=playlist_name,
            playlist_index=playlist_index,
        )

    def get_track(self, track_id: str) -> TrackInfo:
        track = self.client.track(track_id)
        result = self._parse_track_data(track)
        if not result:
            raise ValueError(f"Track not found: {track_id}")
        return result

    def get_album(self, album_id: str) -> Tuple[List[TrackInfo], str]:
        album = self.client.album(album_id)
        album_name = album["name"]
        tracks: List[TrackInfo] = []

        results = self.client.album_tracks(album_id, limit=50)
        items = list(results["items"])
        while results.get("next") and len(items) < settings.MAX_PLAYLIST_SIZE:
            results = self.client.next(results)
            items.extend(results.get("items", []))

        for i, item in enumerate(items[: settings.MAX_PLAYLIST_SIZE]):
            try:
                full_track = self.client.track(item["id"])
                track = self._parse_track_data(full_track, album_name, i + 1)
                if track:
                    tracks.append(track)
            except Exception:
                continue

        return tracks, album_name

    def get_playlist(self, playlist_id: str) -> Tuple[List[TrackInfo], str]:
        playlist = self.client.playlist(playlist_id, fields="id,name")
        playlist_name = playlist["name"]
        tracks: List[TrackInfo] = []

        # Use playlist_items() directly to avoid relying on playlist["tracks"],
        # which can be absent or None in some Spotify API responses.
        results = self.client.playlist_items(
            playlist_id,
            limit=100,
            additional_types=["track"],
        )
        items = list(results["items"])
        while results.get("next") and len(items) < settings.MAX_PLAYLIST_SIZE:
            results = self.client.next(results)
            items.extend(results.get("items", []))

        for i, item in enumerate(items[: settings.MAX_PLAYLIST_SIZE]):
            try:
                track = self._parse_track_data(item, playlist_name, i + 1)
                if track:
                    tracks.append(track)
            except Exception:
                continue

        return tracks, playlist_name


spotify_service = SpotifyService()
