import os
import re
import uuid
import logging
import tempfile
import shutil
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy import delete as sql_delete

import yt_dlp
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    CouldNotRetrieveTranscript,
    VideoUnavailable,
)
from youtube_transcript_api._errors import IpBlocked, RequestBlocked

from app.models.video import Video
from app.models.chunk import TranscriptChunk

logger = logging.getLogger("studyrewinds.services.transcript")

# Preferred languages for educational transcripts: Hindi first, then English variants
PREFERRED_LANGUAGES = ["hi", "hi-Latn", "en", "en-US", "en-GB", "en-IN"]

# Global cache for the Whisper model to avoid reloading weights repeatedly on CPU
_whisper_model = None
_ffmpeg_warned = False


class _SilentLogger:
    """Silences verbose yt-dlp output during audio acquisition for Whisper fallback."""
    def debug(self, msg: str) -> None:
        pass
    def warning(self, msg: str) -> None:
        pass
    def error(self, msg: str) -> None:
        pass


def _warn_if_ffmpeg_missing() -> bool:
    """
    Checks if FFmpeg is available on PATH. Logs a one-time warning if not.
    Returns True if ffmpeg is available, False otherwise.
    """
    global _ffmpeg_warned
    available = shutil.which("ffmpeg") is not None
    if not available and not _ffmpeg_warned:
        logger.warning(
            "FFmpeg is not installed or not on PATH. Whisper fallback will use DASH m4a audio directly. "
            "Some video formats may fail to open. Install FFmpeg for best compatibility."
        )
        _ffmpeg_warned = True
    return available



