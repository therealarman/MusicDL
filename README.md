# MusicDL — Music Downloader

A full-stack web application to download music from **Spotify** and **YouTube**.
Supports individual tracks, full playlists, and albums with metadata embedding and custom filename templates.

---

## Features

- Download from Spotify (tracks, albums, playlists) or YouTube (videos, playlists)
- Audio formats: MP3, FLAC, WAV, OGG, M4A
- Bitrate selection: 128 / 192 / 256 / 320 kbps or Best
- Customizable filename templates with live preview (`{artist} - {title}`, etc.)
- Full metadata embedding (ID3 tags, album art)
- Real-time progress via Server-Sent Events
- Batch download with ZIP archive
- Download history panel
- Drag & drop URL input
- Dark themed, responsive UI

---

## Prerequisites

| Tool | Install |
|------|---------|
| Python 3.10+ | https://python.org |
| ffmpeg | https://ffmpeg.org/download.html |
| yt-dlp | Installed via pip (see below) |

### Install ffmpeg (Windows)

1. Download from https://ffmpeg.org/download.html → Windows builds
2. Extract and add the `bin/` folder to your `PATH`
3. Verify: `ffmpeg -version`

---

## Setup

### 1. Clone / copy the project

```
cd MusicDownloader
```

### 2. Install Python dependencies

```bash
cd backend
pip install -r requirements.txt
cd ..
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your Spotify API credentials (optional — only needed for Spotify)
```

#### Getting Spotify API credentials

1. Go to https://developer.spotify.com/dashboard
2. Log in and click **Create App**
3. Set the redirect URI to `http://localhost:8000` (or anything)
4. Copy the **Client ID** and **Client Secret** into `.env`

### 4. Run the server

```bash
python -m backend.main
```

Or using uvicorn directly:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser at **http://localhost:8000**

---

## Usage

1. Paste a Spotify or YouTube URL into the input field
2. Click **Fetch** (or press Enter)
3. Select the tracks you want
4. Customize the filename template and audio settings
5. Click **Download Selected** or **Download All**
6. Watch real-time progress and download when complete

---

## Filename Template Tokens

| Token | Example |
|-------|---------|
| `{title}` | Bohemian Rhapsody |
| `{artist}` | Queen |
| `{album}` | A Night at the Opera |
| `{track_number}` | 01 |
| `{year}` | 1975 |
| `{genre}` | Rock |
| `{playlist_index}` | 003 |
| `{source}` | spotify |

---

## Project Structure

```
MusicDownloader/
├── backend/
│   ├── main.py              FastAPI entry point
│   ├── config.py            Settings from .env
│   ├── models/schemas.py    Pydantic models
│   ├── routers/
│   │   ├── fetch.py         URL metadata fetching
│   │   ├── download.py      Download + file serving
│   │   └── status.py        SSE progress stream
│   ├── services/
│   │   ├── spotify.py       Spotify API wrapper
│   │   ├── youtube.py       yt-dlp wrapper
│   │   ├── metadata.py      ID3 tag writing (mutagen)
│   │   ├── filename.py      Template system
│   │   └── queue.py         Download queue manager
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   └── src/
│       ├── app.js           Single-page app (vanilla JS)
│       └── styles/main.css  Dark theme CSS
├── .env                     Your config (not committed)
├── .env.example             Config template
└── README.md
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/fetch` | Fetch track metadata from a URL |
| POST | `/api/download` | Start a download job |
| GET | `/api/status/{id}` | SSE stream of job progress |
| GET | `/api/download/{job}/{track}` | Download a single file |
| GET | `/api/batch/{id}` | Download all files as ZIP |
| POST | `/api/cancel/{id}` | Cancel an active job |
| GET | `/api/health` | Health check |
| GET | `/api/tokens` | Available filename template tokens |

---

## Troubleshooting

**ffmpeg not found**: Make sure `ffmpeg` is in your PATH. Run `ffmpeg -version` to verify.

**Spotify errors**: Check your `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` in `.env`.

**YouTube download fails**: Update yt-dlp: `pip install -U yt-dlp`

**No audio conversion**: ffmpeg must be installed for format conversion beyond the source format.
