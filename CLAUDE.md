# MusicDownloader — CLAUDE.md

## What This Is

A full-stack web app for downloading music from Spotify and YouTube as audio files (MP3, FLAC, WAV, OGG, M4A) with embedded metadata and album art. Spotify tracks are matched to YouTube audio via search; YouTube URLs download directly.

## How to Run

```bash
# From repo root
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
# or double-click start.bat
```

Open http://localhost:8000. Health check: GET /api/health.

## Tech Stack

- **Backend**: Python 3.10, FastAPI, uvicorn, sse-starlette
- **Frontend**: Vanilla JS SPA + dark-theme CSS, served as static files from FastAPI
- **Audio**: yt-dlp (download) + ffmpeg (conversion/normalization)
- **Spotify**: spotipy with OAuth2 PKCE flow (lazy-initialized)
- **Metadata**: mutagen (MP3/FLAC/M4A/OGG tag embedding), Pillow (artwork)

## Project Layout

```
backend/
  main.py              FastAPI app, startup logic, static mount
  config.py            pydantic-settings — reads .env
  models/schemas.py    All Pydantic models and enums
  routers/
    fetch.py           POST /api/fetch — resolve URL → TrackInfo list
    download.py        POST /api/download, GET /api/download/{job_id}/{track_id}
                       GET /api/batch/{job_id}, POST /api/cancel/{job_id}
                       GET /api/job/{job_id}
    status.py          GET /api/status/{job_id} — SSE stream
    spotify_auth.py    GET /api/spotify/login, GET /api/spotify/callback
  services/
    spotify.py         SpotifyService — lazy spotipy client, parse/fetch tracks
    youtube.py         YouTubeService — yt-dlp wrapper, search, download_audio()
    metadata.py        mutagen tag embedding
    filename.py        14-token filename template system + 5 presets
    queue.py           DownloadJob, run_download_job(), SSE event management
frontend/
  index.html
  src/
    app.js             ~600-line vanilla JS SPA
    styles/main.css    Dark theme CSS variables
.env                   Local config (never committed)
.env.example           Template for .env
start.bat              Windows launcher
```

## Key Architecture Points

**Download flow:**
1. `POST /api/fetch` → returns `TrackInfo[]` (metadata only, no download)
2. `POST /api/download` → creates a `DownloadJob`, runs in FastAPI background task, returns `job_id`
3. `GET /api/status/{job_id}` → SSE stream of `track_update` / `job_update` / `done` events
4. `GET /api/download/{job_id}/{track_id}` → serves completed file
5. `GET /api/batch/{job_id}` → serves zip of all completed files

**Concurrency model:** yt-dlp runs in `threading.Thread` (blocking I/O), progress polled by asyncio every 0.5s. Semaphore limits to `MAX_CONCURRENT_DOWNLOADS` (default 3).

**SSE replay buffer:** `job.events` list replays all past events to late-connecting clients. New events go into `job.event_queue` (asyncio.Queue). Heartbeat every 25s to keep connection alive.

**Spotify auth:** OAuth2 flow via `/api/spotify/login` → Spotify → `/api/spotify/callback`. Token cached in memory (lost on server restart). Credentials must be set in `.env` first.

**Spotify → YouTube matching:** `youtube_service.search_video(query, duration_ms)` does `ytsearch5:` and picks closest duration match (within 30s). Falls back through candidates on age-restriction errors.

**Frontend static mount:** `app.mount("/", StaticFiles(..., html=True))` must be **last** in main.py — after all `/api` routes.

## Configuration (.env)

| Variable | Default | Description |
|---|---|---|
| `SPOTIFY_CLIENT_ID` | — | Required for Spotify features |
| `SPOTIFY_CLIENT_SECRET` | — | Required for Spotify features |
| `SPOTIFY_REDIRECT_URI` | `http://127.0.0.1:8000/api/spotify/callback` | Must match Spotify dashboard |
| `DOWNLOAD_DIR` | `./downloads` | Where finished files land |
| `TEMP_DIR` | `./temp` | Working dir during download |
| `MAX_CONCURRENT_DOWNLOADS` | `3` | Parallel download limit |
| `FILE_CLEANUP_INTERVAL_MINUTES` | `60` | Temp file TTL |
| `MAX_PLAYLIST_SIZE` | `500` | Max tracks fetched from playlists |
| `HOST` | `0.0.0.0` | Server bind host |
| `PORT` | `8000` | Server bind port |

## Filename Template Tokens

14 tokens available: `{title}`, `{artist}`, `{artists}`, `{album}`, `{album_artist}`, `{track_number}`, `{disc_number}`, `{year}`, `{date}`, `{genre}`, `{duration}`, `{playlist}`, `{playlist_index}`, `{source}`

Illegal filename characters are replaced with `_`. Filenames are truncated at 200 chars.

## Audio Formats & Quality

Formats: `mp3`, `flac`, `wav`, `ogg`, `m4a`
Quality (bitrate for lossy): `128`, `192`, `256`, `320`, `best`

## System Dependencies

- **ffmpeg** — must be in PATH; required for audio conversion. Install from https://ffmpeg.org/
- **Python 3.10+**
- All Python deps in `backend/requirements.txt`

## Common Gotchas

- Spotify token is in-memory — restarting the server requires re-authenticating via `/api/spotify/login`
- The `.env` file and `.cache` (legacy spotipy cache) are gitignored
- `yt-dlp` is imported lazily inside methods — import errors surface at runtime, not startup
- Album art is fetched via httpx at download time, not at fetch time
- Thumbnail (separate JPEG) saved alongside audio only when `download_thumbnail=true` in settings
