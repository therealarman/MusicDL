from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid


class SourceType(str, Enum):
    SPOTIFY = "spotify"
    YOUTUBE = "youtube"


class AudioFormat(str, Enum):
    MP3 = "mp3"
    FLAC = "flac"
    WAV = "wav"
    OGG = "ogg"
    M4A = "m4a"


class AudioQuality(str, Enum):
    Q128 = "128"
    Q192 = "192"
    Q256 = "256"
    Q320 = "320"
    BEST = "best"


class TrackStatus(str, Enum):
    QUEUED = "queued"
    SEARCHING = "searching"
    DOWNLOADING = "downloading"
    CONVERTING = "converting"
    EMBEDDING = "embedding"
    DONE = "done"
    ERROR = "error"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


class TrackInfo(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    artist: str = ""
    artists: List[str] = []
    album: str = ""
    album_artist: str = ""
    album_art_url: Optional[str] = None
    track_number: int = 0
    disc_number: int = 1
    year: str = ""
    date: str = ""
    duration_ms: int = 0
    isrc: str = ""
    source: SourceType = SourceType.YOUTUBE
    url: str = ""
    youtube_url: Optional[str] = None
    playlist_name: str = ""
    playlist_index: int = 0


class FetchRequest(BaseModel):
    url: str


class FetchResponse(BaseModel):
    tracks: List[TrackInfo]
    source_type: SourceType
    playlist_name: str = ""
    total_count: int = 0


class DownloadSettings(BaseModel):
    format: AudioFormat = AudioFormat.MP3
    quality: AudioQuality = AudioQuality.Q320
    filename_template: str = "{artist} - {title}"
    normalize_audio: bool = False
    embed_artwork: bool = True
    download_thumbnail: bool = False


class DownloadRequest(BaseModel):
    tracks: List[TrackInfo]
    settings: DownloadSettings


class TrackProgress(BaseModel):
    track_id: str
    status: TrackStatus = TrackStatus.QUEUED
    progress: float = 0.0
    message: str = ""
    file_path: Optional[str] = None
    error: Optional[str] = None


class StartDownloadResponse(BaseModel):
    job_id: str
    total_tracks: int
