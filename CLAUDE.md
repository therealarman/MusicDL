# Prompt: Build a Music Downloader Web Application

## Project Overview

Build a full-stack web application that allows users to download music from **Spotify** and **YouTube** sources. The app should support downloading individual songs, full playlists, and albums. It must feature a clean, modern UI and a customizable filename template system that auto-fills metadata values for each downloaded track.

**Tech Stack:**
- **Backend:** Python with FastAPI
- **Frontend:** Modern HTML/CSS/JS (React or vanilla JS with a clean component-based structure)
- **Audio Processing:** `yt-dlp` for YouTube audio extraction, `spotdl` or Spotify Web API + `yt-dlp` bridge for Spotify content
- **Metadata:** `mutagen` for reading/writing ID3 tags (artist, title, album, track number, etc.)

---

## Core Features (in priority order)

### 1. Clean, Polished UI

Design a modern, dark-themed single-page application with the following layout and UX:

- **Header** with app name/logo and a source toggle (Spotify / YouTube)
- **Main input area:**
  - A prominent URL input field that accepts:
    - Spotify track, album, or playlist URLs
    - YouTube video or playlist URLs
  - A "Fetch" button that retrieves metadata before downloading
- **Metadata preview panel:**
  - After fetching, display a scrollable list/table of tracks with columns: #, Title, Artist, Album, Duration
  - Each row should have a checkbox for selective downloading
  - "Select All / Deselect All" toggle
- **Filename template bar** (always visible, see Section 3)
- **Download controls:**
  - Audio format selector (MP3, FLAC, WAV, OGG, M4A)
  - Quality/bitrate selector (128kbps, 192kbps, 256kbps, 320kbps — or "Best" for lossless)
  - "Download Selected" and "Download All" buttons
- **Progress area:**
  - Per-track progress bars with status labels (Queued → Downloading → Converting → Done)
  - Overall batch progress bar with ETA
  - Real-time log/console output (collapsible)
- **Download history panel** (collapsible sidebar or bottom drawer):
  - List of previously downloaded tracks in the current session
  - One-click re-download

