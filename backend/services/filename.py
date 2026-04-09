import re
from typing import Optional

AVAILABLE_TOKENS = {
    "title": ("Song title", "Bohemian Rhapsody"),
    "artist": ("Primary artist name", "Queen"),
    "artists": ("All artists, comma-separated", "Queen, David Bowie"),
    "album": ("Album name", "A Night at the Opera"),
    "album_artist": ("Album artist", "Queen"),
    "track_number": ("Track number (zero-padded)", "01"),
    "disc_number": ("Disc number", "1"),
    "year": ("Release year", "1975"),
    "date": ("Full release date", "1975-10-31"),
    "duration": ("Duration in mm:ss", "05:55"),
    "playlist": ("Playlist name", "Classic Rock Hits"),
    "playlist_index": ("Position in playlist (zero-padded)", "003"),
    "source": ("Source platform", "spotify"),
}

TEMPLATE_PRESETS = [
    ("{artist} - {title}", "Simple"),
    ("{track_number}. {title}", "Track listing"),
    ("{artist} - {album} - {track_number} {title}", "Full detail"),
    ("{playlist_index}. {artist} - {title}", "Playlist order"),
    ("{year} - {artist} - {title}", "Year prefix"),
]

ILLEGAL_CHARS = re.compile(r'[/\\:*?"<>|\x00-\x1f]')


def format_duration(ms: int) -> str:
    seconds = ms // 1000
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def apply_template(template: str, track, fallback: str = "Unknown") -> str:
    """Apply filename template to a track, return sanitized filename without extension."""
    replacements = {
        "title": track.title or fallback,
        "artist": track.artist or fallback,
        "artists": (", ".join(track.artists) if track.artists else track.artist) or fallback,
        "album": track.album or fallback,
        "album_artist": (track.album_artist or track.artist) or fallback,
        "track_number": f"{track.track_number:02d}" if track.track_number else "00",
        "disc_number": str(track.disc_number) if track.disc_number else "1",
        "year": track.year or fallback,
        "date": track.date or fallback,
        "duration": format_duration(track.duration_ms) if track.duration_ms else "00:00",
        "playlist": track.playlist_name or fallback,
        "playlist_index": f"{track.playlist_index:03d}" if track.playlist_index else "000",
        "source": track.source.value if track.source else fallback,
    }

    result = template
    for token, value in replacements.items():
        result = result.replace(f"{{{token}}}", str(value))

    return sanitize_filename(result)


def sanitize_filename(filename: str, replacement: str = "_") -> str:
    """Sanitize a filename by removing/replacing illegal characters."""
    filename = ILLEGAL_CHARS.sub(replacement, filename)
    filename = filename.strip(" .")
    filename = re.sub(r'\s+', ' ', filename)
    filename = filename[:200]
    return filename or "track"