def get_whisper_model(model_size: str = "base", device: str = "cpu", compute_type: str = "int8"):
    """
    Lazy loader for local faster-whisper model.
    Loads onto CPU with int8 quantization for laptop-friendly execution.
    cpu_threads is capped at half the available cores to prevent the CPU from
    running at 100% on all cores, which causes severe thermal throttling on laptops.
    Transcription takes ~20% longer but temperature stays manageable.
    """
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        # Use at most half the available cores — prevents 100% CPU peg and thermal throttle.
        # Minimum 2 so transcription is still reasonably fast on dual-core machines.
        cpu_threads = max(2, (os.cpu_count() or 4) // 2)
        logger.info(
            "Initializing faster-whisper model='%s', device='%s', compute_type='%s', cpu_threads=%d",
            model_size, device, compute_type, cpu_threads,
        )
        _whisper_model = WhisperModel(model_size, device=device, compute_type=compute_type, cpu_threads=cpu_threads)
    return _whisper_model


def fetch_youtube_captions(youtube_video_id: str) -> Optional[Tuple[List[Dict], str]]:
    """
    Attempts to retrieve public YouTube captions via youtube-transcript-api.
    Supports Hindi (manual or generated) and English (manual or generated).
    Preserves original language without forced translation.
    Returns:
        (raw_snippets, language_code) if successful, or None if unavailable/failed.
    """
    try:
        api = YouTubeTranscriptApi()
        # 1. Try listing available transcripts to find best match
        transcript_list = api.list(youtube_video_id)

        target_transcript = None
        detected_language = "en"

        # Prioritize Hindi manual, then Hindi auto, then English manual, then English auto
        try:
            # Check for Hindi
            target_transcript = transcript_list.find_transcript(["hi", "hi-Latn"])
            detected_language = target_transcript.language_code
        except Exception:
            try:
                # Check for English
                target_transcript = transcript_list.find_transcript(["en", "en-US", "en-GB", "en-IN"])
                detected_language = target_transcript.language_code
            except Exception:
                # Fallback to whatever transcript is available in the list
                for t in transcript_list:
                    target_transcript = t
                    detected_language = t.language_code
                    break

        if not target_transcript:
            logger.info("No suitable caption track found for video '%s'", youtube_video_id)
            return None

        fetched = target_transcript.fetch()
        raw_snippets = []
        for snippet in fetched:
            text = snippet.text if hasattr(snippet, "text") else snippet.get("text", "")
            start = snippet.start if hasattr(snippet, "start") else snippet.get("start", 0.0)
            duration = snippet.duration if hasattr(snippet, "duration") else snippet.get("duration", 0.0)
            
            clean_text = " ".join(text.split()).strip()
            if clean_text:
                raw_snippets.append({
                    "text": clean_text,
                    "start": float(start),
                    "duration": float(duration),
                })

        if not raw_snippets:
            logger.warning("Captions for video '%s' were empty", youtube_video_id)
            return None

        logger.info("Successfully fetched %d caption snippets for video '%s' (lang='%s')", len(raw_snippets), youtube_video_id, detected_language)
        return raw_snippets, detected_language

    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as e:
        logger.info("Captions unavailable for video '%s': %s", youtube_video_id, e)
        return None
    except (IpBlocked, RequestBlocked) as e:
        logger.info(
            "YouTube is blocking caption requests for video '%s' (IP/request blocked). "
            "Falling back to local Whisper transcription. %s",
            youtube_video_id, type(e).__name__,
        )
        return None
    except CouldNotRetrieveTranscript as e:
        logger.warning("Could not retrieve captions for video '%s': %s", youtube_video_id, e)
        return None
    except Exception as e:
        logger.warning("Unexpected error fetching captions for video '%s': %s", youtube_video_id, e)
        return None


def _parse_vtt_snippets(vtt_path: str) -> Optional[Tuple[List[Dict], str]]:
    """
    Parse a YouTube .vtt subtitle file into raw_snippets compatible with the
    existing chunking pipeline.

    YouTube auto-generated VTT files use a rolling-window format where the same
    text appears in multiple consecutive cues (karaoke-style display). This
    function deduplicates those rolling cues so only one snippet per unique
    (start, end) window is kept.

    Returns (snippets, language_code) or None on failure / empty file.
    """
    try:
        with open(vtt_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        # Detect language from filename: e.g. bkSWJJZNgf8.hi.vtt → "hi"
        lang = "en"
        stem = os.path.splitext(os.path.basename(vtt_path))[0]  # bkSWJJZNgf8.hi
        if "." in stem:
            lang = stem.rsplit(".", 1)[-1]

        def _ts_to_sec(ts: str) -> float:
            ts = ts.replace(",", ".")
            parts = ts.split(":")
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])

        # Parse each cue block (separated by blank lines)
        cues: List[Dict] = []
        for block in re.split(r"\n{2,}", content):
            lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
            if not lines:
                continue

            # Find the --> timestamp line
            ts_idx = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
            if ts_idx is None:
                continue

            ts_match = re.match(
                r"(\d{1,2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[.,]\d{3})",
                lines[ts_idx],
            )
            if not ts_match:
                continue

            start = _ts_to_sec(ts_match.group(1))
            end = _ts_to_sec(ts_match.group(2))

            # Join all text lines after the timestamp line
            raw_text = " ".join(lines[ts_idx + 1:])

            # Strip VTT inline tags: <c>, </c>, <i>, <00:00:01.520>, etc.
            clean = re.sub(r"<[^>]+>", "", raw_text)

            # Decode common HTML entities
            for entity, char in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                                  ("&nbsp;", " "), ("&#39;", "'"), ("&quot;", '"')]:
                clean = clean.replace(entity, char)

            clean = " ".join(clean.split()).strip()
            if clean:
                cues.append({"start": start, "end": end, "text": clean})

        if not cues:
            return None

        # Deduplicate rolling-window cues: for identical (start, end) keep the last
        # (most complete) version, then remove consecutive duplicate texts.
        seen: dict = {}
        for cue in cues:
            key = (round(cue["start"], 2), round(cue["end"], 2))
            seen[key] = cue

        deduped = sorted(seen.values(), key=lambda c: c["start"])

        snippets: List[Dict] = []
        prev_text = ""
        for cue in deduped:
            duration = cue["end"] - cue["start"]
            if duration <= 0 or cue["text"] == prev_text:
                continue
            snippets.append({
                "text": cue["text"],
                "start": cue["start"],
                "duration": duration,
            })
            prev_text = cue["text"]

        return (snippets, lang) if snippets else None

    except Exception as exc:
        logger.warning("VTT parse error for '%s': %s", vtt_path, exc)
        return None


