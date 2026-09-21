import uuid
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.user import User
from app.models.subject import Subject
from app.models.playlist import Playlist
from app.models.video import Video
from app.models.chunk import TranscriptChunk
from app.services.transcript import chunk_transcript


def register_and_login(client: TestClient, email: str, password: str = "Password123!") -> tuple[dict, str]:
    """Helper to register and login a user."""
    client.post("/api/auth/register", json={"email": email, "password": password})
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    token = res.json()["access_token"]
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    return me_res.json(), token


def setup_user_subject_playlist_video(
    client: TestClient, db: Session, email: str, video_count: int = 1
) -> tuple[str, str, str, list[str]]:
    """
    Creates a user, subject, playlist, and N videos directly or via API.
    Returns (token, subject_id, playlist_id, [video_ids]).
    """
    _, token = register_and_login(client, email)

    # 1. Create subject
    s_res = client.post(
        "/api/subjects",
        json={"name": f"Subject for {email}", "description": "Desc"},
        headers={"Authorization": f"Bearer {token}"},
    )
    subject_id = s_res.json()["id"]

    # 2. Add Playlist & Videos to DB
    user = db.execute(select(User).where(User.email == email)).scalar_one()
    pl = Playlist(
        subject_id=uuid.UUID(subject_id),
        youtube_playlist_id=f"PL_{uuid.uuid4().hex[:8]}",
        title="Test Playlist",
        status="completed",
    )
    db.add(pl)
    db.flush()

    video_ids = []
    for i in range(video_count):
        v = Video(
            playlist_id=pl.id,
            youtube_video_id=f"vid_{uuid.uuid4().hex[:8]}",
            title=f"Lecture {i + 1}",
            duration_seconds=300,
            status="pending",
            transcript_source="none",
        )
        db.add(v)
        db.flush()
        video_ids.append(str(v.id))

    db.commit()
    return token, subject_id, str(pl.id), video_ids


# ============================================================
# 1. UNIT TEST: Chunking Algorithm & Timestamp Preservation
# ============================================================

def test_chunking_preserves_chronological_order_and_timestamps():
    """Verify that chunking creates 60-90s windows, preserves timestamps, and respects punctuation."""
    snippets = [
        {"text": "Hello world.", "start": 0.0, "duration": 5.0},
        {"text": "This is operating systems.", "start": 5.0, "duration": 15.0},
        {"text": "Today we discuss processes.", "start": 20.0, "duration": 25.0},
        {"text": "A process is a program in execution.", "start": 45.0, "duration": 20.0},
        {"text": "Next topic is threads.", "start": 65.0, "duration": 15.0},
        {"text": "Threads share memory space.", "start": 80.0, "duration": 15.0},
    ]

    chunks = chunk_transcript(snippets, min_duration=60.0, max_duration=90.0)

    assert len(chunks) >= 1
    for c in chunks:
        assert c["start_time"] < c["end_time"]
        assert len(c["text"]) > 0

    # First chunk should start at 0.0
    assert chunks[0]["start_time"] == 0.0
    # Text from early snippets must appear in order
    assert "Hello world." in chunks[0]["text"]
    assert "Today we discuss processes." in chunks[0]["text"]

    # Verify chronological ordering of chunks
    for i in range(len(chunks) - 1):
        assert chunks[i]["end_time"] <= chunks[i + 1]["start_time"] or chunks[i]["start_time"] < chunks[i + 1]["start_time"]


def test_chunking_empty_or_whitespace_snippets():
    """Empty snippet list should return empty chunks list."""
    assert chunk_transcript([]) == []
    assert chunk_transcript([{"text": "   ", "start": 0.0, "duration": 5.0}]) == []


# ============================================================
# 2. AUTHENTICATION & OWNERSHIP (IDOR)
# ============================================================

def test_unauthenticated_transcript_endpoints_rejected(client: TestClient):
    """Unauthenticated access to any transcript endpoint must return 401 Unauthorized."""
    random_id = uuid.uuid4()

    res1 = client.post(f"/api/videos/{random_id}/transcript/processing")
    assert res1.status_code == 401

    res2 = client.get(f"/api/videos/{random_id}/transcript")
    assert res2.status_code == 401

    res3 = client.get(f"/api/videos/{random_id}/transcript/status")
    assert res3.status_code == 401

    res4 = client.post(f"/api/playlists/{random_id}/transcripts/processing")
    assert res4.status_code == 401


