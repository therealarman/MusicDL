import io
from pathlib import Path
from typing import Optional


def _to_jpeg(data: bytes) -> bytes:
    """Convert image to a clean JPEG (max 500px). Explorer only displays JPEG art."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert('RGB')
        img.thumbnail((500, 500), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=90)
        return buf.getvalue()
    except Exception:
        return data


def embed_metadata(file_path: str, track, album_art_data: Optional[bytes] = None) -> None:
    """Write ID3/Vorbis/MP4 tags into the audio file."""
    ext = Path(file_path).suffix.lower().lstrip(".")
    handlers = {
        "mp3": _embed_mp3,
        "flac": _embed_flac,
        "m4a": _embed_m4a,
        "ogg": _embed_ogg,
        "wav": _embed_wav,
    }
    handler = handlers.get(ext)
    if handler:
        handler(file_path, track, album_art_data)


def _embed_mp3(file_path: str, track, album_art_data: Optional[bytes]) -> None:
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, APIC, TIT2, TPE1, TPE2, TALB, TRCK, TPOS, TDRC, TCON

    audio = MP3(file_path)
    audio.tags = ID3()
    tags = audio.tags
    tags.add(TIT2(encoding=3, text=track.title or ""))
    tags.add(TPE1(encoding=3, text=track.artist or ""))
    if track.album_artist:
        tags.add(TPE2(encoding=3, text=track.album_artist))
    elif track.artists:
        tags.add(TPE2(encoding=3, text="/".join(track.artists)))
    if track.album:
        tags.add(TALB(encoding=3, text=track.album))
    if track.track_number:
        tags.add(TRCK(encoding=3, text=str(track.track_number)))
    if track.disc_number:
        tags.add(TPOS(encoding=3, text=str(track.disc_number)))
    if track.date or track.year:
        tags.add(TDRC(encoding=3, text=track.date or track.year))
    if track.genre:
        tags.add(TCON(encoding=3, text=track.genre))

    if album_art_data:
        art = _to_jpeg(album_art_data)
        # Windows Explorer requires encoding=0 (Latin-1) and an empty description on
        # the APIC frame. A non-empty desc or encoding=3 (UTF-8) causes Explorer's
        # shell thumbnail extractor to silently ignore the frame.
        tags.add(APIC(
            encoding=0,
            mime="image/jpeg",
            type=3,
            desc="",
            data=art,
        ))

    audio.save(v2_version=3, v1=0)


def _embed_flac(file_path: str, track, album_art_data: Optional[bytes]) -> None:
    from mutagen.flac import FLAC, Picture

    audio = FLAC(file_path)
    if track.title:
        audio["title"] = track.title
    if track.artist:
        audio["artist"] = track.artist
    if track.artists:
        audio["artists"] = track.artists
    if track.album:
        audio["album"] = track.album
    if track.album_artist:
        audio["albumartist"] = track.album_artist
    if track.track_number:
        audio["tracknumber"] = str(track.track_number)
    if track.disc_number:
        audio["discnumber"] = str(track.disc_number)
    if track.date or track.year:
        audio["date"] = track.date or track.year
    if track.genre:
        audio["genre"] = track.genre

    if album_art_data:
        art = _to_jpeg(album_art_data)
        pic = Picture()
        pic.type = 3
        pic.mime = "image/jpeg"
        pic.data = art
        audio.clear_pictures()
        audio.add_picture(pic)

    audio.save()


def _embed_m4a(file_path: str, track, album_art_data: Optional[bytes]) -> None:
    from mutagen.mp4 import MP4, MP4Cover

    audio = MP4(file_path)
    if track.title:
        audio["\xa9nam"] = [track.title]
    if track.artist:
        audio["\xa9ART"] = [track.artist]
    if track.album:
        audio["\xa9alb"] = [track.album]
    if track.album_artist:
        audio["aART"] = [track.album_artist]
    if track.track_number:
        audio["trkn"] = [(track.track_number, 0)]
    if track.disc_number:
        audio["disk"] = [(track.disc_number, 0)]
    if track.date or track.year:
        audio["\xa9day"] = [track.date or track.year]
    if track.genre:
        audio["\xa9gen"] = [track.genre]
    if album_art_data:
        art = _to_jpeg(album_art_data)
        audio["covr"] = [MP4Cover(art, imageformat=MP4Cover.FORMAT_JPEG)]
    audio.save()


def _embed_ogg(file_path: str, track, album_art_data: Optional[bytes]) -> None:
    from mutagen.oggvorbis import OggVorbis

    audio = OggVorbis(file_path)
    if track.title:
        audio["title"] = [track.title]
    if track.artist:
        audio["artist"] = [track.artist]
    if track.album:
        audio["album"] = [track.album]
    if track.album_artist:
        audio["albumartist"] = [track.album_artist]
    if track.track_number:
        audio["tracknumber"] = [str(track.track_number)]
    if track.disc_number:
        audio["discnumber"] = [str(track.disc_number)]
    if track.date or track.year:
        audio["date"] = [track.date or track.year]
    if track.genre:
        audio["genre"] = [track.genre]
    audio.save()


def _embed_wav(file_path: str, track, album_art_data: Optional[bytes]) -> None:
    # WAV uses an ID3 chunk internally; Windows Explorer cannot display WAV album art
    # thumbnails regardless, so we write text tags only.
    from mutagen.wave import WAVE
    from mutagen.id3 import TIT2, TPE1, TPE2, TALB, TRCK, TDRC, TCON

    audio = WAVE(file_path)
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags

    tags.add(TIT2(encoding=3, text=track.title or ""))
    tags.add(TPE1(encoding=3, text=track.artist or ""))
    if track.album_artist:
        tags.add(TPE2(encoding=3, text=track.album_artist))
    elif track.artists:
        tags.add(TPE2(encoding=3, text="/".join(track.artists)))
    if track.album:
        tags.add(TALB(encoding=3, text=track.album))
    if track.track_number:
        tags.add(TRCK(encoding=3, text=str(track.track_number)))
    if track.date or track.year:
        tags.add(TDRC(encoding=3, text=track.date or track.year))
    if track.genre:
        tags.add(TCON(encoding=3, text=track.genre))

    audio.save()
