import asyncio
import shutil
import subprocess
import sys
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routers import download, fetch, status
from .services.filename import AVAILABLE_TOKENS, TEMPLATE_PRESETS

app = FastAPI(
    title="Music Downloader",
    description="Download music from Spotify and YouTube",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routes ─────────────────────────────────────────────────────────────────
app.include_router(fetch.router, prefix="/api")
app.include_router(download.router, prefix="/api")
app.include_router(status.router, prefix="/api")


@app.get("/api/health")
async def health_check() -> dict:
    checks: dict = {}

    # Check ffmpeg
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, timeout=5
        )
        checks["ffmpeg"] = result.returncode == 0
    except Exception:
        checks["ffmpeg"] = False

    # Check yt-dlp
    try:
        import yt_dlp  # noqa: F401
        checks["yt_dlp"] = True
    except ImportError:
        checks["yt_dlp"] = False

    checks["spotify_configured"] = bool(
        settings.SPOTIFY_CLIENT_ID and settings.SPOTIFY_CLIENT_SECRET
    )

    warnings = []
    if not checks["ffmpeg"]:
        warnings.append("ffmpeg not found — audio conversion unavailable")
    if not checks["yt_dlp"]:
        warnings.append("yt-dlp not installed — run: pip install yt-dlp")
    if not checks["spotify_configured"]:
        warnings.append("Spotify API credentials not set — Spotify features disabled")

    return {
        "status": "ok",
        "checks": checks,
        "warnings": warnings,
    }


@app.get("/api/tokens")
async def get_tokens() -> dict:
    return {
        "tokens": [
            {"token": k, "description": v[0], "example": v[1]}
            for k, v in AVAILABLE_TOKENS.items()
        ],
        "presets": [
            {"template": t, "label": l} for t, l in TEMPLATE_PRESETS
        ],
    }


# ── Startup ────────────────────────────────────────────────────────────────────

async def _cleanup_loop() -> None:
    """Delete temp files older than the configured interval."""
    interval = settings.FILE_CLEANUP_INTERVAL_MINUTES * 60
    while True:
        await asyncio.sleep(interval)
        cutoff = time.time() - interval
        temp_dir = Path(settings.TEMP_DIR)
        if temp_dir.exists():
            for item in temp_dir.iterdir():
                try:
                    if item.stat().st_mtime < cutoff:
                        if item.is_dir():
                            shutil.rmtree(item, ignore_errors=True)
                        else:
                            item.unlink(missing_ok=True)
                except Exception:
                    pass


@app.on_event("startup")
async def startup() -> None:
    Path(settings.DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.TEMP_DIR).mkdir(parents=True, exist_ok=True)

    # Warn about missing system deps
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, timeout=5)
    except Exception:
        print("WARNING: ffmpeg not found. Install it from https://ffmpeg.org/", file=sys.stderr)

    asyncio.create_task(_cleanup_loop())


# ── Frontend static files ──────────────────────────────────────────────────────
_frontend_dir = Path(__file__).parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )
