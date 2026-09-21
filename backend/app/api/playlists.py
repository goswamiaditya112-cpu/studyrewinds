import logging
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, func

from app.db.session import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.subject import Subject
from app.models.playlist import Playlist
from app.models.video import Video
from app.schemas.playlist import (
    PlaylistCreateRequest,
    PlaylistResponse,
    PlaylistDetailResponse,
    VideoResponse,
)
from app.services.youtube import (
    extract_playlist_id,
    fetch_playlist_metadata,
    PlaylistIngestionError,
)

logger = logging.getLogger("studyrewinds.api.playlists")
router = APIRouter(tags=["Playlists"])


def _to_video_response(video: Video, index: int) -> VideoResponse:
    """Helper to convert a Video ORM object to VideoResponse with derived attributes."""
    return VideoResponse(
        id=video.id,
        playlist_id=video.playlist_id,
        youtube_video_id=video.youtube_video_id,
        title=video.title,
        duration_seconds=video.duration_seconds,
        transcript_source=video.transcript_source,
        status=video.status,
        transcript_status="available" if video.status == "completed" else video.status,  # For frontend UI compatibility
        error_message=video.error_message,
        number=index + 1,
        video_url=f"https://www.youtube.com/watch?v={video.youtube_video_id}",
        created_at=video.created_at,
    )


