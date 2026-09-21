import uuid
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.session import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.subject import Subject
from app.models.playlist import Playlist
from app.models.video import Video
from app.models.chunk import TranscriptChunk
from app.schemas.transcript import (
    TranscriptSegmentResponse,
    VideoTranscriptResponse,
    VideoTranscriptStatusResponse,
    VideoTranscriptProcessingResponse,
    PlaylistTranscriptProcessingResponse,
)
from app.services.transcript import get_or_process_transcript

logger = logging.getLogger("studyrewinds.api.transcripts")
router = APIRouter(tags=["Transcripts"])


def _verify_video_ownership(db: Session, video_id: uuid.UUID, user_id: uuid.UUID) -> Video:
    """
    Enforces strict server-side ownership chain:
    current_user -> Subject -> Playlist -> Video
    Returns the Video if authorized, or raises 404 Not Found (IDOR defense).
    """
    video = db.execute(
        select(Video)
        .join(Playlist, Video.playlist_id == Playlist.id)
        .join(Subject, Playlist.subject_id == Subject.id)
        .where(
            Video.id == video_id,
            Subject.user_id == user_id,
        )
    ).scalar_one_or_none()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found or access denied.",
        )
    return video


def _verify_playlist_ownership(db: Session, playlist_id: uuid.UUID, user_id: uuid.UUID) -> Playlist:
    """
    Enforces strict server-side ownership chain:
    current_user -> Subject -> Playlist
    Returns the Playlist if authorized, or raises 404 Not Found (IDOR defense).
    """
    playlist = db.execute(
        select(Playlist)
        .join(Subject, Playlist.subject_id == Subject.id)
        .where(
            Playlist.id == playlist_id,
            Subject.user_id == user_id,
        )
    ).scalar_one_or_none()

    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playlist not found or access denied.",
        )
    return playlist


@router.post(
    "/videos/{video_id}/transcript/processing",
    response_model=VideoTranscriptProcessingResponse,
    status_code=status.HTTP_200_OK,
)
def process_video_transcript(
    video_id: uuid.UUID,
    force: bool = Query(False, description="Force re-fetching and overwriting existing transcript"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieves and processes the transcript for a single video.
    Attempts YouTube captions first; falls back to local faster-whisper on CPU int8.
    Chunks into 60-90s timestamped segments.
    Enforces ownership chain: current_user -> Subject -> Playlist -> Video.
    Prevents duplicate transcript insertion on repeated calls unless force=True.
    """
    video = _verify_video_ownership(db, video_id, current_user.id)

    updated_video, chunks = get_or_process_transcript(db, video, force=force)

    transcript_status = "available" if updated_video.status == "completed" else "failed"
    processing_status = updated_video.status

    return VideoTranscriptProcessingResponse(
        transcript_status=transcript_status,
        processing_status=processing_status,
        transcript_source=updated_video.transcript_source,
        chunk_count=len(chunks),
        embedding_status="pending",
        processing_error=updated_video.error_message,
        message="Transcript processed successfully." if transcript_status == "available" else updated_video.error_message,
    )


@router.get(
    "/videos/{video_id}/transcript",
    response_model=VideoTranscriptResponse,
    status_code=status.HTTP_200_OK,
)
def get_video_transcript(
    video_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieves stored transcript chunks for a video owned by the authenticated user.
    Returns 404 if not found or belongs to another user.
    """
    video = _verify_video_ownership(db, video_id, current_user.id)

    chunks = db.execute(
        select(TranscriptChunk)
        .where(TranscriptChunk.video_id == video_id)
        .order_by(TranscriptChunk.start_time.asc())
    ).scalars().all()

    segments = [
        TranscriptSegmentResponse(
            segment_index=i,
            text=c.text,
            start_time_seconds=c.start_time,
            end_time_seconds=c.end_time,
            language="hi" if any("\u0900" <= ch <= "\u097f" for ch in c.text) else "en",
        )
        for i, c in enumerate(chunks)
    ]

    return VideoTranscriptResponse(
        video_id=video.id,
        transcript_source=video.transcript_source,
        chunk_count=len(segments),
        data=segments,
    )


@router.get(
    "/videos/{video_id}/transcript/status",
    status_code=status.HTTP_200_OK,
)
def get_video_transcript_status(
    video_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns the current transcript status for a video owned by the authenticated user.
    Returns format expected by frontend: { "data": { transcript_status, processing_status, ... } }
    """
    video = _verify_video_ownership(db, video_id, current_user.id)

    transcript_status = (
        "available" if video.status == "completed"
        else "failed" if video.status == "failed"
        else "processing" if video.status == "processing"
        else "pending"
    )

    return {
        "data": {
            "transcript_status": transcript_status,
            "processing_status": video.status,
            "transcript_source": video.transcript_source,
            "processing_error": video.error_message,
        }
    }


@router.post(
    "/playlists/{playlist_id}/transcripts/processing",
    response_model=PlaylistTranscriptProcessingResponse,
    status_code=status.HTTP_200_OK,
)
def process_playlist_transcripts(
    playlist_id: uuid.UUID,
    force: bool = Query(False, description="Force re-fetching and overwriting existing transcripts"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieves and stores transcripts for all eligible videos in a playlist.
    STRICT FAILURE ISOLATION:
    Each video is processed in an isolated transaction.
    A failure in Video N never stops or rolls back Video N-1 or Video N+1.
    """
    playlist = _verify_playlist_ownership(db, playlist_id, current_user.id)

    videos = db.execute(
        select(Video)
        .where(Video.playlist_id == playlist_id)
        .order_by(Video.created_at.asc())
    ).scalars().all()

    total = len(videos)
    completed = 0
    failed = 0
    skipped = 0

    for video in videos:
        # If not force and already completed, skip processing
        if not force and video.status == "completed":
            completed += 1
            skipped += 1
            continue

        try:
            # Failure-isolated per video
            updated_video, chunks = get_or_process_transcript(db, video, force=force)
            if updated_video.status == "completed":
                completed += 1
            else:
                failed += 1
        except Exception as e:
            logger.error("Error processing transcript for video %s: %s", video.id, e)
            try:
                video.status = "failed"
                video.transcript_source = "none"
                video.error_message = "Unexpected error during transcript acquisition."
                db.commit()
            except Exception:
                db.rollback()
            failed += 1

    msg = f"Transcripts retrieved: {completed} completed, {failed} failed out of {total} videos."
    logger.info("Playlist %s transcript processing finished: %s", playlist_id, msg)

    return PlaylistTranscriptProcessingResponse(
        message=msg,
        total=total,
        completed=completed,
        failed=failed,
        skipped=skipped,
    )
