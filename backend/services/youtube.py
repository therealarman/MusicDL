import logging
import os
import re
import shutil
import sys
import asyncio
import threading
from typing import List, Optional, Callable, Tuple
from pathlib import Path

from ..models.schemas import TrackInfo, SourceType

logger = logging.getLogger(__name__)


def _parse_yt_title(title: str, uploader: str = "") -> Tuple[str, str]:
    """Extract artist and song title from a YouTube video title."""
    patterns = [
        r'^(.+?)\s*[-–—]\s*(.+)$',   # Artist - Title
        r'^(.+?)\s*:\s+(.+)$',        # Artist: Title
    ]
    for i, pattern in enumerate(patterns):
        m = re.match(pattern, title.strip())
        if m:
            return m.group(1).strip(), m.group(2).strip()

    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', title.strip(), re.IGNORECASE)
    if by_match:
        return by_match.group(2).strip(), by_match.group(1).strip()

    return uploader or "Unknown Artist", title


_CLEAN_RE = re.compile(
    r'\b(clean|radio\s+edit|radio\s+version|censored|explicit\s+free|'
    r'edited|clean\s+version|clean\s+edit|sanitized)\b',
    re.IGNORECASE,
)


def _check_cookie_error(exc: Exception) -> None:
    """Re-raise cookie-related yt-dlp errors with clear, actionable messages."""
    msg = str(exc).lower()
    if "could not copy" in msg and "cookie" in msg:
        raise RuntimeError(
            "Browser cookie database is locked. "
            "Close your browser completely (all windows) and try again. "
            "Chrome, Edge, and Brave keep this file open while running."
        ) from exc
    if "dpapi" in msg or ("failed to decrypt" in msg and "cookie" in msg):
        raise RuntimeError(
            "Chrome v127+ uses App-Bound Encryption for cookies, which blocks external access on Windows. "
            "Use Firefox instead — it works without this restriction."
        ) from exc


def _browser_profile_exists(browser: str) -> bool:
    """Return False when the browser's profile directory is not found."""
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        local = os.environ.get("LOCALAPPDATA", "")
        paths: dict = {
            "firefox": os.path.join(appdata, "Mozilla", "Firefox", "Profiles"),
            "chrome": os.path.join(local, "Google", "Chrome", "User Data"),
            "chromium": os.path.join(local, "Chromium", "User Data"),
            "brave": os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data"),
            "edge": os.path.join(local, "Microsoft", "Edge", "User Data"),
            "opera": os.path.join(appdata, "Opera Software", "Opera Stable"),
            "vivaldi": os.path.join(local, "Vivaldi", "User Data"),
        }
    elif sys.platform == "darwin":
        paths = {
            "firefox": os.path.join(home, "Library", "Application Support", "Firefox", "Profiles"),
            "chrome": os.path.join(home, "Library", "Application Support", "Google", "Chrome"),
            "safari": os.path.join(home, "Library", "Cookies"),
        }
    else:
        paths = {
            "firefox": os.path.join(home, ".mozilla", "firefox"),
            "chrome": os.path.join(home, ".config", "google-chrome"),
        }
    profile_dir = paths.get(browser.lower())
    if profile_dir is None:
        return True  # Unknown browser — assume present
    return os.path.isdir(profile_dir)


def preflight_check(browser: str = "") -> None:
    """Log warnings (no crash) when node or browser cookies may be unavailable."""
    if shutil.which("node") is None:
        logger.warning(
            "Node.js not found on PATH — js_runtimes PO-token bypass will be skipped. "
            "Install Node.js from https://nodejs.org/ and restart to enable full age-gate bypass."
        )
    if browser:
        if not _browser_profile_exists(browser):
            logger.warning(
                "Browser '%s' profile directory not found — cookie access may fail. "
                "Make sure %s is installed and you have logged into Google.",
                browser, browser.title(),
            )
        locked = {"chrome", "chromium", "brave", "edge", "opera", "vivaldi"}
        if browser.lower() in locked:
            logger.info(
                "Browser '%s' selected for cookies — ensure ALL windows are fully "
                "closed before downloading (cookie DB is locked while browser is running).",
                browser,
            )


