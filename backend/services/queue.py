"""
Download queue manager.

Each download job runs as an asyncio background task.
Progress is broadcast via per-job asyncio queues (for SSE streaming)
and also stored in a replay list (for clients that connect late).
"""
import asyncio
import threading
import uuid
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

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
from .youtube import youtube_service


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

        # Final file paths
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
    await _emit(job, "track_update", payload)


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

    job_temp = Path(settings.TEMP_DIR) / job_id
    job_temp.mkdir(parents=True, exist_ok=True)

    semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_DOWNLOADS)

    async def process(track: TrackInfo) -> None:
        if job.cancel_event.is_set():
            await _track_update(job, track.id, "cancelled", 0)
            return
        async with semaphore:
            await _download_track(job, track, job_temp)

    await asyncio.gather(*[process(t) for t in job.tracks], return_exceptions=True)

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

    await _emit(job, "done", {})


# ── Per-track downloader ───────────────────────────────────────────────────────

def _is_age_restricted(exc: Exception) -> bool:
    return "sign in to confirm your age" in str(exc).lower()


async def _download_track(job: DownloadJob, track: TrackInfo, job_temp: Path) -> None:
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
                None, youtube_service.search_video, query, track.duration_ms
            )
            if not candidates:
                raise RuntimeError(f"No YouTube match found for: {track.artist} - {track.title}")
            yt_url = candidates[0]
            fallbacks = candidates[1:]

        await _track_update(job, track_id, "downloading", 0, "Starting download…")

        # 2. Build output template
        filename = apply_template(job.settings.filename_template, track)
        out_template = str(job_temp / f"{filename}.%(ext)s")

        # 3. Download (with live progress polling, retrying on age restriction)
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
                file_path = await youtube_service.download_audio(
                    url=attempt_url,
                    output_template=out_template,
                    fmt=fmt,
                    quality=quality,
                    normalize=job.settings.normalize_audio,
                    on_progress=on_progress,
                )
                break  # success — stop trying
            except Exception as exc:
                if i < len(urls_to_try) - 1 and _is_age_restricted(exc):
                    continue
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

        # Optionally save cover art as a separate JPEG alongside the audio file
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
