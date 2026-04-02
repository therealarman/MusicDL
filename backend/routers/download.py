from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from ..models.schemas import DownloadRequest, StartDownloadResponse
from ..services.queue import cancel_job, create_job, jobs, run_download_job

router = APIRouter()


@router.post("/download", response_model=StartDownloadResponse)
async def start_download(
    request: DownloadRequest,
    background_tasks: BackgroundTasks,
) -> StartDownloadResponse:
    if not request.tracks:
        raise HTTPException(400, "No tracks provided")

    job_id = create_job(request.tracks, request.settings)
    background_tasks.add_task(run_download_job, job_id)

    return StartDownloadResponse(job_id=job_id, total_tracks=len(request.tracks))


@router.get("/download/{job_id}/{track_id}")
async def download_track_file(job_id: str, track_id: str) -> FileResponse:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    file_path = job.file_paths.get(track_id)
    if not file_path:
        raise HTTPException(404, "File not ready or not found")

    p = Path(file_path)
    if not p.exists():
        raise HTTPException(404, "File no longer available (may have been cleaned up)")

    return FileResponse(str(p), filename=p.name, media_type="application/octet-stream")


@router.get("/batch/{job_id}")
async def download_batch_zip(job_id: str) -> FileResponse:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if not job.zip_path:
        raise HTTPException(400, "Batch zip not ready yet")

    p = Path(job.zip_path)
    if not p.exists():
        raise HTTPException(404, "Zip file no longer available")

    return FileResponse(str(p), filename="music_download.zip", media_type="application/zip")


@router.post("/cancel/{job_id}")
async def cancel_download(job_id: str) -> dict:
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    cancel_job(job_id)
    return {"status": "cancelled", "job_id": job_id}


@router.get("/job/{job_id}")
async def get_job_info(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "job_id": job_id,
        "status": job.status.value,
        "completed_tracks": job.completed,
        "failed_tracks": job.failed,
        "total_tracks": len(job.tracks),
        "zip_ready": job.zip_path is not None,
        "tracks": {
            tid: {
                "status": tp.status.value,
                "progress": tp.progress,
                "message": tp.message,
                "error": tp.error,
            }
            for tid, tp in job.track_progress.items()
        },
    }
