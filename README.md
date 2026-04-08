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

## Requirements

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.10+ | [python.org](https://python.org) |
| ffmpeg | Any recent | Required for audio conversion |
| Git | Any | To clone the repo |

### Install ffmpeg (Windows)

1. Download a Windows build from [ffmpeg.org/download.html](https://ffmpeg.org/download.html)
2. Extract the archive and add the `bin/` folder to your system `PATH`
3. Verify it works: `ffmpeg -version`

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/MusicDownloader.git
cd MusicDownloader
```

### 2. Install Python dependencies

```bash
pip install -r backend/requirements.txt
```

### 3. Configure environment variables

```bash
copy .env.example .env
```

Open `.env` and fill in your settings. Spotify credentials are only required if you want to download from Spotify — YouTube works without them.

#### Getting Spotify API credentials

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) and log in
2. Click **Create App**, give it any name and description
3. Set the Redirect URI to `http://localhost:8000`
4. Open the app settings and copy the **Client ID** and **Client Secret**
5. Paste them into `.env`:
   ```
   SPOTIFY_CLIENT_ID=your_client_id_here
   SPOTIFY_CLIENT_SECRET=your_client_secret_here
   ```

---

## Running the App

Double-click **`start.bat`** in the project root.

- A terminal opens showing the server output
- Your browser opens automatically at `http://127.0.0.1:8000`
- Press **Ctrl+C** in the terminal to stop the server

To start manually instead:

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

---

## Usage

1. Paste a Spotify or YouTube URL into the input field
2. Click **Fetch** (or press Enter)
3. Select the tracks you want
4. Customize the filename template and audio settings
5. Click **Download Selected** or **Download All**
6. Watch real-time progress, then download when complete

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
├── start.bat                Double-click to run
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

**ffmpeg not found** — Make sure `ffmpeg` is in your PATH. Run `ffmpeg -version` to verify.

**Spotify errors** — Check your `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` in `.env`.

**YouTube download fails** — Update yt-dlp: `pip install -U yt-dlp`

**No audio conversion** — ffmpeg must be installed for format conversion beyond the source format.

**Port already in use** — Another process is on port 8000. Either stop it or change `PORT` in `.env`.
