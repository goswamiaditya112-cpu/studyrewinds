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
from app.models.document import Document
from app.models.video import Video
from app.schemas.subject import (
    SubjectCreateRequest,
    SubjectUpdateRequest,
    SubjectResponse,
    SubjectSummaryResponse,
)

router = APIRouter(prefix="/subjects", tags=["Subjects"])


@router.post("", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED)
def create_subject(
    payload: SubjectCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Creates a new subject owned by the authenticated user.
    Enforces strict ownership: user_id is assigned directly from the verified JWT.
    Rejects duplicate subject names for the same user (case-insensitive).
    """
    existing = db.execute(
        select(Subject).where(
            Subject.user_id == current_user.id,
            func.lower(Subject.name) == payload.name.lower(),
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A subject named '{payload.name}' already exists in your workspace.",
        )

    subject = Subject(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
    )
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return subject


@router.get("", response_model=List[SubjectResponse], status_code=status.HTTP_200_OK)
def list_subjects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lists all subjects owned strictly by the authenticated user.
    Never exposes subjects belonging to another user.
    Results are ordered deterministically by created_at DESC.
    """
    subjects = (
        db.execute(
            select(Subject)
            .where(Subject.user_id == current_user.id)
            .order_by(desc(Subject.created_at))
        )
        .scalars()
        .all()
    )
    return subjects


@router.get("/{subject_id}", response_model=SubjectResponse, status_code=status.HTTP_200_OK)
def get_subject(
    subject_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieves a single subject by ID.
    Enforces IDOR protection: returns 404 Not Found if the subject does not exist
    OR if it belongs to a different user, preventing resource-existence leaks.
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
    return subject


@router.put("/{subject_id}", response_model=SubjectResponse, status_code=status.HTTP_200_OK)
@router.patch("/{subject_id}", response_model=SubjectResponse, status_code=status.HTTP_200_OK)
def update_subject(
    subject_id: uuid.UUID,
    payload: SubjectUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Renames or updates the description of a subject owned by the authenticated user.
    Returns 404 Not Found if subject doesn't exist or belongs to another user.
    Prevents modifying id, user_id, or created_at.
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

    if payload.name is not None:
        duplicate = db.execute(
            select(Subject).where(
                Subject.user_id == current_user.id,
                Subject.id != subject_id,
                func.lower(Subject.name) == payload.name.lower(),
            )
        ).scalar_one_or_none()
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A subject named '{payload.name}' already exists in your workspace.",
            )
        subject.name = payload.name

    if payload.description is not None:
        subject.description = payload.description

    db.commit()
    db.refresh(subject)
    return subject


@router.delete("/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subject(
    subject_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Deletes a subject owned by the authenticated user.
    Returns 404 Not Found if the subject does not exist or belongs to another user.
    Database CASCADE ensures all child resources are cleanly removed.
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

    db.delete(subject)
    db.commit()
    return None


@router.get("/{subject_id}/summary", response_model=SubjectSummaryResponse, status_code=status.HTTP_200_OK)
def get_subject_summary(
    subject_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns counts of playlists, documents/materials, and processed videos for the subject.
    Enforces user ownership: returns 404 Not Found if subject is not owned by current user.
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

    playlist_count = db.execute(
        select(func.count(Playlist.id)).where(Playlist.subject_id == subject_id)
    ).scalar() or 0

    material_count = db.execute(
        select(func.count(Document.id)).where(Document.subject_id == subject_id)
    ).scalar() or 0

    processed_video_count = db.execute(
        select(func.count(Video.id))
        .join(Playlist, Video.playlist_id == Playlist.id)
        .where(
            Playlist.subject_id == subject_id,
            Video.status.in_(["completed", "processed"]),
        )
    ).scalar() or 0

    return SubjectSummaryResponse(
        playlist_count=playlist_count,
        material_count=material_count,
        processed_video_count=processed_video_count,
    )
