"""
Semantic Search API Router (Phase 9)

Provides dedicated subject-scoped semantic retrieval endpoint.
POST /api/subjects/{subject_id}/search
POST /api/v1/subjects/{subject_id}/search
"""

import uuid
import logging
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.search import SearchRequest, SearchResponse
from app.services.search import search_subject

logger = logging.getLogger("studyrewinds.api.search")
router = APIRouter(tags=["Semantic Search"])


@router.post(
    "/subjects/{subject_id}/search",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Semantic Search within Subject",
    description=(
        "Retrieves semantically relevant YouTube transcript snippets and PDF document chunks "
        "belonging to a specific Subject owned by the authenticated user using pgvector cosine similarity."
    ),
)
def search_subject_endpoint(
    subject_id: uuid.UUID,
    payload: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SearchResponse:
    """
    Authenticated semantic search endpoint:
    1. Authenticates current user via JWT.
    2. Validates subject ownership (returns 404 if unowned).
    3. Generates 384-d normalized query embedding locally via Phase 7 EmbeddingService.
    4. Performs pgvector cosine distance search across transcript and document chunks.
    5. Combines and ranks results by semantic score.
    6. Returns structured provenance metadata.
    """
    return search_subject(
        db=db,
        subject_id=subject_id,
        user_id=current_user.id,
        query=payload.query,
        top_k=payload.top_k,
    )