def test_idor_cross_user_video_transcript_access_rejected(client: TestClient, db_session: Session):
    """User B cannot process or retrieve transcripts for User A's video (returns 404 IDOR defense)."""
    token_a, _, _, video_ids_a = setup_user_subject_playlist_video(client, db_session, "usera_t@example.com")
    _, token_b = register_and_login(client, "userb_t@example.com")

    vid = video_ids_a[0]

    # User B tries to process User A's video
    res_proc = client.post(
        f"/api/videos/{vid}/transcript/processing",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_proc.status_code == 404
    assert "Video not found or access denied" in res_proc.json()["detail"]

    # User B tries to get User A's transcript
    res_get = client.get(
        f"/api/videos/{vid}/transcript",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_get.status_code == 404

    # User B tries to get User A's transcript status
    res_status = client.get(
        f"/api/videos/{vid}/transcript/status",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_status.status_code == 404


def test_idor_cross_user_playlist_transcripts_rejected(client: TestClient, db_session: Session):
    """User B cannot trigger playlist transcript processing for User A's playlist (returns 404)."""
    _, _, playlist_id_a, _ = setup_user_subject_playlist_video(client, db_session, "user_pl_a@example.com")
    _, token_b = register_and_login(client, "user_pl_b@example.com")

    res = client.post(
        f"/api/playlists/{playlist_id_a}/transcripts/processing",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res.status_code == 404
    assert "Playlist not found or access denied" in res.json()["detail"]


# ============================================================
# 3. CAPTION SUCCESS (ENGLISH & HINDI)
# ============================================================

def test_single_video_caption_success_english(client: TestClient, db_session: Session):
    """Test successful English caption retrieval, chunk storage, and status update."""
    token, _, _, video_ids = setup_user_subject_playlist_video(client, db_session, "en_cap_user@example.com")
    vid = video_ids[0]

    mock_snippets = [
        {"text": "Welcome to Operating Systems.", "start": 0.0, "duration": 5.0},
        {"text": "Today we discuss the CPU scheduler.", "start": 5.0, "duration": 60.0},
    ]

    with patch("app.services.transcript.fetch_youtube_captions", return_value=(mock_snippets, "en")):
        res = client.post(
            f"/api/videos/{vid}/transcript/processing",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert res.status_code == 200
    data = res.json()
    assert data["transcript_status"] == "available"
    assert data["processing_status"] == "completed"
    assert data["transcript_source"] == "caption"
    assert data["chunk_count"] >= 1

    # Verify in DB
    db_video = db_session.execute(select(Video).where(Video.id == uuid.UUID(vid))).scalar_one()
    assert db_video.status == "completed"
    assert db_video.transcript_source == "caption"
    assert db_video.error_message is None

    chunks = db_session.execute(
        select(TranscriptChunk).where(TranscriptChunk.video_id == uuid.UUID(vid))
    ).scalars().all()
    assert len(chunks) >= 1
    assert chunks[0].start_time == 0.0
    assert "Welcome to Operating Systems." in chunks[0].text
    # Embedding vector exists and matches 384 dimensions
    assert len(chunks[0].embedding) == 384

    # Verify GET transcript
    get_res = client.get(
        f"/api/videos/{vid}/transcript",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.status_code == 200
    t_data = get_res.json()
    assert len(t_data["data"]) >= 1
    assert t_data["data"][0]["language"] == "en"
    assert t_data["data"][0]["start_time_seconds"] == 0.0


def test_single_video_caption_success_hindi_preservation(client: TestClient, db_session: Session):
    """Test Hindi / Hinglish caption retrieval preserves original script and detects Hindi language."""
    token, _, _, video_ids = setup_user_subject_playlist_video(client, db_session, "hi_cap_user@example.com")
    vid = video_ids[0]

    mock_hindi_snippets = [
        {"text": "नमस्ते दोस्तों, आज हम प्रोसेस शेड्यूलिंग समझेंगे।", "start": 0.0, "duration": 10.0},
        {"text": "Round robin algorithm time sharing systems ke liye best hota hai.", "start": 10.0, "duration": 55.0},
    ]

    with patch("app.services.transcript.fetch_youtube_captions", return_value=(mock_hindi_snippets, "hi")):
        res = client.post(
            f"/api/videos/{vid}/transcript/processing",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert res.status_code == 200
    assert res.json()["transcript_status"] == "available"
    assert res.json()["transcript_source"] == "caption"

    # Verify Devanagari text is stored verbatim without translation
    get_res = client.get(
        f"/api/videos/{vid}/transcript",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.status_code == 200
    segments = get_res.json()["data"]
    assert len(segments) >= 1
    assert "नमस्ते दोस्तों" in segments[0]["text"]
    assert segments[0]["language"] == "hi"


# ============================================================
# 4. FASTER-WHISPER FALLBACK
# ============================================================

def test_whisper_fallback_when_captions_unavailable(client: TestClient, db_session: Session):
    """When captions return None, system must fall back to local faster-whisper."""
    token, _, _, video_ids = setup_user_subject_playlist_video(client, db_session, "whisper_user@example.com")
    vid = video_ids[0]

    mock_whisper_snippets = [
        {"text": "Transcribed by local faster-whisper fallback.", "start": 0.0, "duration": 65.0}
    ]

    # Captions fail, Whisper succeeds
    with patch("app.services.transcript.fetch_youtube_captions", return_value=None), \
         patch("app.services.transcript.transcribe_with_whisper", return_value=(mock_whisper_snippets, "en")):
        res = client.post(
            f"/api/videos/{vid}/transcript/processing",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert res.status_code == 200
    data = res.json()
    assert data["transcript_status"] == "available"
    assert data["processing_status"] == "completed"
    assert data["transcript_source"] == "whisper"

    db_video = db_session.execute(select(Video).where(Video.id == uuid.UUID(vid))).scalar_one()
    assert db_video.status == "completed"
    assert db_video.transcript_source == "whisper"


def test_both_captions_and_whisper_fail(client: TestClient, db_session: Session):
    """When both captions and Whisper fail, transcript_source must be 'none' and status 'failed'."""
    token, _, _, video_ids = setup_user_subject_playlist_video(client, db_session, "both_fail_user@example.com")
    vid = video_ids[0]

    with patch("app.services.transcript.fetch_youtube_captions", return_value=None), \
         patch("app.services.transcript.transcribe_with_whisper", return_value=None):
        res = client.post(
            f"/api/videos/{vid}/transcript/processing",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert res.status_code == 200
    data = res.json()
    assert data["transcript_status"] == "failed"
    assert data["processing_status"] == "failed"
    assert data["transcript_source"] == "none"
    assert "Captions unavailable and Whisper fallback failed" in data["processing_error"]

    db_video = db_session.execute(select(Video).where(Video.id == uuid.UUID(vid))).scalar_one()
    assert db_video.status == "failed"
    assert db_video.transcript_source == "none"
    assert "Captions unavailable and Whisper fallback failed" in db_video.error_message


# ============================================================
# 5. DUPLICATE TRANSCRIPT PREVENTION
# ============================================================

def test_duplicate_transcript_prevention(client: TestClient, db_session: Session):
    """
    Clicking [Retrieve Transcript] multiple times on an already completed video
    must NOT duplicate chunks in the database.
    """
    token, _, _, video_ids = setup_user_subject_playlist_video(client, db_session, "dup_prevent_user@example.com")
    vid = video_ids[0]

    mock_snippets = [
        {"text": "Unique lecture chunk sentence one.", "start": 0.0, "duration": 30.0},
        {"text": "Unique lecture chunk sentence two.", "start": 30.0, "duration": 40.0},
    ]

    with patch("app.services.transcript.fetch_youtube_captions", return_value=(mock_snippets, "en")):
        # First call: processes and stores
        res1 = client.post(
            f"/api/videos/{vid}/transcript/processing",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res1.status_code == 200

        initial_count = db_session.execute(
            select(TranscriptChunk).where(TranscriptChunk.video_id == uuid.UUID(vid))
        ).scalars().all()
        assert len(initial_count) == 1

        # Second call: repeated click without force
        res2 = client.post(
            f"/api/videos/{vid}/transcript/processing",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res2.status_code == 200

        second_count = db_session.execute(
            select(TranscriptChunk).where(TranscriptChunk.video_id == uuid.UUID(vid))
        ).scalars().all()
        # Chunks must NOT have multiplied!
        assert len(second_count) == len(initial_count)

        # Third call: with force=True (safe refresh/re-fetch)
        res3 = client.post(
            f"/api/videos/{vid}/transcript/processing?force=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res3.status_code == 200
        third_count = db_session.execute(
            select(TranscriptChunk).where(TranscriptChunk.video_id == uuid.UUID(vid))
        ).scalars().all()
        assert len(third_count) == len(initial_count)


# ============================================================
# 6. PLAYLIST-WIDE TRANSCRIPT RETRIEVAL & FAILURE ISOLATION
# ============================================================

def test_playlist_wide_processing_with_failure_isolation(client: TestClient, db_session: Session):
    """
    CRITICAL REQUIREMENT:
    In a playlist with 3 videos:
      Video 1 -> SUCCESS (captions)
      Video 2 -> FAILURE (both fail)
      Video 3 -> SUCCESS (whisper fallback)
    Video 2 failure must NOT rollback or abort Video 1 or Video 3.
    Final states must be: Video 1 completed, Video 2 failed, Video 3 completed.
    """
    token, _, playlist_id, video_ids = setup_user_subject_playlist_video(
        client, db_session, "iso_user@example.com", video_count=3
    )

    v1_id, v2_id, v3_id = video_ids

    def mock_fetch_captions(yt_id: str):
        # Look up which video this is
        vid_obj = db_session.execute(select(Video).where(Video.youtube_video_id == yt_id)).scalar_one_or_none()
        if vid_obj and str(vid_obj.id) == v1_id:
            return ([{"text": "Video 1 caption text.", "start": 0.0, "duration": 65.0}], "en")
        return None  # V2 and V3 have no captions

    def mock_whisper(yt_id: str):
        vid_obj = db_session.execute(select(Video).where(Video.youtube_video_id == yt_id)).scalar_one_or_none()
        if vid_obj and str(vid_obj.id) == v3_id:
            return ([{"text": "Video 3 whisper text.", "start": 0.0, "duration": 70.0}], "en")
        return None  # V2 fails on whisper as well

    with patch("app.services.transcript.fetch_youtube_captions", side_effect=mock_fetch_captions), \
         patch("app.services.transcript.transcribe_with_whisper", side_effect=mock_whisper):
        res = client.post(
            f"/api/playlists/{playlist_id}/transcripts/processing",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert res.status_code == 200
    summary = res.json()
    assert summary["total"] == 3
    assert summary["completed"] == 2
    assert summary["failed"] == 1

    # Verify per-video status in DB
    db_v1 = db_session.execute(select(Video).where(Video.id == uuid.UUID(v1_id))).scalar_one()
    db_v2 = db_session.execute(select(Video).where(Video.id == uuid.UUID(v2_id))).scalar_one()
    db_v3 = db_session.execute(select(Video).where(Video.id == uuid.UUID(v3_id))).scalar_one()

    assert db_v1.status == "completed"
    assert db_v1.transcript_source == "caption"

    assert db_v2.status == "failed"
    assert db_v2.transcript_source == "none"

    assert db_v3.status == "completed"
    assert db_v3.transcript_source == "whisper"

    # Verify V1 and V3 have stored chunks in DB, V2 has none
    v1_chunks = db_session.execute(select(TranscriptChunk).where(TranscriptChunk.video_id == uuid.UUID(v1_id))).scalars().all()
    v2_chunks = db_session.execute(select(TranscriptChunk).where(TranscriptChunk.video_id == uuid.UUID(v2_id))).scalars().all()
    v3_chunks = db_session.execute(select(TranscriptChunk).where(TranscriptChunk.video_id == uuid.UUID(v3_id))).scalars().all()

    assert len(v1_chunks) >= 1
    assert len(v2_chunks) == 0
    assert len(v3_chunks) >= 1


def test_transcript_status_endpoint(client: TestClient, db_session: Session):
    """Test GET /videos/{video_id}/transcript/status returns expected UI shape."""
    token, _, _, video_ids = setup_user_subject_playlist_video(client, db_session, "status_test@example.com")
    vid = video_ids[0]

    res = client.get(
        f"/api/videos/{vid}/transcript/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["transcript_status"] == "pending"
    assert data["processing_status"] == "pending"
    assert data["transcript_source"] == "none"


def test_api_v1_prefix_compatibility(client: TestClient, db_session: Session):
    """Verify endpoints are also accessible via /api/v1 prefix."""
    token, _, playlist_id, video_ids = setup_user_subject_playlist_video(client, db_session, "v1_user@example.com")
    vid = video_ids[0]

    mock_snippets = [{"text": "v1 prefix test segment.", "start": 0.0, "duration": 65.0}]
    with patch("app.services.transcript.fetch_youtube_captions", return_value=(mock_snippets, "en")):
        res1 = client.post(
            f"/api/v1/videos/{vid}/transcript/processing",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res1.status_code == 200

        res2 = client.get(
            f"/api/v1/videos/{vid}/transcript",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res2.status_code == 200
        assert len(res2.json()["data"]) >= 1

        res3 = client.get(
            f"/api/v1/videos/{vid}/transcript/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res3.status_code == 200
        assert res3.json()["data"]["transcript_status"] == "available"


# ---------------------------------------------------------------------------
# Whisper temporary-directory cleanup retry tests (Phase 5 cleanup bug fix)
# ---------------------------------------------------------------------------

class TestWhisperTempDirCleanup:
    """
    Unit tests for the bounded-retry temp-dir cleanup in transcribe_with_whisper().
    All tests simulate the yt-dlp download path without hitting the network.
    """

    def _make_fake_download(self, temp_dir: str, filename: str = "testvid.m4a") -> None:
        """Write a small fake audio file into temp_dir to simulate yt-dlp output."""
        import os
        with open(os.path.join(temp_dir, filename), "wb") as fh:
            fh.write(b"\x00" * 4096)  # 4 KB placeholder — passes the 1024-byte size check

    def test_cleanup_succeeds_on_first_attempt(self, tmp_path):
        """
        Normal path: rmtree succeeds immediately — directory is gone after the call.
        """
        import os
        import shutil
        from unittest.mock import patch, MagicMock

        # Build a real temporary directory with a dummy file inside
        target_dir = str(tmp_path / "sr_whisper_test_ok")
        os.makedirs(target_dir)
        self._make_fake_download(target_dir)
        assert os.path.isdir(target_dir)

        # Patch tempfile.mkdtemp to return our controlled dir
        # and yt_dlp.YoutubeDL to simulate a successful download
        fake_model = MagicMock()
        fake_segments_gen = iter([])  # no segments — transcription "succeeds" with empty output
        fake_info = MagicMock(language="en")
        fake_model.transcribe.return_value = (fake_segments_gen, fake_info)

        with patch("tempfile.mkdtemp", return_value=target_dir), \
             patch("yt_dlp.YoutubeDL") as mock_ydl_cls, \
             patch("app.services.transcript.get_whisper_model", return_value=fake_model):
            mock_ydl_instance = MagicMock()
            mock_ydl_cls.return_value.__enter__ = lambda s: mock_ydl_instance
            mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)

            from app.services.transcript import transcribe_with_whisper
            transcribe_with_whisper("_test_ok_")

        # Directory must be gone
        assert not os.path.exists(target_dir), \
            f"Temp dir was NOT removed: {target_dir}"

    def test_cleanup_succeeds_after_one_oserror(self, tmp_path):
        """
        Retry path: first rmtree call raises OSError (simulating Windows file lock);
        second call succeeds. Directory must be removed after the retry.
        """
        import os
        import shutil
        from unittest.mock import patch, MagicMock, call

        target_dir = str(tmp_path / "sr_whisper_test_retry")
        os.makedirs(target_dir)
        self._make_fake_download(target_dir)

        # We'll track how many times shutil.rmtree is called and fail the first time
        real_rmtree = shutil.rmtree
        call_count = {"n": 0}

        def patched_rmtree(path, onerror=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise OSError("simulated Windows file lock")
            # Second attempt: delegate to real rmtree
            real_rmtree(path)

        fake_model = MagicMock()
        fake_model.transcribe.return_value = (iter([]), MagicMock(language="en"))

        with patch("tempfile.mkdtemp", return_value=target_dir), \
             patch("yt_dlp.YoutubeDL") as mock_ydl_cls, \
             patch("app.services.transcript.get_whisper_model", return_value=fake_model), \
             patch("app.services.transcript.shutil.rmtree", side_effect=patched_rmtree), \
             patch("time.sleep"):          # suppress real sleep during test
            mock_ydl_cls.return_value.__enter__ = lambda s: MagicMock()
            mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)

            from app.services.transcript import transcribe_with_whisper
            transcribe_with_whisper("_test_retry_")

        assert call_count["n"] == 2, f"Expected 2 rmtree calls, got {call_count['n']}"

    def test_cleanup_logs_warning_after_all_attempts_fail(self, tmp_path, caplog):
        """
        All-fail path: all 3 rmtree attempts raise OSError.
        A WARNING must be emitted; no unhandled exception must propagate.
        """
        import os
        from unittest.mock import patch, MagicMock
        import logging

        target_dir = str(tmp_path / "sr_whisper_test_allfail")
        os.makedirs(target_dir)
        self._make_fake_download(target_dir)

        fake_model = MagicMock()
        fake_model.transcribe.return_value = (iter([]), MagicMock(language="en"))

        # Track how many times rmtree is called (expect exactly 3 — max retry attempts)
        call_count = {"n": 0}

        def always_fail(path, onerror=None):
            call_count["n"] += 1
            raise OSError("locked")

        with patch("tempfile.mkdtemp", return_value=target_dir), \
             patch("yt_dlp.YoutubeDL") as mock_ydl_cls, \
             patch("app.services.transcript.get_whisper_model", return_value=fake_model), \
             patch("app.services.transcript.shutil.rmtree", side_effect=always_fail), \
             patch("time.sleep"):
            mock_ydl_cls.return_value.__enter__ = lambda s: MagicMock()
            mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
            from app.services.transcript import transcribe_with_whisper
            # Must NOT raise — failure to clean up is non-fatal
            result = transcribe_with_whisper("_test_allfail_")

        # Exactly 3 rmtree attempts must have been made (the retry cap)
        assert call_count["n"] == 3, \
            f"Expected 3 rmtree attempts, got {call_count['n']}"

    def test_cleanup_onerror_clears_readonly_bit(self, tmp_path):
        """
        The _force_remove_readonly onerror handler sets S_IWRITE then retries.
        Simulate a read-only file — rmtree must still succeed via the handler.
        """
        import os
        import stat
        import shutil
        from unittest.mock import patch, MagicMock

        target_dir = str(tmp_path / "sr_whisper_test_readonly")
        os.makedirs(target_dir)
        fpath = os.path.join(target_dir, "locked.m4a")
        with open(fpath, "wb") as fh:
            fh.write(b"\x00" * 4096)
        # Make the file read-only so the first rmtree attempt fails on Windows
        os.chmod(fpath, stat.S_IREAD)

        fake_model = MagicMock()
        fake_model.transcribe.return_value = (iter([]), MagicMock(language="en"))

        with patch("tempfile.mkdtemp", return_value=target_dir), \
             patch("yt_dlp.YoutubeDL") as mock_ydl_cls, \
             patch("app.services.transcript.get_whisper_model", return_value=fake_model), \
             patch("time.sleep"):
            mock_ydl_cls.return_value.__enter__ = lambda s: MagicMock()
            mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)

            from app.services.transcript import transcribe_with_whisper
            transcribe_with_whisper("_test_readonly_")

        # Directory must be gone regardless of the read-only file
        assert not os.path.exists(target_dir), \
            f"Temp dir with read-only file was NOT removed: {target_dir}"
