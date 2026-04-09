import re
from typing import List, Tuple, Optional

from ..config import settings
from ..models.schemas import TrackInfo, SourceType


class SpotifyService:
    def __init__(self):
        self._client = None
        self._oauth_manager = None

    def _require_credentials(self) -> None:
        if not settings.SPOTIFY_CLIENT_ID or not settings.SPOTIFY_CLIENT_SECRET:
            raise ValueError(
                "Spotify API credentials not configured. "
                "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in your .env file."
            )

    @property
    def oauth_manager(self):
        if self._oauth_manager is None:
            self._require_credentials()
            import spotipy  # noqa: F401
            from spotipy.oauth2 import SpotifyOAuth
            from spotipy.cache_handler import MemoryCacheHandler
            self._oauth_manager = SpotifyOAuth(
                client_id=settings.SPOTIFY_CLIENT_ID,
                client_secret=settings.SPOTIFY_CLIENT_SECRET,
                redirect_uri=settings.SPOTIFY_REDIRECT_URI,
                scope="playlist-read-private playlist-read-collaborative",
                open_browser=False,
                cache_handler=MemoryCacheHandler(),
            )
        return self._oauth_manager

    def get_auth_url(self) -> str:
        """Return the Spotify authorization URL to redirect the user to."""
        return self.oauth_manager.get_authorize_url()

    def handle_callback(self, code: str) -> None:
        """Exchange an authorization code for tokens and cache them in memory."""
        self._client = None  # Force client re-creation with the new token
        self.oauth_manager.get_access_token(code, as_dict=False, check_cache=False)

    @property
    def client(self):
        if self._client is None:
            # get_cached_token() refreshes automatically if the token is expired
            # and a refresh token is available.
            token_info = self.oauth_manager.get_cached_token()
            if not token_info:
                raise ValueError(
                    "Spotify not authenticated. "
                    "Visit /api/spotify/login to authorize the app."
                )
            import spotipy
            self._client = spotipy.Spotify(auth_manager=self.oauth_manager)
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
        # Spotify API returns the nested object as "item" (newer playlists endpoint)
        # or "track" (older endpoint / album tracks). Fall back to data itself for
        # direct track objects passed from get_track().
        track = data.get("item") or data.get("track") or data
        if not track or not track.get("id"):
            return None
        # Skip podcast episodes that appear in mixed playlists
        if track.get("type") == "episode":
            return None

        # Use `or` instead of `.get(key, default)` so that an explicit null
        # from the API (key present, value None) still falls back to the default.
        artist_objects = track.get("artists") or []
        artists = [a["name"] for a in artist_objects]
        album = track.get("album") or {}
        release_date = album.get("release_date") or ""
        year = release_date[:4] if release_date else ""

        images = album.get("images") or []
        album_art_url = images[0]["url"] if images else None
        album_artists = album.get("artists") or []
        album_artist = album_artists[0]["name"] if album_artists else (artists[0] if artists else "")

        external_ids = track.get("external_ids") or {}
        external_urls = track.get("external_urls") or {}

        return TrackInfo(
            id=track.get("id") or "",
            title=track.get("name") or "",
            artist=artists[0] if artists else "",
            artists=artists,
            album=album.get("name") or "",
            album_artist=album_artist,
            album_art_url=album_art_url,
            track_number=track.get("track_number") or 0,
            disc_number=track.get("disc_number") or 1,
            year=year,
            date=release_date,
            duration_ms=track.get("duration_ms") or 0,
            isrc=external_ids.get("isrc") or "",
            source=SourceType.SPOTIFY,
            url=external_urls.get("spotify") or "",
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
            except Exception as e:
                print(f"WARNING: skipping album track {i + 1}: {e}")
                continue

        return tracks, album_name

    def get_playlist(self, playlist_id: str) -> Tuple[List[TrackInfo], str]:
        playlist = self.client.playlist(playlist_id, fields="id,name")
        playlist_name = playlist["name"]
        tracks: List[TrackInfo] = []

        results = self.client.playlist_items(playlist_id, limit=100)
        items = list(results.get("items") or [])
        while results.get("next") and len(items) < settings.MAX_PLAYLIST_SIZE:
            results = self.client.next(results)
            items.extend(results.get("items") or [])

        for i, item in enumerate(items[: settings.MAX_PLAYLIST_SIZE]):
            try:
                track = self._parse_track_data(item, playlist_name, i + 1)
                if track:
                    tracks.append(track)
            except Exception as e:
                print(f"WARNING: skipping playlist track {i + 1}: {e}")
                continue

        return tracks, playlist_name


spotify_service = SpotifyService()
