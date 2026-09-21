import math
import pytest
from sqlalchemy.orm import Session
from sqlalchemy import select, text
from app.models import User, Subject, Playlist, Video, Document, TranscriptChunk, DocumentChunk

def make_unit_vector(dim: int, non_zero_idx: int) -> list[float]:
    """Helper to generate a clean unit vector."""
    v = [0.0] * dim
    v[non_zero_idx] = 1.0
    return v

def test_pgvector_transcript_chunk_insertion_and_distance(db_session: Session):
    """Test inserting 384-dim vector and running cosine distance (<=>) query on transcript_chunks."""
    user = User(email="vec_user@example.com", hashed_password="pw")
    db_session.add(user)
    db_session.flush()

    subject = Subject(user_id=user.id, name="Artificial Intelligence")
    db_session.add(subject)
    db_session.flush()

    playlist = Playlist(subject_id=subject.id, youtube_playlist_id="PL_AI", title="AI Lectures")
    db_session.add(playlist)
    db_session.flush()

    video = Video(playlist_id=playlist.id, youtube_video_id="v_ai_1", title="Intro to AI")
    db_session.add(video)
    db_session.flush()

    # Vector 1: aligned with axis 0
    vec1 = make_unit_vector(384, 0)
    # Vector 2: aligned with axis 1 (orthogonal, cosine distance = 1.0)
    vec2 = make_unit_vector(384, 1)

    chunk1 = TranscriptChunk(
        video_id=video.id,
        start_time=0.0,
        end_time=30.0,
        text="Topic A: Vector Search Basics",
        embedding=vec1,
    )
    chunk2 = TranscriptChunk(
        video_id=video.id,
        start_time=30.0,
        end_time=60.0,
        text="Topic B: Orthogonal Concepts",
        embedding=vec2,
    )
    db_session.add_all([chunk1, chunk2])
    db_session.commit()

    # Query using vec1: chunk1 should have distance 0.0, chunk2 should have distance 1.0
    query_vec = make_unit_vector(384, 0)
    
    # Query with pgvector cosine distance operator <=>
    results = db_session.execute(
        select(
            TranscriptChunk.text,
            TranscriptChunk.embedding.cosine_distance(query_vec).label("distance")
        ).order_by("distance")
    ).all()

    assert len(results) == 2
    top_result = results[0]
    second_result = results[1]

    assert top_result[0] == "Topic A: Vector Search Basics"
    assert pytest.approx(top_result[1], abs=1e-4) == 0.0

    assert second_result[0] == "Topic B: Orthogonal Concepts"
    assert pytest.approx(second_result[1], abs=1e-4) == 1.0

def test_pgvector_document_chunk_insertion_and_distance(db_session: Session):
    """Test inserting 384-dim vector and running cosine distance query on document_chunks."""
    user = User(email="vec_doc_user@example.com", hashed_password="pw")
    db_session.add(user)
    db_session.flush()

    subject = Subject(user_id=user.id, name="Database Systems")
    db_session.add(subject)
    db_session.flush()

    document = Document(
        subject_id=subject.id,
        filename="pgvector_guide.pdf",
        file_path="/storage/pgvector_guide.pdf",
        page_count=5,
        status="completed",
    )
    db_session.add(document)
    db_session.flush()

    vec_doc = make_unit_vector(384, 10)
    doc_chunk = DocumentChunk(
        document_id=document.id,
        page_number=3,
        chunk_index=1,
        text="Page 3 content discussing HNSW indexing and cosine distance.",
        embedding=vec_doc,
    )
    db_session.add(doc_chunk)
    db_session.commit()

    # Query with exact vector
    query_vec = make_unit_vector(384, 10)
    result = db_session.execute(
        select(
            DocumentChunk.page_number,
            DocumentChunk.text,
            DocumentChunk.embedding.cosine_distance(query_vec).label("distance")
        )
    ).first()

    assert result is not None
    assert result[0] == 3
    assert pytest.approx(result[2], abs=1e-4) == 0.0
