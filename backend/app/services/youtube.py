import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional
import yt_dlp

logger = logging.getLogger("studyrewinds.youtube")

# Pattern for valid YouTube playlist IDs (alphanumeric, dashes, underscores)
PLAYLIST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{2,64}$")
YOUTUBE_DOMAINS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


class PlaylistIngestionError(Exception):
    """Raised when playlist discovery or external retrieval fails."""
    pass


class SilentLogger:
    """Silences verbose logging from yt-dlp internal routines."""
    def debug(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        pass

    def error(self, msg: str) -> None:
        pass


def extract_playlist_id(url_or_id: str) -> str:
    """
    Validates and extracts a canonical YouTube playlist ID from an arbitrary URL or raw ID.
    Rejects non-YouTube URLs, empty strings, and video URLs without a playlist ID.
    """
    cleaned = url_or_id.strip()
    if not cleaned:
        raise ValueError("Playlist URL or ID cannot be empty.")

    # Check if the string is already a bare playlist ID
    if PLAYLIST_ID_PATTERN.match(cleaned) and not cleaned.startswith(("http://", "https://")):
        return cleaned

    parsed = urllib.parse.urlparse(cleaned)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Invalid YouTube URL: missing scheme or domain.")

    hostname = parsed.netloc.lower()
    # Normalize port if any
    if ":" in hostname:
        hostname = hostname.split(":")[0]

    if hostname not in YOUTUBE_DOMAINS:
        raise ValueError("URL must belong to a supported YouTube domain.")

    # Parse query parameters
    query_params = urllib.parse.parse_qs(parsed.query)
    playlist_ids = query_params.get("list")

    if not playlist_ids or not playlist_ids[0].strip():
        raise ValueError(
            "YouTube URL does not contain a playlist ID ('list' query parameter is required). "
            "Single-video URLs are not accepted."
        )

    canonical_id = playlist_ids[0].strip()
    if not PLAYLIST_ID_PATTERN.match(canonical_id):
        raise ValueError(f"Extracted playlist ID '{canonical_id}' has an invalid format.")

    return canonical_id


def fetch_playlist_metadata(playlist_id: str, timeout: int = 20) -> Dict[str, Any]:
    """
    Dynamically discovers playlist metadata and video entries using yt-dlp.
    Operates strictly in metadata-only mode ('extract_flat': True).
    Never downloads video or audio files.
    Preserves playlist order and isolates video-level metadata failures.
    """
    logger.info("Discovering metadata for YouTube playlist: %s", playlist_id)
    canonical_url = f"https://www.youtube.com/playlist?list={playlist_id}"

    ydl_opts = {
        "extract_flat": True,
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "logger": SilentLogger(),
        "socket_timeout": timeout,
        "retries": 1,
        "ignoreerrors": True,  # Do not fail entire playlist if one video is unavailable
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(canonical_url, download=False)
    except yt_dlp.utils.DownloadError as e:
        logger.warning("DownloadError while fetching playlist %s: %s", playlist_id, str(e))
        raise PlaylistIngestionError(
            "YouTube playlist is unavailable, private, or not found. "
            "Please ensure the playlist is public and accessible."
        ) from e
    except Exception as e:
        logger.error("Unexpected error fetching playlist %s: %s", playlist_id, str(e))
        raise PlaylistIngestionError(
            f"Failed to retrieve playlist metadata: {str(e)}"
        ) from e

    if not info or "entries" not in info:
        raise PlaylistIngestionError(
            "Playlist information could not be retrieved. Ensure the playlist is public and non-empty."
        )

    playlist_title = (info.get("title") or f"Playlist {playlist_id}").strip()
    # Truncate title if longer than 255
    if len(playlist_title) > 255:
        playlist_title = playlist_title[:252] + "..."

    raw_entries = info.get("entries") or []
    videos: List[Dict[str, Any]] = []
    seen_video_ids = set()
    failed_video_count = 0

    for idx, entry in enumerate(raw_entries):
        if not entry or not isinstance(entry, dict):
            failed_video_count += 1
            continue

        video_id = entry.get("id")
        title = (entry.get("title") or "").strip()

        # Count unavailable, corrupted, deleted, or private videos
        if (
            not video_id
            or not isinstance(video_id, str)
            or not video_id.strip()
            or title in ("[Deleted video]", "[Private video]")
        ):
            failed_video_count += 1
            continue

        video_id = video_id.strip()
        # Duplicate video IDs are deduplicated intentionally and not counted as failures
        if video_id in seen_video_ids:
            continue

        seen_video_ids.add(video_id)

        if not title:
            title = f"Video {idx + 1}"
        elif len(title) > 255:
            title = title[:252] + "..."

        raw_duration = entry.get("duration")
        duration_seconds: Optional[int] = None
        if raw_duration is not None:
            try:
                duration_seconds = max(0, int(raw_duration))
            except (ValueError, TypeError):
                duration_seconds = None

        videos.append({
            "youtube_video_id": video_id,
            "title": title,
            "duration_seconds": duration_seconds,
        })

    logger.info(
        "Successfully discovered %d videos (%d skipped/unavailable) for playlist %s",
        len(videos),
        failed_video_count,
        playlist_id,
    )
    return {
        "youtube_playlist_id": playlist_id,
        "title": playlist_title,
        "videos": videos,
        "failed_video_count": failed_video_count,
    }
