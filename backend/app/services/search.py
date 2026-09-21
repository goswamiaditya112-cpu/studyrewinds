"""
StudyRewind Semantic Search Service (Phase 9)

Implements backend semantic search across YouTube transcripts and PDF documents.
Uses Phase 7 local EmbeddingService for query embedding and PostgreSQL pgvector
for cosine distance similarity search.
Enforces strict subject ownership isolation at the database query level.
"""

import math
import uuid
import logging
from typing import List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.subject import Subject
from app.models.playlist import Playlist
from app.models.video import Video
from app.models.document import Document
from app.models.chunk import TranscriptChunk, DocumentChunk
from app.services.embedding import embed_text
from app.schemas.search import (
    SearchResponse,
    SearchResultItem,
    YouTubeSearchResult,
    YouTubeVideoInfo,
    YouTubeTranscriptInfo,
    PDFSearchResult,
    PDFDocumentInfo,
)

logger = logging.getLogger("studyrewinds.services.search")


def search_subject(
    db: Session,
    subject_id: uuid.UUID,
    user_id: uuid.UUID,
    query: str,
    top_k: int = 5,
) -> SearchResponse:
    """
    Performs semantic retrieval across YouTube transcripts and PDF chunks
    belonging to a specific Subject owned by the authenticated user.

    Args:
        db: Active SQLAlchemy database session.
        subject_id: UUID of the target Subject.
        user_id: UUID of the authenticated user.
        query: User search string (validated non-empty).
        top_k: Maximum number of ranked results to return (1-50).

    Returns:
        SearchResponse with ranked results preserving complete source provenance.

    Raises:
        HTTPException 404: If the subject is not found or owned by another user.
        HTTPException 500: If vector embedding or database query fails.
    """
    # 1. Verify subject ownership in database
    subject = db.execute(
        select(Subject).where(
            Subject.id == subject_id,
            Subject.user_id == user_id,
        )
    ).scalar_one_or_none()

    if not subject:
        logger.warning("User %s attempted to search unowned or nonexistent subject %s", user_id, subject_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found or access denied.",
        )

    # 2. Generate normalized 384-d query embedding locally using Phase 7 service
    try:
        query_vector = embed_text(query)
    except Exception as err:
        logger.error("Failed to generate query embedding: %s", err, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate query embedding: {str(err)}",
        )

    # 2b. Ensure all chunks for this subject have valid embeddings (self-healing for un-embedded chunks)
    try:
        from app.services.vector_storage import is_valid_embedding, store_chunks_embeddings_batch

        unembedded_transcripts = (
            db.execute(
                select(TranscriptChunk)
                .join(Video, TranscriptChunk.video_id == Video.id)
                .join(Playlist, Video.playlist_id == Playlist.id)
                .where(Playlist.subject_id == subject_id)
            )
            .scalars()
            .all()
        )
        t_to_embed = [c for c in unembedded_transcripts if not is_valid_embedding(c.embedding)]
        if t_to_embed:
            logger.info("Embedding %d un-embedded transcript chunks for subject %s", len(t_to_embed), subject_id)
            store_chunks_embeddings_batch(db, t_to_embed, force=True)

        unembedded_docs = (
            db.execute(
                select(DocumentChunk)
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(Document.subject_id == subject_id)
            )
            .scalars()
            .all()
        )
        d_to_embed = [c for c in unembedded_docs if not is_valid_embedding(c.embedding)]
        if d_to_embed:
            logger.info("Embedding %d un-embedded document chunks for subject %s", len(d_to_embed), subject_id)
            store_chunks_embeddings_batch(db, d_to_embed, force=True)

    except Exception as err:
        logger.warning("Auto-embedding unpopulated chunks for subject %s encountered non-critical error: %s", subject_id, err)

    candidates: List[SearchResultItem] = []

    # 3. Search YouTube Transcript Chunks via PostgreSQL pgvector cosine distance
    try:
        transcript_dist = TranscriptChunk.embedding.cosine_distance(query_vector).label("distance")
        transcript_stmt = (
            select(TranscriptChunk, Video, transcript_dist)
            .join(Video, TranscriptChunk.video_id == Video.id)
            .join(Playlist, Video.playlist_id == Playlist.id)
            .where(
                Playlist.subject_id == subject_id,
                TranscriptChunk.embedding.isnot(None),
            )
            .order_by(transcript_dist.asc())
            .limit(top_k)
        )
        transcript_rows = db.execute(transcript_stmt).all()

        for chunk, video, dist in transcript_rows:
            if dist is None or math.isnan(dist):
                continue
            # Cosine similarity score = 1.0 - cosine_distance
            score = round(max(0.0, 1.0 - float(dist)), 4)
            candidates.append(
                YouTubeSearchResult(
                    score=score,
                    chunk_id=chunk.id,
                    video=YouTubeVideoInfo(
                        id=video.id,
                        youtube_video_id=video.youtube_video_id,
                        title=video.title,
                    ),
                    transcript=YouTubeTranscriptInfo(
                        text=chunk.text,
                        start_time=chunk.start_time,
                        end_time=chunk.end_time,
                    ),
                )
            )

        # 4. Search PDF Document Chunks via PostgreSQL pgvector cosine distance
        doc_dist = DocumentChunk.embedding.cosine_distance(query_vector).label("distance")
        doc_stmt = (
            select(DocumentChunk, Document, doc_dist)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(
                Document.subject_id == subject_id,
                DocumentChunk.embedding.isnot(None),
            )
            .order_by(doc_dist.asc())
            .limit(top_k)
        )
        doc_rows = db.execute(doc_stmt).all()

        for chunk, document, dist in doc_rows:
            if dist is None or math.isnan(dist):
                continue
            score = round(max(0.0, 1.0 - float(dist)), 4)
            candidates.append(
                PDFSearchResult(
                    score=score,
                    chunk_id=chunk.id,
                    document=PDFDocumentInfo(
                        id=document.id,
                        filename=document.filename,
                    ),
                    page_number=chunk.page_number,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                )
            )

    except HTTPException:
        raise
    except Exception as err:
        logger.error("Database vector search failed for subject %s: %s", subject_id, err, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database vector search failed: {str(err)}",
        )

    # 5. Rank combined results by semantic relevance (highest score first)
    # Deterministic tie-breaker: chunk_id ascending
    candidates.sort(key=lambda item: (-item.score, str(item.chunk_id)))
    final_results = candidates[:top_k]

    return SearchResponse(
        query=query,
        subject_id=subject_id,
        total_results=len(final_results),
        results=final_results,
    )
