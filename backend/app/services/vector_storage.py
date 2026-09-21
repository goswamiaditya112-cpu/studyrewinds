"""
StudyRewind Vector Storage Service (Phase 8)

Connects the Phase 7 local EmbeddingService (paraphrase-multilingual-MiniLM-L12-v2)
to PostgreSQL + pgvector storage for TranscriptChunk and DocumentChunk records.
Handles single-chunk and batch vector persistence, idempotency, transaction safety,
and provenance preservation without schema changes or database migrations.
"""

import math
import uuid
import logging
from typing import List, Sequence, Union, Optional, NamedTuple
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.chunk import TranscriptChunk, DocumentChunk
from app.services.embedding import (
    EMBEDDING_DIMENSION,
    EmbeddingService,
    get_embedding_service,
    EmbeddingServiceError,
    InvalidInputError,
)

logger = logging.getLogger("studyrewinds.services.vector_storage")


class VectorStorageError(Exception):
    """Base exception for vector storage and persistence failures."""
    pass


class ChunkValidationError(VectorStorageError):
    """Raised when chunk text, metadata, or generated embedding is invalid."""
    pass


class VectorPersistenceError(VectorStorageError):
    """Raised when committing vectors to PostgreSQL fails."""
    pass


class BatchStorageResult(NamedTuple):
    """Encapsulates the result of a batch embedding and persistence operation."""
    total: int
    updated: int
    skipped: int


def is_valid_embedding(embedding: Optional[Sequence[float]]) -> bool:
    """
    Checks whether a chunk already has a non-default, non-zero 384-dimensional embedding.
    The initial un-embedded default in the schema is a vector of all zeros (norm == 0.0).
    Normalized embeddings produced by Phase 7 have an L2 norm approximately equal to 1.0.
    """
    if embedding is None:
        return False
    if len(embedding) != EMBEDDING_DIMENSION:
        return False
    # Check if vector has non-zero magnitude (L2 norm > 0.1)
    norm = sum(x * x for x in embedding)
    return norm > 0.01


def _validate_vector(vector: List[float], chunk_id: Optional[uuid.UUID] = None) -> List[float]:
    """Validates that a generated vector contains exactly 384 finite float values."""
    ctx = f" for chunk {chunk_id}" if chunk_id else ""
    if len(vector) != EMBEDDING_DIMENSION:
        raise ChunkValidationError(
            f"Embedding vector{ctx} has dimension {len(vector)}, expected {EMBEDDING_DIMENSION}."
        )
    for i, val in enumerate(vector):
        if not math.isfinite(val):
            raise ChunkValidationError(
                f"Embedding vector{ctx} contains non-finite value at index {i}: {val}."
            )
    return vector


def store_transcript_chunk_embedding(
    db: Session,
    chunk: TranscriptChunk,
    force: bool = False,
    embedding_service: Optional[EmbeddingService] = None,
) -> TranscriptChunk:
    """
    Generates and stores a 384-dimensional embedding for an existing TranscriptChunk.

    Args:
        db: Active SQLAlchemy database session.
        chunk: The TranscriptChunk model instance to embed.
        force: If False, skips chunks that already have valid embeddings (idempotent).
        embedding_service: Optional EmbeddingService instance (defaults to singleton).

    Returns:
        The refreshed TranscriptChunk instance with updated embedding.
    """
    if not force and is_valid_embedding(chunk.embedding):
        logger.debug("TranscriptChunk %s already has valid embedding; skipping (force=False).", chunk.id)
        return chunk

    if not chunk.text or not chunk.text.strip():
        raise ChunkValidationError(f"TranscriptChunk {chunk.id} has empty or whitespace-only text.")

    service = embedding_service or get_embedding_service()

    try:
        vector = service.embed_text(chunk.text)
    except (InvalidInputError, EmbeddingServiceError) as err:
        raise ChunkValidationError(f"Failed to generate embedding for TranscriptChunk {chunk.id}: {err}") from err

    _validate_vector(vector, chunk_id=chunk.id)

    # Assign embedding preserving all other provenance fields
    chunk.embedding = vector

    try:
        db.commit()
        db.refresh(chunk)
    except Exception as err:
        db.rollback()
        logger.error("Failed to commit embedding for TranscriptChunk %s: %s", chunk.id, err, exc_info=True)
        raise VectorPersistenceError(f"Database error persisting TranscriptChunk {chunk.id} embedding: {err}") from err

    logger.debug("Successfully persisted embedding for TranscriptChunk %s.", chunk.id)
    return chunk


def store_document_chunk_embedding(
    db: Session,
    chunk: DocumentChunk,
    force: bool = False,
    embedding_service: Optional[EmbeddingService] = None,
) -> DocumentChunk:
    """
    Generates and stores a 384-dimensional embedding for an existing DocumentChunk.

    Args:
        db: Active SQLAlchemy database session.
        chunk: The DocumentChunk model instance to embed.
        force: If False, skips chunks that already have valid embeddings (idempotent).
        embedding_service: Optional EmbeddingService instance (defaults to singleton).

    Returns:
        The refreshed DocumentChunk instance with updated embedding.
    """
    if not force and is_valid_embedding(chunk.embedding):
        logger.debug("DocumentChunk %s already has valid embedding; skipping (force=False).", chunk.id)
        return chunk

    if not chunk.text or not chunk.text.strip():
        raise ChunkValidationError(f"DocumentChunk {chunk.id} has empty or whitespace-only text.")

    service = embedding_service or get_embedding_service()

    try:
        vector = service.embed_text(chunk.text)
    except (InvalidInputError, EmbeddingServiceError) as err:
        raise ChunkValidationError(f"Failed to generate embedding for DocumentChunk {chunk.id}: {err}") from err

    _validate_vector(vector, chunk_id=chunk.id)

    # Assign embedding preserving all other provenance fields
    chunk.embedding = vector

    try:
        db.commit()
        db.refresh(chunk)
    except Exception as err:
        db.rollback()
        logger.error("Failed to commit embedding for DocumentChunk %s: %s", chunk.id, err, exc_info=True)
        raise VectorPersistenceError(f"Database error persisting DocumentChunk {chunk.id} embedding: {err}") from err

    logger.debug("Successfully persisted embedding for DocumentChunk %s.", chunk.id)
    return chunk


def store_chunk_embedding(
    db: Session,
    chunk: Union[TranscriptChunk, DocumentChunk],
    force: bool = False,
    embedding_service: Optional[EmbeddingService] = None,
) -> Union[TranscriptChunk, DocumentChunk]:
    """
    Generic dispatcher to store embedding for either a TranscriptChunk or DocumentChunk.
    """
    if isinstance(chunk, TranscriptChunk):
        return store_transcript_chunk_embedding(db, chunk, force=force, embedding_service=embedding_service)
    elif isinstance(chunk, DocumentChunk):
        return store_document_chunk_embedding(db, chunk, force=force, embedding_service=embedding_service)
    else:
        raise ChunkValidationError(f"Unsupported chunk type: {type(chunk).__name__}")


def store_chunks_embeddings_batch(
    db: Session,
    chunks: Sequence[Union[TranscriptChunk, DocumentChunk]],
    batch_size: int = 32,
    force: bool = False,
    embedding_service: Optional[EmbeddingService] = None,
) -> BatchStorageResult:
    """
    Embeds and persists multiple chunks in batches using Phase 7 EmbeddingService.
    Preserves transaction safety (rolls back on failure) and provenance.

    Args:
        db: Active SQLAlchemy database session.
        chunks: Sequence of TranscriptChunk or DocumentChunk records.
        batch_size: Inference batch size (default: 32).
        force: If True, re-embeds chunks even if they already have valid embeddings.
        embedding_service: Optional EmbeddingService instance.

    Returns:
        BatchStorageResult with total, updated, and skipped counts.
    """
    if not chunks:
        return BatchStorageResult(total=0, updated=0, skipped=0)

    # Identify chunks that require embedding
    target_chunks: List[Union[TranscriptChunk, DocumentChunk]] = []
    skipped_count = 0

    for chunk in chunks:
        if not force and is_valid_embedding(chunk.embedding):
            skipped_count += 1
        else:
            if not chunk.text or not chunk.text.strip():
                raise ChunkValidationError(f"Chunk {chunk.id} has empty or whitespace-only text.")
            target_chunks.append(chunk)

    if not target_chunks:
        return BatchStorageResult(total=len(chunks), updated=0, skipped=skipped_count)

    service = embedding_service or get_embedding_service()
    texts = [c.text for c in target_chunks]

    try:
        vectors = service.embed_texts(texts, batch_size=batch_size)
    except (InvalidInputError, EmbeddingServiceError) as err:
        raise ChunkValidationError(f"Failed to generate batch embeddings: {err}") from err

    if len(vectors) != len(target_chunks):
        raise ChunkValidationError(
            f"Embedding service returned {len(vectors)} vectors for {len(target_chunks)} chunks."
        )

    for chunk, vector in zip(target_chunks, vectors):
        _validate_vector(vector, chunk_id=chunk.id)
        chunk.embedding = vector

    try:
        db.commit()
        for chunk in target_chunks:
            db.refresh(chunk)
    except Exception as err:
        db.rollback()
        logger.error("Failed to commit batch embeddings (%d chunks): %s", len(target_chunks), err, exc_info=True)
        raise VectorPersistenceError(f"Database error persisting batch embeddings: {err}") from err

    logger.info("Successfully persisted embeddings for %d chunks (skipped %d).", len(target_chunks), skipped_count)
    return BatchStorageResult(total=len(chunks), updated=len(target_chunks), skipped=skipped_count)


def store_transcript_chunks_for_video(
    db: Session,
    video_id: uuid.UUID,
    batch_size: int = 32,
    force: bool = False,
    embedding_service: Optional[EmbeddingService] = None,
) -> BatchStorageResult:
    """
    Convenience helper: embeds and stores all transcript chunks for a specific Video.
    """
    chunks = (
        db.execute(
            select(TranscriptChunk)
            .where(TranscriptChunk.video_id == video_id)
            .order_by(TranscriptChunk.start_time.asc())
        )
        .scalars()
        .all()
    )
    return store_chunks_embeddings_batch(
        db, chunks, batch_size=batch_size, force=force, embedding_service=embedding_service
    )


def store_document_chunks_for_document(
    db: Session,
    document_id: uuid.UUID,
    batch_size: int = 32,
    force: bool = False,
    embedding_service: Optional[EmbeddingService] = None,
) -> BatchStorageResult:
    """
    Convenience helper: embeds and stores all document chunks for a specific Document.
    """
    chunks = (
        db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.page_number.asc(), DocumentChunk.chunk_index.asc())
        )
        .scalars()
        .all()
    )
    return store_chunks_embeddings_batch(
        db, chunks, batch_size=batch_size, force=force, embedding_service=embedding_service
    )