class YouTubeService:

    def _cookies_opt(self, browser: str = "") -> dict:
        if browser:
            # 4-tuple required by yt-dlp >= 2023.11 for cookiesfrombrowser
            return {"cookiesfrombrowser": (browser.lower(), None, None, None)}
        return {}

    def _quiet_opts(self, browser: str = "") -> dict:
        return {
            "quiet": True,
            "no_warnings": True,
            "js_runtimes": {"node": {}},
            **self._cookies_opt(browser),
        }

    def get_video_info(self, url: str) -> TrackInfo:
        import yt_dlp
        with yt_dlp.YoutubeDL(self._quiet_opts()) as ydl:
            info = ydl.extract_info(url, download=False)

        artist, title = _parse_yt_title(info.get("title", ""), info.get("uploader", ""))
        return TrackInfo(
            id=info.get("id", ""),
            title=title,
            artist=artist,
            artists=[artist],
            duration_ms=int(info.get("duration") or 0) * 1000,
            source=SourceType.YOUTUBE,
            url=url,
            youtube_url=url,
            album_art_url=info.get("thumbnail"),
        )

    def get_playlist_info(self, url: str) -> Tuple[List[TrackInfo], str]:
        import yt_dlp
        opts = {**self._quiet_opts(), "extract_flat": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        playlist_name = info.get("title", "YouTube Playlist")
        tracks: List[TrackInfo] = []

        for i, entry in enumerate(info.get("entries", []) or []):
            if not entry:
                continue
            vid_url = f"https://www.youtube.com/watch?v={entry.get('id', '')}"
            artist, title = _parse_yt_title(entry.get("title", ""), entry.get("uploader", ""))
            vid_id = entry.get("id", "")
            thumbnail = entry.get("thumbnail") or (
                f"https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg" if vid_id else None
            )
            tracks.append(
                TrackInfo(
                    id=vid_id,
                    title=title,
                    artist=artist,
                    artists=[artist],
                    duration_ms=int(entry.get("duration") or 0) * 1000,
                    source=SourceType.YOUTUBE,
                    url=vid_url,
                    youtube_url=vid_url,
                    album_art_url=thumbnail,
                    playlist_name=playlist_name,
                    playlist_index=i + 1,
                )
            )
        return tracks, playlist_name

    def search_video(self, query: str, duration_ms: Optional[int] = None, cookies_browser: str = "") -> List[str]:
        """Search YouTube and return candidate URLs, best match first."""
        import yt_dlp
        opts = {**self._quiet_opts(cookies_browser), "extract_flat": True}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                results = ydl.extract_info(f"ytsearch5:{query}", download=False)
        except Exception as exc:
            _check_cookie_error(exc)
            raise

        entries = [e for e in (results.get("entries") or []) if e and e.get("id")]

        if duration_ms:
            target_s = duration_ms / 1000

            def sort_key(e):
                is_clean = bool(_CLEAN_RE.search(e.get("title", "")))
                dur = e.get("duration")
                dur_diff = abs(dur - target_s) if dur and abs(dur - target_s) < 30 else float("inf")
                return (is_clean, dur_diff)

            entries.sort(key=sort_key)

        return [f"https://www.youtube.com/watch?v={e['id']}" for e in entries]

    async def download_audio(
        self,
        url: str,
        output_template: str,
        fmt: str = "mp3",
        quality: str = "320",
        normalize: bool = False,
        on_progress: Optional[Callable[[float, str], None]] = None,
        cookies_browser: str = "",
        cookie_file: str = "",
    ) -> str:
        """Download and convert audio. Returns actual output file path.

        Prefer cookie_file (pre-extracted per-batch) over cookies_browser to avoid
        concurrent reads from the browser cookie DB.
        """
        import yt_dlp

        dl_state = {"pct": 0.0, "status": "downloading"}

        def hook(d):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                if total > 0:
                    dl_state["pct"] = (downloaded / total) * 80
            elif d["status"] == "finished":
                dl_state["pct"] = 80
                dl_state["status"] = "converting"

        postprocessors = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": fmt if fmt != "best" else "mp3",
                "preferredquality": quality if quality != "best" else "0",
            }
        ]
        if normalize:
            postprocessors.append({"key": "FFmpegNormalize"})

        # Cookie settings: prefer pre-extracted batch file; fall back to live browser
        cookies_opts: dict = {}
        if cookie_file:
            cookies_opts["cookiefile"] = cookie_file
        elif cookies_browser:
            cookies_opts["cookiesfrombrowser"] = (cookies_browser.lower(), None, None, None)

        ydl_opts: dict = {
            "quiet": True,
            "no_warnings": True,
            "js_runtimes": {"node": {}},
            **cookies_opts,
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "postprocessors": postprocessors,
            "progress_hooks": [hook],
            "retries": 3,
            "fragment_retries": 3,
        }

        done_event = threading.Event()
        error_box: List[Exception] = []

        def run():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            except Exception as exc:
                error_box.append(exc)
            finally:
                done_event.set()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

        while not done_event.is_set():
            if on_progress:
                on_progress(dl_state["pct"], dl_state["status"])
            await asyncio.sleep(0.5)

        thread.join()

        if error_box:
            _check_cookie_error(error_box[0])
            raise error_box[0]

        ext = fmt if fmt != "best" else "mp3"
        actual = output_template.replace("%(ext)s", ext)
        p = Path(actual)
        if p.exists():
            return str(p)

        parent = p.parent
        stem = p.stem
        for f in parent.iterdir():
            if f.stem == stem:
                return str(f)

        return actual


youtube_service = YouTubeService()
