import uuid
import pytest
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text, select

from app.models import (
    User,
    Subject,
    Playlist,
    Video,
    Document,
    TranscriptChunk,
    DocumentChunk,
)

def test_tables_exist(db_session: Session):
    """Verify all expected StudyRewinds tables exist in PostgreSQL."""
    result = db_session.execute(text("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public';
    """)).scalars().all()
    
    expected_tables = {
        "users",
        "subjects",
        "playlists",
        "videos",
        "documents",
        "transcript_chunks",
        "document_chunks",
        "alembic_version",
    }
    for table in expected_tables:
        assert table in result, f"Table {table} not found in database!"

def test_cascade_delete_youtube_tree(db_session: Session):
    """Verify deleting a User cascades to Subject -> Playlist -> Video -> TranscriptChunk."""
    # 1. Create full hierarchy
    user = User(email="test_user@example.com", hashed_password="hashed_pw_test")
    db_session.add(user)
    db_session.flush()

    subject = Subject(user_id=user.id, name="Computer Networks")
    db_session.add(subject)
    db_session.flush()

    playlist = Playlist(
        subject_id=subject.id,
        youtube_playlist_id="PL12345",
        title="CN Lectures",
        status="completed",
    )
    db_session.add(playlist)
    db_session.flush()

    video = Video(
        playlist_id=playlist.id,
        youtube_video_id="vid_001",
        title="OSI Model Overview",
        duration_seconds=1200,
        transcript_source="caption",
        status="completed",
    )
    db_session.add(video)
    db_session.flush()

    dummy_vector = [0.1] * 384
    chunk = TranscriptChunk(
        video_id=video.id,
        start_time=10.0,
        end_time=60.0,
        text="Introduction to layer 7 application layer.",
        embedding=dummy_vector,
    )
    db_session.add(chunk)
    db_session.commit()

    # Verify rows exist
    assert db_session.execute(select(TranscriptChunk).where(TranscriptChunk.id == chunk.id)).scalar_one() is not None

    # 2. Delete User
    db_session.delete(user)
    db_session.commit()

    # 3. Assert all cascaded rows are gone
    assert db_session.execute(select(Subject).where(Subject.id == subject.id)).scalar_one_or_none() is None
    assert db_session.execute(select(Playlist).where(Playlist.id == playlist.id)).scalar_one_or_none() is None
    assert db_session.execute(select(Video).where(Video.id == video.id)).scalar_one_or_none() is None
    assert db_session.execute(select(TranscriptChunk).where(TranscriptChunk.id == chunk.id)).scalar_one_or_none() is None

def test_cascade_delete_document_tree(db_session: Session):
    """Verify deleting a User cascades to Subject -> Document -> DocumentChunk."""
    user = User(email="doc_user@example.com", hashed_password="hashed_pw_test")
    db_session.add(user)
    db_session.flush()

    subject = Subject(user_id=user.id, name="Operating Systems")
    db_session.add(subject)
    db_session.flush()

    document = Document(
        subject_id=subject.id,
        filename="lecture_01.pdf",
        file_path="/storage/documents/lecture_01.pdf",
        page_count=25,
        status="completed",
    )
    db_session.add(document)
    db_session.flush()

    dummy_vector = [0.05] * 384
    doc_chunk = DocumentChunk(
        document_id=document.id,
        page_number=1,
        chunk_index=0,
        text="Process management and threads introduction.",
        embedding=dummy_vector,
    )
    db_session.add(doc_chunk)
    db_session.commit()

    # Verify rows exist
    assert db_session.execute(select(DocumentChunk).where(DocumentChunk.id == doc_chunk.id)).scalar_one() is not None

    # Delete User
    db_session.delete(user)
    db_session.commit()

    # Assert cascaded rows are deleted
    assert db_session.execute(select(Document).where(Document.id == document.id)).scalar_one_or_none() is None
    assert db_session.execute(select(DocumentChunk).where(DocumentChunk.id == doc_chunk.id)).scalar_one_or_none() is None

def test_playlist_uniqueness_constraint(db_session: Session):
    """Verify (subject_id, youtube_playlist_id) unique constraint."""
    user = User(email="unique_playlist@example.com", hashed_password="pw")
    db_session.add(user)
    db_session.flush()

    subj1 = Subject(user_id=user.id, name="Subj 1")
    subj2 = Subject(user_id=user.id, name="Subj 2")
    db_session.add_all([subj1, subj2])
    db_session.flush()

    p1 = Playlist(subject_id=subj1.id, youtube_playlist_id="PL_DUP", title="PL 1")
    db_session.add(p1)
    db_session.commit()

    # Duplicate in same subject must fail
    p1_dup = Playlist(subject_id=subj1.id, youtube_playlist_id="PL_DUP", title="PL 1 Duplicate")
    db_session.add(p1_dup)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Same playlist in a DIFFERENT subject must succeed
    p2 = Playlist(subject_id=subj2.id, youtube_playlist_id="PL_DUP", title="PL 2 Different Subj")
    db_session.add(p2)
    db_session.commit()
    assert p2.id is not None

def test_video_uniqueness_constraint(db_session: Session):
    """Verify (playlist_id, youtube_video_id) unique constraint."""
    user = User(email="unique_vid@example.com", hashed_password="pw")
    db_session.add(user)
    db_session.flush()

    subject = Subject(user_id=user.id, name="Subj Vid")
    db_session.add(subject)
    db_session.flush()

    pl1 = Playlist(subject_id=subject.id, youtube_playlist_id="PL_A", title="PL A")
    pl2 = Playlist(subject_id=subject.id, youtube_playlist_id="PL_B", title="PL B")
    db_session.add_all([pl1, pl2])
    db_session.flush()

    v1 = Video(playlist_id=pl1.id, youtube_video_id="v_100", title="Video 100")
    db_session.add(v1)
    db_session.commit()

    # Duplicate in same playlist must fail
    v1_dup = Video(playlist_id=pl1.id, youtube_video_id="v_100", title="Video 100 Dup")
    db_session.add(v1_dup)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Same video in a different playlist must succeed
    v2 = Video(playlist_id=pl2.id, youtube_video_id="v_100", title="Video 100 in PL B")
    db_session.add(v2)
    db_session.commit()
    assert v2.id is not None

def test_document_filename_not_globally_unique(db_session: Session):
    """Verify that multiple documents can share the same filename."""
    user = User(email="doc_dup@example.com", hashed_password="pw")
    db_session.add(user)
    db_session.flush()

    subject = Subject(user_id=user.id, name="Subj Doc")
    db_session.add(subject)
    db_session.flush()

    d1 = Document(subject_id=subject.id, filename="notes.pdf", file_path="/path/1/notes.pdf", page_count=10)
    d2 = Document(subject_id=subject.id, filename="notes.pdf", file_path="/path/2/notes.pdf", page_count=12)
    db_session.add_all([d1, d2])
    db_session.commit()

    assert d1.id != d2.id
    assert d1.filename == d2.filename
