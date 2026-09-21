"""
Phase 8 - Vector Storage Tests
Tests storing and retrieving 384-dimensional embeddings in PostgreSQL + pgvector
for TranscriptChunk and DocumentChunk models.
Verifies provenance preservation, batching, idempotency, transaction safety,
and reuse of Phase 7 local EmbeddingService.
"""

import math
import uuid
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.subject import Subject
from app.models.playlist import Playlist
from app.models.video import Video
from app.models.document import Document
from app.models.chunk import TranscriptChunk, DocumentChunk
from app.services.vector_storage import (
    store_transcript_chunk_embedding,
    store_document_chunk_embedding,
    store_chunk_embedding,
    store_chunks_embeddings_batch,
    store_transcript_chunks_for_video,
    store_document_chunks_for_document,
    is_valid_embedding,
    ChunkValidationError,
    VectorPersistenceError,
    BatchStorageResult,
)


def create_test_hierarchy(db: Session):
    """Helper to create a minimal user -> subject -> playlist -> video -> doc hierarchy."""
    user = User(email=f"user_{uuid.uuid4().hex[:8]}@example.com", hashed_password="hashed_pw_test")
    db.add(user)
    db.flush()

    subject = Subject(user_id=user.id, name="Computer Architecture")
    db.add(subject)
    db.flush()

    playlist = Playlist(subject_id=subject.id, youtube_playlist_id="PL_ARCH", title="Arch 101")
    db.add(playlist)
    db.flush()

    video = Video(playlist_id=playlist.id, youtube_video_id="v_arch_1", title="Pipeline Hazards")
    db.add(video)
    db.flush()

    doc = Document(
        subject_id=subject.id,
        filename="lecture_notes.pdf",
        file_path="/dummy/path.pdf",
        page_count=5,
        status="completed",
    )
    db.add(doc)
    db.flush()

    return user, subject, playlist, video, doc


def test_transcript_chunk_embedding_storage_and_retrieval(db_session: Session):
    """Verifies that an embedding is generated and stored for a TranscriptChunk, then retrieved."""
    _, _, _, video, _ = create_test_hierarchy(db_session)

    chunk = TranscriptChunk(
        video_id=video.id,
        start_time=12.5,
        end_time=25.0,
        text="Instruction pipelining introduces data hazards when operands are unavailable.",
    )
    db_session.add(chunk)
    db_session.commit()
    db_session.refresh(chunk)

    # Initial state: default zero vector
    assert not is_valid_embedding(chunk.embedding)

    # Store embedding using Phase 8 service
    updated_chunk = store_transcript_chunk_embedding(db_session, chunk)
    chunk_id = updated_chunk.id

    # Retrieve freshly from database
    retrieved = db_session.get(TranscriptChunk, chunk_id)
    assert retrieved is not None
    assert is_valid_embedding(retrieved.embedding)
    assert len(retrieved.embedding) == 384
    assert all(isinstance(v, float) for v in retrieved.embedding)
    assert all(math.isfinite(v) for v in retrieved.embedding)

    # Normalized unit vector check
    norm = sum(v * v for v in retrieved.embedding)
    assert math.isclose(norm, 1.0, rel_tol=1e-3)

    # Provenance preservation check
    assert retrieved.video_id == video.id
    assert retrieved.start_time == 12.5
    assert retrieved.end_time == 25.0
    assert retrieved.text == "Instruction pipelining introduces data hazards when operands are unavailable."


def test_document_chunk_embedding_storage_and_retrieval(db_session: Session):
    """Verifies that an embedding is generated and stored for a DocumentChunk, then retrieved."""
    _, _, _, _, doc = create_test_hierarchy(db_session)

    chunk = DocumentChunk(
        document_id=doc.id,
        page_number=3,
        chunk_index=1,
        text="A branch target buffer caches branch predictions to minimize pipeline stalls.",
    )
    db_session.add(chunk)
    db_session.commit()
    db_session.refresh(chunk)

    # Store embedding using Phase 8 service
    updated_chunk = store_document_chunk_embedding(db_session, chunk)
    chunk_id = updated_chunk.id

    # Retrieve freshly from database
    retrieved = db_session.get(DocumentChunk, chunk_id)
    assert retrieved is not None
    assert is_valid_embedding(retrieved.embedding)
    assert len(retrieved.embedding) == 384
    assert all(math.isfinite(v) for v in retrieved.embedding)

    norm = sum(v * v for v in retrieved.embedding)
    assert math.isclose(norm, 1.0, rel_tol=1e-3)

    # Provenance preservation check
    assert retrieved.document_id == doc.id
    assert retrieved.page_number == 3
    assert retrieved.chunk_index == 1
    assert retrieved.text == "A branch target buffer caches branch predictions to minimize pipeline stalls."