def fetch_subtitles_via_ytdlp(youtube_video_id: str) -> Optional[Tuple[List[Dict], str]]:
    """
    Downloads YouTube auto-generated subtitle text files via yt-dlp.

    This is the fastest transcript source (3-5 seconds, ~3% CPU) and works even
    when youtube-transcript-api is IP-blocked, because yt-dlp mimics a real browser.

    Only the subtitle text file (~30-100 KB) is downloaded — no audio, no video.
    The temporary directory is deleted immediately after parsing.

    Returns (raw_snippets, language_code) or None if subtitles are unavailable.
    """
    temp_dir = tempfile.mkdtemp(prefix="sr_sub_")
    try:
        ydl_opts = {
            "writeautomaticsub": True,   # auto-generated captions (most common)
            "writesubtitles": True,       # manual captions too, if available
            "subtitleslangs": ["hi", "hi-IN", "en", "en-IN"],
            "subtitlesformat": "vtt",
            "skip_download": True,        # subtitle text file ONLY — no audio/video
            "outtmpl": os.path.join(temp_dir, "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "logger": _SilentLogger(),
            "noplaylist": True,
        }

        video_url = f"https://www.youtube.com/watch?v={youtube_video_id}"
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        # Find downloaded .vtt files — prefer Hindi
        vtt_files = sorted(
            [f for f in os.listdir(temp_dir) if f.endswith(".vtt")]
        )
        if not vtt_files:
            logger.info(
                "yt-dlp found no subtitle files for video '%s' (auto-captions may be disabled)",
                youtube_video_id,
            )
            return None

        # Prefer Hindi subtitle file over English
        target = None
        for lang_pref in ["hi", "hi-IN", "en-IN", "en"]:
            target = next((f for f in vtt_files if f".{lang_pref}." in f), None)
            if target:
                break
        if not target:
            target = vtt_files[0]

        vtt_path = os.path.join(temp_dir, target)
        file_size = os.path.getsize(vtt_path)
        logger.info(
            "Parsing subtitle file '%s' (%d bytes) for video '%s'",
            target, file_size, youtube_video_id,
        )

        result = _parse_vtt_snippets(vtt_path)
        if result:
            snippets, lang = result
            if snippets:
                logger.info(
                    "yt-dlp subtitles: %d snippets (lang='%s') for video '%s'",
                    len(snippets), lang, youtube_video_id,
                )
                return snippets, lang

        logger.info(
            "Subtitle file for video '%s' was empty or unparseable; will fall back to Whisper",
            youtube_video_id,
        )
        return None

    except Exception as exc:
        logger.warning(
            "yt-dlp subtitle download failed for video '%s': %s", youtube_video_id, exc
        )
        return None

    finally:
        # Clean up temp subtitle directory immediately — files are tiny but we still tidy up
        import stat as _stat

        def _force_remove(func, path, _exc_info):
            try:
                os.chmod(path, _stat.S_IWRITE)
                func(path)
            except Exception:
                pass

        shutil.rmtree(temp_dir, onerror=_force_remove)


def transcribe_with_whisper(youtube_video_id: str) -> Optional[Tuple[List[Dict], str]]:
    """

    Local fallback using faster-whisper when YouTube captions are unavailable.
    Downloads temporary audio via yt-dlp, transcribes locally with CPU int8,
    and guarantees immediate cleanup of all temporary media files.

    Format selection strategy:
    - Strongly prefers m4a (MPEG-4 audio) since ctranslate2/faster-whisper reads DASH m4a natively.
    - Avoids webm/opus as a primary format when FFmpeg is absent, since those containers
      often require ffmpeg for remuxing before ctranslate2 can open them.
    - Falls back to 'bestaudio/best' if m4a is unavailable.
    """
    _warn_if_ffmpeg_missing()
    temp_dir = tempfile.mkdtemp(prefix="sr_whisper_")
    try:
        audio_template = os.path.join(temp_dir, "%(id)s.%(ext)s")
        ydl_opts = {
            # Prefer m4a (AAC/MPEG-4): natively readable by ctranslate2 without FFmpeg.
            # Fallback: bestaudio[acodec=mp4a] then generic bestaudio, avoiding webm/opus primary.
            "format": "bestaudio[ext=m4a]/bestaudio[acodec=mp4a]/bestaudio/best",
            "outtmpl": audio_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "logger": _SilentLogger(),
            # No extractor_args override: yt-dlp's default web client finds 47 formats
            # including 12 audio-only streams. Overriding player_client to include
            # "tv_embedded" or "mweb" triggers YouTube SABR-only streaming / PO token
            # requirements on some networks, leaving zero audio formats available.
        }


        logger.info("Downloading temporary audio for video '%s' for Whisper fallback", youtube_video_id)
        video_url = f"https://www.youtube.com/watch?v={youtube_video_id}"
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        downloaded_files = os.listdir(temp_dir)
        if not downloaded_files:
            logger.error("yt-dlp completed without producing an audio file for '%s'", youtube_video_id)
            return None

        audio_path = os.path.join(temp_dir, downloaded_files[0])
        file_size = os.path.getsize(audio_path)
        logger.info("Running faster-whisper on '%s' (%d bytes)", audio_path, file_size)

        if file_size < 1024:
            logger.error("Downloaded audio file for video '%s' is suspiciously small (%d bytes); aborting Whisper", youtube_video_id, file_size)
            return None

        model = get_whisper_model(model_size="base", device="cpu", compute_type="int8")

        try:
            # beam_size=2: lower CPU load than beam_size=5 (2-3x less compute per segment).
            # Quality difference is negligible for clear educational speech.
            segments_gen, info = model.transcribe(audio_path, beam_size=2)
        except Exception as transcribe_err:
            logger.error(
                "faster-whisper failed to open/transcribe audio for video '%s' "
                "(file: '%s', ext: '%s'). Error: %s. "
                "Install FFmpeg for broader audio format support.",
                youtube_video_id,
                os.path.basename(audio_path),
                os.path.splitext(audio_path)[1],
                transcribe_err,
            )
            return None

        raw_snippets = []
        for segment in segments_gen:
            clean_text = " ".join(segment.text.split()).strip()
            if clean_text:
                raw_snippets.append({
                    "text": clean_text,
                    "start": float(segment.start),
                    "duration": float(segment.end - segment.start),
                })

        detected_lang = getattr(info, "language", "en")
        logger.info("Whisper transcribed %d segments for video '%s' (detected lang='%s')", len(raw_snippets), youtube_video_id, detected_lang)
        return raw_snippets, detected_lang

    except Exception as e:
        logger.error("Whisper transcription failed for video '%s': %s", youtube_video_id, e)
        return None
    finally:
        # STRICT CLEANUP: Remove temporary audio directory with bounded retry.
        # On Windows, yt-dlp may hold the downloaded audio file open briefly after
        # the YoutubeDL context exits, causing PermissionError on the first rmtree
        # attempt. We retry up to 3 times with a 0.5s delay between attempts.
        import time as _time
        import stat as _stat

        def _force_remove_readonly(func, path, _exc_info):
            """onerror handler: clear read-only bit then retry the removal."""
            try:
                os.chmod(path, _stat.S_IWRITE)
                func(path)
            except Exception:
                pass

        _cleaned = False
        for _attempt in range(3):
            try:
                shutil.rmtree(temp_dir, onerror=_force_remove_readonly)
                logger.debug(
                    "Cleaned up temporary audio directory '%s' (attempt %d)",
                    temp_dir, _attempt + 1,
                )
                _cleaned = True
                break
            except OSError:
                if _attempt < 2:
                    _time.sleep(0.5)
        if not _cleaned:
            logger.warning(
                "Could not remove temporary audio directory '%s' after 3 attempts. "
                "Manual cleanup of %s may be required.",
                temp_dir, temp_dir,
            )



# Punctuation markers indicating sentence boundaries across English, Hindi, and Hinglish
SENTENCE_ENDINGS = (".", "!", "?", "।", "॥")


def chunk_transcript(
    raw_snippets: List[Dict],
    min_duration: float = 60.0,
    max_duration: float = 90.0,
) -> List[Dict]:
    """
    Chunks raw timestamped snippets into contiguous 60–90 second windows.
    Preserves exact start_time and end_time, chronological ordering, and sentence boundaries.
    Returns:
        List of dicts: [{'start_time': float, 'end_time': float, 'text': str}]
    """
    if not raw_snippets:
        return []

    # Sort chronologically by start timestamp
    sorted_snippets = sorted(raw_snippets, key=lambda s: s["start"])

    chunks: List[Dict] = []
    current_texts: List[str] = []
    chunk_start: Optional[float] = None
    chunk_end: Optional[float] = None

    for snippet in sorted_snippets:
        text = snippet["text"].strip()
        if not text:
            continue

        s_start = snippet["start"]
        s_duration = snippet.get("duration", 0.0)
        s_end = s_start + max(s_duration, 0.5)

        if chunk_start is None:
            chunk_start = s_start
            chunk_end = s_end
            current_texts.append(text)
            continue

        current_duration = s_end - chunk_start
        current_texts.append(text)
        chunk_end = s_end

        # Check if we should close the chunk:
        # 1. We reached or exceeded min_duration AND current snippet ends at a sentence boundary
        # 2. OR we reached/exceeded max_duration
        ends_with_punctuation = any(text.endswith(p) for p in SENTENCE_ENDINGS)

        if (current_duration >= min_duration and ends_with_punctuation) or (current_duration >= max_duration):
            joined_text = " ".join(current_texts).strip()
            if joined_text:
                chunks.append({
                    "start_time": round(chunk_start, 2),
                    "end_time": round(max(chunk_end, chunk_start + 1.0), 2),
                    "text": joined_text,
                })
            current_texts = []
            chunk_start = None
            chunk_end = None

    # Flush any remaining accumulated text as the final chunk
    if current_texts and chunk_start is not None and chunk_end is not None:
        joined_text = " ".join(current_texts).strip()
        if joined_text:
            chunks.append({
                "start_time": round(chunk_start, 2),
                "end_time": round(max(chunk_end, chunk_start + 1.0), 2),
                "text": joined_text,
            })

    return chunks


def get_or_process_transcript(
    db: Session,
    video: Video,
    force: bool = False,
) -> Tuple[Video, List[TranscriptChunk]]:
    """
    Acquires and stores transcript for a single video.
    Behavior:
    1. If transcript already completed and force=False: returns existing chunks (prevents duplicate insertion).
    2. If force=True or not completed:
       - Tries YouTube captions first.
       - Falls back to faster-whisper if captions unavailable.
       - Chunks into 60-90s windows preserving timestamps.
       - Replaces existing chunks if force=True.
       - Updates Video status, transcript_source, and error_message.
       - Commits to PostgreSQL.
    """
    # 1. Check for existing completed transcript to prevent duplicate insertion
    if not force and video.status == "completed":
        existing_chunks = db.execute(
            select(TranscriptChunk)
            .where(TranscriptChunk.video_id == video.id)
            .order_by(TranscriptChunk.start_time.asc())
        ).scalars().all()

        if existing_chunks:
            logger.info("Video '%s' already has %d transcript chunks stored; returning existing.", video.id, len(existing_chunks))
            return video, list(existing_chunks)

    # 2. Mark processing
    video.status = "processing"
    db.commit()
    db.refresh(video)

    raw_snippets = None
    source = "none"
    detected_lang = "en"

    # 3. Attempt YouTube captions first (fast ~2s, but IP-blocked on many networks)
    caption_result = fetch_youtube_captions(video.youtube_video_id)
    if caption_result:
        raw_snippets, detected_lang = caption_result
        source = "caption"
        logger.info("Acquired captions for video '%s' (lang='%s')", video.youtube_video_id, detected_lang)
    else:
        # 4. yt-dlp subtitle download — fast middle path (3-5s, ~3% CPU)
        # Downloads only the subtitle text file, not audio. Works even when
        # youtube-transcript-api is IP-blocked because yt-dlp mimics a real browser.
        logger.info("Captions unavailable for '%s'; trying yt-dlp subtitle download", video.youtube_video_id)
        subtitle_result = fetch_subtitles_via_ytdlp(video.youtube_video_id)
        if subtitle_result:
            raw_snippets, detected_lang = subtitle_result
            source = "subtitle"
            logger.info("Acquired subtitles via yt-dlp for video '%s' (lang='%s')", video.youtube_video_id, detected_lang)
        else:
            # 5. Last resort: local faster-whisper (slow ~1-2 min, high CPU)
            logger.info("Subtitles unavailable for '%s'; falling back to faster-whisper", video.youtube_video_id)
            whisper_result = transcribe_with_whisper(video.youtube_video_id)
            if whisper_result:
                raw_snippets, detected_lang = whisper_result
                source = "whisper"
                logger.info("Acquired Whisper transcript for video '%s' (lang='%s')", video.youtube_video_id, detected_lang)

    # 5. Handle total failure
    if not raw_snippets:
        video.transcript_source = "none"
        video.status = "failed"
        video.error_message = "All transcript methods failed: captions blocked, yt-dlp subtitles unavailable, Whisper fallback failed."
        db.commit()
        db.refresh(video)
        return video, []

    # 6. Chunk snippets into 60-90 second windows
    chunk_data = chunk_transcript(raw_snippets, min_duration=60.0, max_duration=90.0)
    if not chunk_data:
        video.transcript_source = "none"
        video.status = "failed"
        video.error_message = "Transcript contained no usable text chunks."
        db.commit()
        db.refresh(video)
        return video, []

    # 7. Safe replacement: delete any existing chunks via direct SQL DELETE.
    # Using sql_delete() instead of ORM relationship iteration avoids stale
    # session cache issues where video.transcript_chunks may return an empty list
    # despite rows existing in the database after a prior commit + refresh cycle.
    db.execute(sql_delete(TranscriptChunk).where(TranscriptChunk.video_id == video.id))
    db.flush()


    # 8. Insert new chunks
    new_chunks = [
        TranscriptChunk(
            video_id=video.id,
            start_time=c["start_time"],
            end_time=c["end_time"],
            text=c["text"],
            embedding=[0.0] * 384,  # Phase 1 schema zero-vector placeholder until Phase 6
        )
        for c in chunk_data
    ]
    db.add_all(new_chunks)

    # 9. Update Video attributes
    video.transcript_source = source
    video.status = "completed"
    video.error_message = None
    db.commit()
    db.refresh(video)

    # 10. Generate and persist vector embeddings for semantic search (Phase 8 integration)
    try:
        from app.services.vector_storage import store_chunks_embeddings_batch
        store_chunks_embeddings_batch(db, new_chunks, force=True)
        logger.info("Generated and stored vector embeddings for %d transcript chunks (video '%s')", len(new_chunks), video.id)
    except Exception as emb_err:
        logger.error("Failed to generate embeddings for transcript chunks of video %s: %s", video.id, emb_err, exc_info=True)

    logger.info("Stored %d transcript chunks for video '%s' (source='%s')", len(new_chunks), video.id, source)
    return video, new_chunks