@router.post("/playlists", response_model=PlaylistResponse, status_code=status.HTTP_201_CREATED)
def create_playlist(
    payload: PlaylistCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ingests a public YouTube playlist into a verified Subject owned by the current user.
    Enforces server-side ownership: current_user must own subject_id.
    Validates the playlist URL, dynamically discovers videos, and stores metadata in PostgreSQL.
    Prevents duplicate playlist submissions under the same subject.
    """
    # 1. Verify Subject ownership
    subject = db.execute(
        select(Subject).where(
            Subject.id == payload.subject_id,
            Subject.user_id == current_user.id,
        )
    ).scalar_one_or_none()

    if not subject:
        logger.warning(
            "User %s attempted to add playlist to unowned or nonexistent subject %s",
            current_user.id,
            payload.subject_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found or access denied.",
        )

    # 2. Extract and validate canonical playlist ID
    try:
        raw_url = payload.playlist_url or payload.url or ""
        canonical_id = extract_playlist_id(raw_url)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # 3. Check for duplicate playlist under the same subject
    existing = db.execute(
        select(Playlist).where(
            Playlist.subject_id == payload.subject_id,
            Playlist.youtube_playlist_id == canonical_id,
        )
    ).scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Playlist '{canonical_id}' has already been added to this subject.",
        )

    # 4. Fetch playlist metadata and discovered videos dynamically
    try:
        metadata = fetch_playlist_metadata(canonical_id)
    except PlaylistIngestionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Failed to ingest playlist %s: %s", canonical_id, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the playlist metadata.",
        )

    # 5. Database transaction boundary: insert Playlist and discovered Videos
    try:
        playlist = Playlist(
            subject_id=subject.id,
            youtube_playlist_id=canonical_id,
            title=metadata["title"],
            status="processing",
        )
        db.add(playlist)
        db.flush()  # Obtain playlist.id

        video_count = 0
        seen_vids = set()
        for video_info in metadata["videos"]:
            vid_id = video_info["youtube_video_id"]
            if vid_id in seen_vids:
                continue
            seen_vids.add(vid_id)

            video_record = Video(
                playlist_id=playlist.id,
                youtube_video_id=vid_id,
                title=video_info["title"],
                duration_seconds=video_info["duration_seconds"],
                transcript_source="none",
                status="pending",
                error_message=None,
            )
            db.add(video_record)
            video_count += 1

        failed_count = metadata.get("failed_video_count", 0)
        if video_count > 0 and failed_count == 0:
            playlist.status = "completed"
        elif video_count > 0 and failed_count > 0:
            playlist.status = "partial_failure"
        else:
            playlist.status = "failed"

        db.commit()
        db.refresh(playlist)
    except Exception as e:
        db.rollback()
        logger.error("Database error committing playlist %s: %s", canonical_id, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist playlist and video records.",
        )

    logger.info(
        "Successfully ingested playlist '%s' (%s) with %d videos for user %s",
        playlist.title,
        playlist.id,
        video_count,
        current_user.id,
    )

    return PlaylistResponse(
        id=playlist.id,
        subject_id=playlist.subject_id,
        youtube_playlist_id=playlist.youtube_playlist_id,
        title=playlist.title,
        status=playlist.status,
        video_count=video_count,
        created_at=playlist.created_at,
    )


@router.get("/playlists", response_model=List[PlaylistResponse], status_code=status.HTTP_200_OK)
def list_user_playlists(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lists all playlists owned by the authenticated user across all their subjects.
    Never returns playlists belonging to other users.
    """
    rows = (
        db.execute(
            select(Playlist, func.count(Video.id).label("video_count"))
            .join(Subject, Playlist.subject_id == Subject.id)
            .outerjoin(Video, Playlist.id == Video.playlist_id)
            .where(Subject.user_id == current_user.id)
            .group_by(Playlist.id)
            .order_by(desc(Playlist.created_at))
        )
        .all()
    )

    return [
        PlaylistResponse(
            id=playlist.id,
            subject_id=playlist.subject_id,
            youtube_playlist_id=playlist.youtube_playlist_id,
            title=playlist.title,
            status=playlist.status,
            video_count=video_count,
            created_at=playlist.created_at,
        )
        for playlist, video_count in rows
    ]


@router.get("/subjects/{subject_id}/playlists", response_model=List[PlaylistResponse], status_code=status.HTTP_200_OK)
def list_subject_playlists(
    subject_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lists all playlists belonging to a specific Subject owned by the authenticated user.
    Returns 404 if the Subject is not found or owned by a different user.
    """
    subject = db.execute(
        select(Subject).where(
            Subject.id == subject_id,
            Subject.user_id == current_user.id,
        )
    ).scalar_one_or_none()

    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found",
        )

    rows = (
        db.execute(
            select(Playlist, func.count(Video.id).label("video_count"))
            .outerjoin(Video, Playlist.id == Video.playlist_id)
            .where(Playlist.subject_id == subject_id)
            .group_by(Playlist.id)
            .order_by(desc(Playlist.created_at))
        )
        .all()
    )

    return [
        PlaylistResponse(
            id=playlist.id,
            subject_id=playlist.subject_id,
            youtube_playlist_id=playlist.youtube_playlist_id,
            title=playlist.title,
            status=playlist.status,
            video_count=video_count,
            created_at=playlist.created_at,
        )
        for playlist, video_count in rows
    ]


@router.get("/playlists/{playlist_id}", response_model=PlaylistDetailResponse, status_code=status.HTTP_200_OK)
def get_playlist_details(
    playlist_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieves full details of a playlist including discovered videos.
    Enforces ownership chain: current_user -> subject -> playlist.
    Returns 404 if not found or belongs to another user (IDOR defense).
    """
    playlist = db.execute(
        select(Playlist)
        .join(Subject, Playlist.subject_id == Subject.id)
        .where(
            Playlist.id == playlist_id,
            Subject.user_id == current_user.id,
        )
    ).scalar_one_or_none()

    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playlist not found",
        )

    videos = (
        db.execute(
            select(Video)
            .where(Video.playlist_id == playlist_id)
            .order_by(Video.created_at.asc())
        )
        .scalars()
        .all()
    )

    video_responses = [_to_video_response(v, i) for i, v in enumerate(videos)]

    return PlaylistDetailResponse(
        id=playlist.id,
        subject_id=playlist.subject_id,
        youtube_playlist_id=playlist.youtube_playlist_id,
        title=playlist.title,
        status=playlist.status,
        video_count=len(video_responses),
        created_at=playlist.created_at,
        videos=video_responses,
    )


@router.get("/playlists/{playlist_id}/videos", response_model=List[VideoResponse], status_code=status.HTTP_200_OK)
def list_playlist_videos(
    playlist_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lists the videos belonging to a playlist owned by the authenticated user.
    Enforces ownership chain: current_user -> subject -> playlist -> videos.
    Returns 404 if not found or belongs to another user (IDOR defense).
    """
    playlist = db.execute(
        select(Playlist)
        .join(Subject, Playlist.subject_id == Subject.id)
        .where(
            Playlist.id == playlist_id,
            Subject.user_id == current_user.id,
        )
    ).scalar_one_or_none()

    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playlist not found",
        )

    videos = (
        db.execute(
            select(Video)
            .where(Video.playlist_id == playlist_id)
            .order_by(Video.created_at.asc())
        )
        .scalars()
        .all()
    )

    return [_to_video_response(v, i) for i, v in enumerate(videos)]


@router.delete("/playlists/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_playlist(
    playlist_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Deletes a playlist owned by the authenticated user.
    Foreign key cascade automatically deletes all associated videos.
    """
    playlist = db.execute(
        select(Playlist)
        .join(Subject, Playlist.subject_id == Subject.id)
        .where(
            Playlist.id == playlist_id,
            Subject.user_id == current_user.id,
        )
    ).scalar_one_or_none()

    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playlist not found",
        )

    db.delete(playlist)
    db.commit()
    return None
