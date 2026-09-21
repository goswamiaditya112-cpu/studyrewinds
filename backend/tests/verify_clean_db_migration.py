import os
import sys
from pathlib import Path
import psycopg
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.models import (
    User,
    Subject,
    Playlist,
    Video,
    Document,
    TranscriptChunk,
    DocumentChunk,
)

CLEAN_DB_NAME = "studyrewinds_clean_verification_test"
ADMIN_URL = "postgresql://studyrewind:change-me@localhost:5432/studyrewind"
TARGET_URL = f"postgresql://studyrewind:change-me@localhost:5432/{CLEAN_DB_NAME}"
TARGET_URL_SQLALCHEMY = f"postgresql+psycopg://studyrewind:change-me@localhost:5432/{CLEAN_DB_NAME}"

def step_1_create_empty_db():
    print(f"Step 1: Dropping and recreating clean database '{CLEAN_DB_NAME}'...")
    conn = psycopg.connect(ADMIN_URL, autocommit=True)
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT pg_terminate_backend(pid) 
            FROM pg_stat_activity 
            WHERE datname = '{CLEAN_DB_NAME}' AND pid <> pg_backend_pid();
        """)
        cur.execute(f"DROP DATABASE IF EXISTS {CLEAN_DB_NAME};")
        cur.execute(f"CREATE DATABASE {CLEAN_DB_NAME};")
    conn.close()

    conn = psycopg.connect(TARGET_URL)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")
        count = cur.fetchone()[0]
        assert count == 0, f"Database is not empty! Table count: {count}"
        print(f"  Confirmed empty database: {count} tables present.")
    conn.close()

def step_2_run_alembic_migration():
    print("Step 2: Executing Alembic upgrade head on empty database...")
    ini_path = backend_dir / "alembic.ini"
    alembic_dir = backend_dir / "alembic"
    
    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("script_location", str(alembic_dir))
    alembic_cfg.set_main_option("sqlalchemy.url", TARGET_URL_SQLALCHEMY)
    
    command.upgrade(alembic_cfg, "head")
    print("  Alembic upgrade completed successfully.")

def step_3_verify_schema():
    print("Step 3: Verifying created tables and vector extension...")
    conn = psycopg.connect(TARGET_URL)
    with conn.cursor() as cur:
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;")
        tables = [r[0] for r in cur.fetchall()]
        print(f"  Tables found ({len(tables)}): {tables}")
        
        expected = {
            "alembic_version",
            "users",
            "subjects",
            "playlists",
            "videos",
            "documents",
            "transcript_chunks",
            "document_chunks",
        }
        missing = expected - set(tables)
        assert not missing, f"Missing tables: {missing}"
        
        cur.execute("SELECT extversion FROM pg_extension WHERE extname='vector';")
        ext = cur.fetchone()
        assert ext is not None, "pgvector extension is NOT installed!"
        print(f"  pgvector extension verified: version {ext[0]}")

        cur.execute("""
            SELECT c.relname, a.attname, atttypmod
            FROM pg_attribute a
            JOIN pg_class c ON a.attrelid = c.oid
            WHERE a.attname = 'embedding' AND c.relname IN ('transcript_chunks', 'document_chunks');
        """)
        dim_rows = cur.fetchall()
        for r in dim_rows:
            assert r[2] == 384, f"Vector column {r[0]}.{r[1]} dimension is {r[2]}, expected 384!"
            print(f"  Vector column verified: {r[0]}.{r[1]} dimension = {r[2]}")
    conn.close()

def step_4_verify_vector_operations():
    print("Step 4: Verifying vector insertion and cosine distance calculation...")
    engine = create_engine(TARGET_URL_SQLALCHEMY, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    session = Session()

    user = User(email="clean_test@example.com", hashed_password="pw")
    session.add(user)
    session.flush()

    subject = Subject(user_id=user.id, name="Test Clean Subject")
    session.add(subject)
    session.flush()

    playlist = Playlist(subject_id=subject.id, youtube_playlist_id="PL_CLEAN", title="Clean PL")
    session.add(playlist)
    session.flush()

    video = Video(playlist_id=playlist.id, youtube_video_id="vid_clean", title="Clean Video")
    session.add(video)
    session.flush()

    v1 = [0.0] * 384
    v1[0] = 1.0

    v2 = [0.0] * 384
    v2[1] = 1.0

    chunk1 = TranscriptChunk(
        video_id=video.id,
        start_time=0.0,
        end_time=10.0,
        text="Chunk 1: Identical direction",
        embedding=v1,
    )
    chunk2 = TranscriptChunk(
        video_id=video.id,
        start_time=10.0,
        end_time=20.0,
        text="Chunk 2: Orthogonal direction",
        embedding=v2,
    )
    session.add_all([chunk1, chunk2])
    session.commit()

    results = session.execute(
        select(
            TranscriptChunk.text,
            TranscriptChunk.embedding.cosine_distance(v1).label("distance")
        ).order_by("distance")
    ).all()

    assert len(results) == 2
    assert results[0][0] == "Chunk 1: Identical direction"
    assert abs(results[0][1] - 0.0) < 1e-4
    assert results[1][0] == "Chunk 2: Orthogonal direction"
    assert abs(results[1][1] - 1.0) < 1e-4
    print(f"  Cosine distance for chunk 1: {results[0][1]:.4f} (expected 0.0)")
    print(f"  Cosine distance for chunk 2: {results[1][1]:.4f} (expected 1.0)")

    session.close()
    engine.dispose()

def step_5_cleanup():
    print(f"Step 5: Dropping temporary clean database '{CLEAN_DB_NAME}'...")
    conn = psycopg.connect(ADMIN_URL, autocommit=True)
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT pg_terminate_backend(pid) 
            FROM pg_stat_activity 
            WHERE datname = '{CLEAN_DB_NAME}' AND pid <> pg_backend_pid();
        """)
        cur.execute(f"DROP DATABASE IF EXISTS {CLEAN_DB_NAME};")
    conn.close()
    print("  Temporary database cleaned up.")

if __name__ == "__main__":
    try:
        step_1_create_empty_db()
        step_2_run_alembic_migration()
        step_3_verify_schema()
        step_4_verify_vector_operations()
        step_5_cleanup()
        print("\n=======================================================")
        print("ALL CLEAN DATABASE VERIFICATION CHECKS PASSED PERFECTLY!")
        print("=======================================================")
    except Exception as e:
        print(f"\nFAILURE during clean database verification: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
