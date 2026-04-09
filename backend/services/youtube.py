import re
import asyncio
import threading
from typing import List, Optional, Callable, Tuple
from pathlib import Path

from ..models.schemas import TrackInfo, SourceType


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

    # "Title by Artist" pattern
    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', title.strip(), re.IGNORECASE)
    if by_match:
        return by_match.group(2).strip(), by_match.group(1).strip()

    return uploader or "Unknown Artist", title


class YouTubeService:

    def _quiet_opts(self) -> dict:
        return {"quiet": True, "no_warnings": True}

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

    def search_video(self, query: str, duration_ms: Optional[int] = None) -> List[str]:
        """Search YouTube and return candidate URLs, best match first."""
        import yt_dlp
        opts = {**self._quiet_opts(), "extract_flat": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            results = ydl.extract_info(f"ytsearch5:{query}", download=False)

        entries = [e for e in (results.get("entries") or []) if e and e.get("id")]

        if duration_ms:
            target_s = duration_ms / 1000

            def sort_key(e):
                dur = e.get("duration")
                if dur and abs(dur - target_s) < 30:
                    return abs(dur - target_s)
                return float("inf")

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
    ) -> str:
        """Download and convert audio. Returns actual output file path."""
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

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "postprocessors": postprocessors,
            "progress_hooks": [hook],
            "quiet": True,
            "no_warnings": True,
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
            raise error_box[0]

        # Resolve actual output path (yt-dlp replaces %(ext)s)
        ext = fmt if fmt != "best" else "mp3"
        actual = output_template.replace("%(ext)s", ext)
        p = Path(actual)
        if p.exists():
            return str(p)

        # Fallback: scan parent directory
        parent = p.parent
        stem = p.stem
        for f in parent.iterdir():
            if f.stem == stem:
                return str(f)

        return actual


youtube_service = YouTubeService()