def test_hindi_chunk_vector_storage_and_retrieval(db_session: Session):
    """Verifies storing and retrieving Devanagari Hindi text embedding in PostgreSQL/pgvector."""
    _, _, _, video, _ = create_test_hierarchy(db_session)

    chunk = TranscriptChunk(
        video_id=video.id,
        start_time=0.0,
        end_time=15.0,
        text="पाइपलाइनिंग आर्किटेक्चर में डेटा हेज़ार्ड्स को हल करने के विभिन्न तरीके हैं।",
    )
    db_session.add(chunk)
    db_session.commit()

    updated = store_transcript_chunk_embedding(db_session, chunk)
    retrieved = db_session.get(TranscriptChunk, updated.id)

    assert is_valid_embedding(retrieved.embedding)
    assert len(retrieved.embedding) == 384
    assert all(math.isfinite(v) for v in retrieved.embedding)
    norm = sum(v * v for v in retrieved.embedding)
    assert math.isclose(norm, 1.0, rel_tol=1e-3)


def test_generic_store_chunk_embedding_dispatcher(db_session: Session):
    """Verifies that store_chunk_embedding correctly handles both model types."""
    _, _, _, video, doc = create_test_hierarchy(db_session)

    tc = TranscriptChunk(video_id=video.id, start_time=1.0, end_time=2.0, text="Transcript text")
    dc = DocumentChunk(document_id=doc.id, page_number=1, chunk_index=0, text="Document text")
    db_session.add_all([tc, dc])
    db_session.commit()

    res_tc = store_chunk_embedding(db_session, tc)
    res_dc = store_chunk_embedding(db_session, dc)

    assert is_valid_embedding(res_tc.embedding)
    assert is_valid_embedding(res_dc.embedding)


def test_batch_storage_success(db_session: Session):
    """Verifies batch embedding and persistence across multiple chunks."""
    _, _, _, video, doc = create_test_hierarchy(db_session)

    c1 = TranscriptChunk(video_id=video.id, start_time=0.0, end_time=5.0, text="Cache memory hierarchy and locality of reference.")
    c2 = TranscriptChunk(video_id=video.id, start_time=5.0, end_time=10.0, text="Direct-mapped versus set-associative caches.")
    c3 = DocumentChunk(document_id=doc.id, page_number=1, chunk_index=0, text="Virtual memory page tables and TLB lookups.")
    c4 = DocumentChunk(document_id=doc.id, page_number=1, chunk_index=1, text="Page replacement algorithms: LRU, FIFO, and Optimal.")

    chunks = [c1, c2, c3, c4]
    db_session.add_all(chunks)
    db_session.commit()

    result = store_chunks_embeddings_batch(db_session, chunks, batch_size=2)

    assert result == BatchStorageResult(total=4, updated=4, skipped=0)

    for c in chunks:
        retrieved = db_session.get(type(c), c.id)
        assert is_valid_embedding(retrieved.embedding)
        assert len(retrieved.embedding) == 384
        assert all(math.isfinite(v) for v in retrieved.embedding)


def test_batch_storage_empty_list(db_session: Session):
    """Verifies handling of empty batch input."""
    result = store_chunks_embeddings_batch(db_session, [])
    assert result == BatchStorageResult(total=0, updated=0, skipped=0)


def test_idempotency_skips_valid_embeddings(db_session: Session):
    """Verifies that chunks with valid embeddings are skipped unless force=True."""
    _, _, _, video, _ = create_test_hierarchy(db_session)

    chunk = TranscriptChunk(video_id=video.id, start_time=0.0, end_time=10.0, text="Idempotency test text.")
    db_session.add(chunk)
    db_session.commit()

    # First store: generates and saves embedding
    store_transcript_chunk_embedding(db_session, chunk)
    original_vector = list(chunk.embedding)

    # Second store (force=False): should skip
    with patch("app.services.vector_storage.get_embedding_service") as mock_get_service:
        same_chunk = store_transcript_chunk_embedding(db_session, chunk, force=False)
        # Service should not have been called because it skipped
        mock_get_service.assert_not_called()
        assert same_chunk.embedding == original_vector

    # Batch test: should report skipped=1, updated=0
    batch_res = store_chunks_embeddings_batch(db_session, [chunk], force=False)
    assert batch_res.skipped == 1
    assert batch_res.updated == 0


def test_force_flag_reembeds(db_session: Session):
    """Verifies that force=True re-generates the embedding even if one exists."""
    _, _, _, video, _ = create_test_hierarchy(db_session)

    chunk = TranscriptChunk(video_id=video.id, start_time=0.0, end_time=10.0, text="Force re-embed test.")
    db_session.add(chunk)
    db_session.commit()

    store_transcript_chunk_embedding(db_session, chunk)

    # Re-embed with force=True
    updated = store_transcript_chunk_embedding(db_session, chunk, force=True)
    assert is_valid_embedding(updated.embedding)
    assert len(updated.embedding) == 384


def test_invalid_chunk_text_rejected(db_session: Session):
    """Verifies that empty or whitespace-only text raises ChunkValidationError."""
    _, _, _, video, _ = create_test_hierarchy(db_session)

    empty_chunk = TranscriptChunk(video_id=video.id, start_time=0.0, end_time=5.0, text="")
    db_session.add(empty_chunk)
    db_session.commit()

    with pytest.raises(ChunkValidationError, match="empty or whitespace-only"):
        store_transcript_chunk_embedding(db_session, empty_chunk)

    whitespace_chunk = TranscriptChunk(video_id=video.id, start_time=5.0, end_time=10.0, text="   \n\t  ")
    db_session.add(whitespace_chunk)
    db_session.commit()

    with pytest.raises(ChunkValidationError, match="empty or whitespace-only"):
        store_transcript_chunk_embedding(db_session, whitespace_chunk)


def test_unsupported_chunk_type_rejected(db_session: Session):
    """Verifies that passing an unknown type to store_chunk_embedding raises error."""
    with pytest.raises(ChunkValidationError, match="Unsupported chunk type"):
        store_chunk_embedding(db_session, "not_a_chunk")  # type: ignore


def test_transaction_rollback_on_db_failure(db_session: Session):
    """Verifies that database failure during commit triggers rollback and raises VectorPersistenceError."""
    _, _, _, video, _ = create_test_hierarchy(db_session)

    chunk = TranscriptChunk(video_id=video.id, start_time=0.0, end_time=5.0, text="Rollback test chunk.")
    db_session.add(chunk)
    db_session.commit()

    with patch.object(db_session, "commit", side_effect=Exception("Simulated DB connection drop")):
        with pytest.raises(VectorPersistenceError, match="Database error persisting"):
            store_transcript_chunk_embedding(db_session, chunk)


def test_phase7_embedding_service_reused(db_session: Session):
    """Verifies that Phase 7 EmbeddingService is invoked without duplicating model loading."""
    _, _, _, video, _ = create_test_hierarchy(db_session)

    chunk = TranscriptChunk(video_id=video.id, start_time=0.0, end_time=5.0, text="Service reuse verification.")
    db_session.add(chunk)
    db_session.commit()

    mock_service = MagicMock()
    mock_service.embed_text.return_value = [0.05] * 384

    store_transcript_chunk_embedding(db_session, chunk, embedding_service=mock_service)
    mock_service.embed_text.assert_called_once_with("Service reuse verification.")


def test_video_level_batch_storage_helper(db_session: Session):
    """Verifies store_transcript_chunks_for_video helper embeds all chunks for a video."""
    _, _, _, video, _ = create_test_hierarchy(db_session)

    tc1 = TranscriptChunk(video_id=video.id, start_time=0.0, end_time=10.0, text="Video chunk 1")
    tc2 = TranscriptChunk(video_id=video.id, start_time=10.0, end_time=20.0, text="Video chunk 2")
    db_session.add_all([tc1, tc2])
    db_session.commit()

    res = store_transcript_chunks_for_video(db_session, video.id)
    assert res == BatchStorageResult(total=2, updated=2, skipped=0)

    for tc in [tc1, tc2]:
        refreshed = db_session.get(TranscriptChunk, tc.id)
        assert is_valid_embedding(refreshed.embedding)


def test_document_level_batch_storage_helper(db_session: Session):
    """Verifies store_document_chunks_for_document helper embeds all chunks for a document."""
    _, _, _, _, doc = create_test_hierarchy(db_session)

    dc1 = DocumentChunk(document_id=doc.id, page_number=1, chunk_index=0, text="Doc chunk 1")
    dc2 = DocumentChunk(document_id=doc.id, page_number=2, chunk_index=0, text="Doc chunk 2")
    db_session.add_all([dc1, dc2])
    db_session.commit()

    res = store_document_chunks_for_document(db_session, doc.id)
    assert res == BatchStorageResult(total=2, updated=2, skipped=0)

    for dc in [dc1, dc2]:
        refreshed = db_session.get(DocumentChunk, dc.id)
        assert is_valid_embedding(refreshed.embedding)