**UI/UX requirements:**
- Responsive design (works on desktop and tablet)
- Toast notifications for errors, warnings, and completion
- Loading spinners/skeletons while fetching metadata
- Drag-and-drop URL input support (drop a link onto the page)
- Keyboard shortcut: Enter to fetch, Ctrl+Enter to download all
- Color palette: dark background (#0d1117 or similar), accent color inspired by Spotify green (#1DB954) or a user-selectable accent
- Smooth transitions and micro-animations (nothing jarring)
- Accessible: proper ARIA labels, focus states, contrast ratios

---

### 2. Batch Downloading (Playlists & Albums)

Implement robust batch downloading with the following behavior:

- **Spotify playlists/albums:**
  - Use the Spotify Web API to fetch full track metadata (title, artist(s), album name, album art URL, track number, disc number, release date, duration, ISRC)
  - Resolve each track to a YouTube equivalent using search matching (artist + title + duration matching)
  - Download audio from the matched YouTube source via `yt-dlp`
  - Embed full metadata and album art into the downloaded file using `mutagen`

- **YouTube playlists:**
  - Use `yt-dlp` to extract playlist metadata (video titles, durations, uploader)
  - Parse artist/title from video titles using common patterns:
    - `"Artist - Title"`
    - `"Artist — Title"`
    - `"Title by Artist"`
    - `"Artist: Title"`
    - Fall back to full video title as the song title, uploader as artist
  - Download and convert each video's audio

- **Batch behavior:**
  - Configurable concurrent download limit (default: 3 simultaneous downloads)
  - Queue system: tracks are queued and processed in order
  - Retry logic: automatically retry failed downloads up to 2 times with exponential backoff
  - Skip duplicates: if a file with the same resolved filename already exists, prompt or skip
  - Graceful cancellation: user can cancel individual tracks or the entire batch mid-download
  - Final delivery: zip all downloaded files into a single archive for easy download, or offer individual file downloads

---

### 3. Filename Template System

Provide a persistent text input field where the user defines a naming pattern using placeholder tokens enclosed in curly braces. The system should:

- **Default template:** `{artist} - {title}`
- **Available tokens (display these in a help tooltip or dropdown):**

| Token | Description | Example Value |
|-------|-------------|---------------|
| `{title}` | Song title | `Bohemian Rhapsody` |
| `{artist}` | Primary artist name | `Queen` |
| `{artists}` | All artists, comma-separated | `Queen, David Bowie` |
| `{album}` | Album name | `A Night at the Opera` |
| `{album_artist}` | Album artist | `Queen` |
| `{track_number}` | Track number (zero-padded) | `01` |
| `{disc_number}` | Disc number | `1` |
| `{year}` | Release year | `1975` |
| `{date}` | Full release date | `1975-10-31` |
| `{genre}` | Genre | `Rock` |
| `{duration}` | Duration in mm:ss | `05:55` |
| `{playlist}` | Playlist name (if applicable) | `Classic Rock Hits` |
| `{playlist_index}` | Position in playlist (zero-padded) | `003` |
| `{source}` | Source platform | `spotify` or `youtube` |

- **Live preview:** As the user types or modifies the template, show a real-time preview below the input using the first track's metadata as sample data. Example:
  ```
  Template:  {track_number}. {artist} - {title} ({year})
  Preview:   01. Queen - Bohemian Rhapsody (1975)
  ```

- **Filename sanitization:**
  - Strip or replace characters illegal in filenames: `/ \ : * ? " < > |`
  - Replace with underscore or hyphen (user-configurable)
  - Trim leading/trailing whitespace and dots
  - Truncate to a max filename length (255 chars) while preserving the file extension
  - Handle missing metadata gracefully: if a token has no value, replace with `"Unknown"` or allow the user to set a custom fallback string

- **Template presets:**
  - Provide 3–5 built-in presets the user can select from a dropdown:
    - `{artist} - {title}` (Simple)
    - `{track_number}. {title}` (Track listing)
    - `{artist} - {album} - {track_number} {title}` (Full detail)
    - `{playlist_index}. {artist} - {title}` (Playlist order)
  - Allow users to save custom presets (stored in browser localStorage)

---

### 4. Audio Quality Options

- **Format selection:** MP3, FLAC, WAV, OGG, M4A
- **Bitrate selection** (for lossy formats): 128, 192, 256, 320 kbps
- **Post-processing:**
  - Normalize audio levels (optional toggle, using ffmpeg loudnorm filter)
  - Embed album artwork (fetched from Spotify API or YouTube thumbnail)
  - Embed full ID3/Vorbis metadata tags
- **Quality indicator:** Show estimated file size per track based on duration + selected quality

---

## Technical Architecture

### Backend (FastAPI)

```
/api/fetch          POST   - Accept a URL, return track metadata (title, artist, album, etc.)
/api/download       POST   - Start downloading selected tracks with given settings
/api/download/{id}  GET    - Stream/download a completed file
/api/batch/{id}     GET    - Download a zipped batch of files
/api/status/{id}    GET    - SSE (Server-Sent Events) endpoint for real-time progress updates
/api/cancel/{id}    POST   - Cancel an in-progress download or batch
/api/health         GET    - Health check
```

- Use **background tasks** or **Celery/Redis** for download queue management
- Use **Server-Sent Events (SSE)** for real-time progress streaming to the frontend
- Store temporary files in a configurable temp directory with automatic cleanup (delete files older than 1 hour)
- Implement rate limiting to avoid API abuse

### Frontend

- Single-page app (React with Vite, or vanilla JS if preferred — keep it lightweight)
- State management for: current tracks, download queue, progress, settings
- Persistent settings in localStorage (preferred format, quality, filename template)
- EventSource API for SSE progress updates

### File Structure

```
music-downloader/
├── backend/
│   ├── main.py                 # FastAPI app entry point
│   ├── routers/
│   │   ├── fetch.py            # URL parsing and metadata fetching
│   │   ├── download.py         # Download and conversion logic
│   │   └── status.py           # SSE progress endpoints
│   ├── services/
│   │   ├── spotify.py          # Spotify API integration
│   │   ├── youtube.py          # yt-dlp wrapper
│   │   ├── metadata.py         # ID3 tag writing with mutagen
│   │   ├── filename.py         # Template parsing and sanitization
│   │   └── queue.py            # Download queue manager
│   ├── models/
│   │   └── schemas.py          # Pydantic models
│   ├── config.py               # Settings and environment variables
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── src/
│   │   ├── app.js              # Main application logic
│   │   ├── components/         # UI components
│   │   ├── services/           # API client functions
│   │   └── styles/             # CSS / Tailwind
│   └── package.json
├── docker-compose.yml          # Optional: containerized deployment
├── .env.example                # Environment variable template
└── README.md
```

---

## Configuration & Environment

The app should use a `.env` file for configuration:

```env
# Spotify API (required for Spotify features)
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret

# App Settings
DOWNLOAD_DIR=./downloads
TEMP_DIR=./temp
MAX_CONCURRENT_DOWNLOADS=3
FILE_CLEANUP_INTERVAL_MINUTES=60
MAX_PLAYLIST_SIZE=500

# Server
HOST=0.0.0.0
PORT=8000
```

Include clear instructions in the README for:
1. Getting Spotify API credentials (link to Spotify Developer Dashboard)
2. Installing system dependencies (`ffmpeg`, `yt-dlp`)
3. Installing Python and Node.js dependencies
4. Running the app in development and production modes
5. Optional Docker setup

---

## Error Handling

Implement robust error handling for these common scenarios:
- Invalid or unsupported URL format → clear error message with supported URL examples
- Spotify API rate limiting → queue and retry with backoff
- YouTube video unavailable / region-locked / age-restricted → skip with warning, continue batch
- No YouTube match found for a Spotify track → flag in UI, allow manual URL entry for that track
- Network interruption mid-download → retry from where it left off if possible
- Disk space low → warn before starting large batch downloads
- `ffmpeg` or `yt-dlp` not installed → startup check with clear installation instructions

---

## Stretch Goals (implement if time allows)

- **Search integration:** Let users search for songs by name (not just paste URLs)
- **Audio preview:** 30-second preview playback in the browser before downloading
- **Lyrics embedding:** Fetch lyrics from a lyrics API and embed as ID3 lyrics tag
- **Folder structure templates:** e.g., `{artist}/{album}/{track_number}. {title}.mp3`
- **Dark/light theme toggle**
- **Browser extension:** A companion browser extension that adds a "Download with [App Name]" button on Spotify and YouTube pages
- **PWA support:** Make the web app installable as a Progressive Web App
