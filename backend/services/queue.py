"""
Download queue manager.

Each download job runs as an asyncio background task.
Progress is broadcast via per-job asyncio queues (for SSE streaming)
and also stored in a replay list (for clients that connect late).
"""
import asyncio
import logging
import os
import shutil
import stat
import tempfile
import threading
import uuid
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx

from ..config import settings
from ..models.schemas import (
    DownloadSettings,
    JobStatus,
    TrackInfo,
    TrackProgress,
    TrackStatus,
)
from .filename import apply_template
from .metadata import embed_metadata, _to_jpeg
from .youtube import youtube_service, preflight_check

logger = logging.getLogger(__name__)

# Transient HTTP errors worth retrying (403, throttle, rate-limit)
_TRANSIENT_MARKERS = ("403", "throttled", "rate limit", "too many requests", "429", "connection reset")


def _is_transient(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(m in msg for m in _TRANSIENT_MARKERS)


def _is_age_restricted(exc: Exception) -> bool:
    return "sign in to confirm your age" in str(exc).lower()


# ── Job state ─────────────────────────────────────────────────────────────────

class DownloadJob:
    def __init__(self, job_id: str, tracks: List[TrackInfo], dl_settings: DownloadSettings):
        self.job_id = job_id
        self.tracks = tracks
        self.settings = dl_settings
        self.status: JobStatus = JobStatus.PENDING

        self.track_progress: Dict[str, TrackProgress] = {
            t.id: TrackProgress(track_id=t.id) for t in tracks
        }
        self.completed = 0
        self.failed = 0

        # Replay buffer + live queue for SSE
        self.events: List[dict] = []
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.cancel_event: asyncio.Event = asyncio.Event()

        self.file_paths: Dict[str, str] = {}  # track_id -> absolute path
        self.zip_path: Optional[str] = None


# Global registry
jobs: Dict[str, DownloadJob] = {}


# ── Public API ─────────────────────────────────────────────────────────────────

def create_job(tracks: List[TrackInfo], dl_settings: DownloadSettings) -> str:
    job_id = str(uuid.uuid4())
    jobs[job_id] = DownloadJob(job_id, tracks, dl_settings)
    return job_id


def cancel_job(job_id: str) -> None:
    job = jobs.get(job_id)
    if job:
        job.cancel_event.set()


# ── Event helpers ──────────────────────────────────────────────────────────────

async def _emit(job: DownloadJob, event_type: str, data: dict) -> None:
    event = {"event_type": event_type, "data": data}
    job.events.append(event)
    await job.event_queue.put(event)


async def _track_update(
    job: DownloadJob,
    track_id: str,
    status: str,
    progress: float,
    message: str = "",
    error: Optional[str] = None,
) -> None:
    tp = job.track_progress[track_id]
    tp.status = TrackStatus(status)
    tp.progress = progress
    tp.message = message
    if error:
        tp.error = error
    payload: dict = {
        "track_id": track_id,
        "status": status,
        "progress": progress,
        "message": message,
    }
    if error:
        payload["error"] = error
    if tp.file_path:
        payload["file_path"] = tp.file_path
    await _emit(job, "track_update", payload)


# ── Batch cookie extraction ────────────────────────────────────────────────────

async def _extract_batch_cookies(browser: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract browser cookies to a private temp directory once per batch.

    Returns (cookie_file_path, tmp_dir) so the caller can delete the directory
    when the batch finishes.  Both values are None when no browser is selected
    or extraction fails.

    The cookie file is written to an isolated tempdir (not the user's save-to
    folder) and gets mode 0o600 so only the current user can read it.
    """
    if not browser:
        return None, None
    loop = asyncio.get_event_loop()

    def _do() -> Tuple[Optional[str], Optional[str]]:
        import yt_dlp
        tmpdir = tempfile.mkdtemp(prefix="musicdl_cookies_")
        cookie_file = os.path.join(tmpdir, "cookies.txt")
        try:
            with yt_dlp.YoutubeDL({
                "quiet": True,
                "no_warnings": True,
                "cookiesfrombrowser": (browser.lower(), None, None, None),
                "cookiefile": cookie_file,
            }):
                pass  # cookie extraction happens on context init
            if os.path.exists(cookie_file):
                try:
                    os.chmod(cookie_file, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
                except OSError:
                    pass  # best-effort on Windows
                return cookie_file, tmpdir
            logger.warning("Cookie extraction produced no file for browser '%s'", browser)
            shutil.rmtree(tmpdir, ignore_errors=True)
            return None, None
        except Exception as exc:
            shutil.rmtree(tmpdir, ignore_errors=True)
            logger.warning("Could not extract browser cookies for batch: %s", exc)
            return None, None

    return await loop.run_in_executor(None, _do)


# ── Main runner ────────────────────────────────────────────────────────────────

async def run_download_job(job_id: str) -> None:
    job = jobs.get(job_id)
    if not job:
        return

    job.status = JobStatus.RUNNING
    await _emit(job, "job_update", {
        "status": "running",
        "total_tracks": len(job.tracks),
        "completed_tracks": 0,
        "failed_tracks": 0,
    })

    if job.settings.output_dir:
        job_temp = Path(job.settings.output_dir)
    else:
        job_temp = Path(settings.TEMP_DIR) / job_id
    job_temp.mkdir(parents=True, exist_ok=True)

    # Log warnings for missing node / browser profile before any track starts
    preflight_check(job.settings.cookies_browser)

    # Extract cookies once for the whole batch into a private temp dir.
    # We delete the temp dir in the finally block regardless of success/failure.
    cookie_file, cookie_tmpdir = await _extract_batch_cookies(job.settings.cookies_browser)

    concurrency = settings.DOWNLOAD_CONCURRENCY
    semaphore = asyncio.Semaphore(concurrency)

    async def process(track: TrackInfo) -> None:
        if job.cancel_event.is_set():
            await _track_update(job, track.id, "cancelled", 0)
            return
        async with semaphore:
            await _download_track(job, track, job_temp, cookie_file)

    try:
        # Use as_completed so per-item completions surface immediately
        tasks = [asyncio.create_task(process(t)) for t in job.tracks]
        for fut in asyncio.as_completed(tasks):
            try:
                await fut
            except Exception:
                pass  # Already handled (and logged) inside _download_track

        if job.cancel_event.is_set():
            job.status = JobStatus.CANCELLED
            await _emit(job, "job_update", {"status": "cancelled"})
        else:
            if job.file_paths:
                await _create_zip(job, job_temp)
            job.status = JobStatus.DONE
            await _emit(job, "job_update", {
                "status": "done",
                "completed_tracks": job.completed,
                "failed_tracks": job.failed,
                "zip_ready": job.zip_path is not None,
            })
    finally:
        # Always remove the private cookie temp dir
        if cookie_tmpdir:
            shutil.rmtree(cookie_tmpdir, ignore_errors=True)

    await _emit(job, "done", {})


# ── Per-track downloader ───────────────────────────────────────────────────────

async def _download_track(
    job: DownloadJob,
    track: TrackInfo,
    job_temp: Path,
    cookie_file: Optional[str] = None,
) -> None:
    track_id = track.id
    fmt = job.settings.format.value
    quality = job.settings.quality.value

    try:
        # 1. Resolve YouTube URL(s) for Spotify tracks
        yt_url = track.youtube_url or (track.url if track.source.value == "youtube" else None)
        fallbacks: List[str] = []

        if not yt_url:
            await _track_update(job, track_id, "searching", 0, "Searching YouTube…")
            query = f"{track.artist} - {track.title}"
            loop = asyncio.get_event_loop()
            candidates = await loop.run_in_executor(
                None, youtube_service.search_video, query, track.duration_ms, job.settings.cookies_browser
            )
            if not candidates:
                raise RuntimeError(f"No YouTube match found for: {track.artist} - {track.title}")
            yt_url = candidates[0]
            fallbacks = candidates[1:]

        await _track_update(job, track_id, "downloading", 0, "Starting download…")

        # 2. Build output template
        filename = apply_template(job.settings.filename_template, track)
        out_template = str(job_temp / f"{filename}.%(ext)s")

        # 3. Download with live progress polling, fallback URLs, and transient-error retry
        dl_state = {"pct": 0.0, "stage": "downloading"}

        def on_progress(pct: float, stage: str) -> None:
            dl_state["pct"] = pct
            dl_state["stage"] = stage

        cancel = job.cancel_event

        async def poll_progress(done_event: asyncio.Event) -> None:
            while not done_event.is_set():
                if cancel.is_set():
                    break
                await _track_update(
                    job, track_id,
                    dl_state["stage"],
                    dl_state["pct"],
                    f"{dl_state['stage'].capitalize()}… {dl_state['pct']:.0f}%",
                )
                await asyncio.sleep(0.5)

        urls_to_try = [yt_url] + fallbacks
        file_path = None

        for i, attempt_url in enumerate(urls_to_try):
            if i > 0:
                dl_state["pct"] = 0.0
                dl_state["stage"] = "downloading"
                await _track_update(job, track_id, "downloading", 0, "Trying alternative source…")

            progress_done = asyncio.Event()
            poll_task = asyncio.create_task(poll_progress(progress_done))
            try:
                # Inner retry loop for transient 403 / throttle errors (up to 2 retries)
                for transient_try in range(3):
                    try:
                        file_path = await youtube_service.download_audio(
                            url=attempt_url,
                            output_template=out_template,
                            fmt=fmt,
                            quality=quality,
                            normalize=job.settings.normalize_audio,
                            on_progress=on_progress,
                            cookies_browser="" if cookie_file else job.settings.cookies_browser,
                            cookie_file=cookie_file or "",
                        )
                        break  # success
                    except Exception as exc:
                        if transient_try < 2 and _is_transient(exc):
                            wait = 5 * (2 ** transient_try)  # 5s, 10s
                            logger.warning(
                                "Transient error on '%s' (try %d/3), retrying in %ds: %s",
                                track.title, transient_try + 1, wait, exc,
                            )
                            await asyncio.sleep(wait)
                            continue
                        raise
                break  # URL attempt succeeded
            except Exception as exc:
                if i < len(urls_to_try) - 1 and _is_age_restricted(exc) and not job.settings.cookies_browser:
                    continue  # try next candidate URL
                raise
            finally:
                progress_done.set()
                await poll_task

        if job.cancel_event.is_set():
            await _track_update(job, track_id, "cancelled", 0)
            return

        # 4. Embed metadata
        await _track_update(job, track_id, "embedding", 88, "Embedding metadata…")

        album_art_data: Optional[bytes] = None
        if job.settings.embed_artwork and track.album_art_url:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(track.album_art_url)
                    if resp.status_code == 200:
                        album_art_data = resp.content
            except Exception:
                pass

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, embed_metadata, file_path, track, album_art_data)

        if job.settings.download_thumbnail and album_art_data:
            try:
                thumb_data = await loop.run_in_executor(None, _to_jpeg, album_art_data)
                thumb_path = Path(file_path).with_suffix('.jpg')
                thumb_path.write_bytes(thumb_data)
                job.file_paths[f"{track_id}_thumb"] = str(thumb_path)
            except Exception:
                pass

        job.file_paths[track_id] = file_path
        job.track_progress[track_id].file_path = file_path
        job.completed += 1

        await _track_update(job, track_id, "done", 100, "Complete!")
        await _emit(job, "job_update", {
            "status": "running",
            "completed_tracks": job.completed,
            "failed_tracks": job.failed,
            "total_tracks": len(job.tracks),
        })

    except Exception as exc:
        job.failed += 1
        msg = str(exc)
        await _track_update(job, track_id, "error", 0, msg, error=msg)
        await _emit(job, "log", {"message": f"Error – {track.title}: {msg}"})


# ── Zip creation ───────────────────────────────────────────────────────────────

async def _create_zip(job: DownloadJob, job_temp: Path) -> None:
    zip_path = str(Path(settings.TEMP_DIR) / f"{job.job_id}.zip")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _zip_files, job.file_paths, zip_path)
    job.zip_path = zip_path


def _zip_files(file_paths: Dict[str, str], zip_path: str) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in file_paths.values():
            p = Path(file_path)
            if p.exists():
                zf.write(file_path, p.name)
