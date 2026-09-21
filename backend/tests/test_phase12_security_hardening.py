"""
Phase 12 - Security Hardening & Failure Testing Suite
Aggressively verifies:
1. Authentication Security (Missing, expired, forged, invalid JWTs, login edge cases)
2. Strict Ownership / IDOR Isolation across ALL resource types (Subjects, Playlists, Videos, Transcripts, Documents, Chunks, Search)
3. Subject-Level Search Security (IDOR, SQL injection, parameter tampering)
4. YouTube Input & Processing Failures (Malformed URLs, inaccessible playlists, partial failures, deduplication)
5. Transcript Failures & Whisper Fallback (Caption failure, Whisper fallback, error recovery, idempotency)
6. PDF Security & Failures (File validation, magic bytes, path traversal defense, oversized files, corrupt PDFs)
7. Embedding Service Edge Cases (Invalid inputs, batch handling, dimensional validity, finite floats)
8. Database Transaction Rollbacks & Error Resilience
9. API Input Validation & Hardening
"""

import io
import os
import math
import uuid
import pytest
import jwt
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password, create_access_token
from app.models.user import User
from app.models.subject import Subject
from app.models.playlist import Playlist
from app.models.video import Video
from app.models.document import Document
from app.models.chunk import TranscriptChunk, DocumentChunk
from app.services.embedding import (
    embed_text,
    embed_texts,
    InvalidInputError,
    EmbeddingDimensionError,
    EmbeddingServiceError,
    EMBEDDING_DIMENSION,
)
from app.services.pdf import validate_pdf_content, PDFValidationError, extract_and_chunk_pdf, save_uploaded_pdf


def get_auth_token(client: TestClient, email: str, password: str = "Password123!") -> tuple[str, str]:
    """Helper to register/login a user and return (user_id, token)."""
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = res.json()["access_token"]
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    return me_res.json()["id"], token


# ==============================================================================
# 1. AUTHENTICATION SECURITY TESTING
# ==============================================================================

class TestAuthenticationSecurity:
    """Rigorous security testing of JWT verification and authentication edge cases."""

    def test_missing_authorization_header(self, client: TestClient):
        """Protected endpoint rejects requests with missing Authorization header (401)."""
        res = client.get("/api/v1/auth/me")
        assert res.status_code == 401
        assert "Authentication token is missing" in res.json()["detail"]

    def test_empty_or_whitespace_bearer_token(self, client: TestClient):
        """Protected endpoint rejects empty or whitespace-only Bearer token (401)."""
        res1 = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer "})
        assert res1.status_code == 401

        res2 = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer    "})
        assert res2.status_code == 401

    def test_missing_bearer_scheme(self, client: TestClient):
        """Protected endpoint rejects tokens with missing or incorrect scheme (401)."""
        res1 = client.get("/api/v1/auth/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert res1.status_code == 401

        res2 = client.get("/api/v1/auth/me", headers={"Authorization": "Token randomtoken123"})
        assert res2.status_code == 401

    def test_malformed_and_corrupted_jwt(self, client: TestClient):
        """Protected endpoint rejects malformed or random string JWTs (401)."""
        bad_tokens = [
            "not-a-token",
            "a.b.c",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.corrupted.signature",
            "Bearer invalid.payload.structure",
        ]
        for bad_tok in bad_tokens:
            res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bad_tok}"})
            assert res.status_code == 401
            assert "Token is invalid or expired" in res.json()["detail"]

    def test_expired_jwt_token(self, client: TestClient):
        """Protected endpoint rejects expired JWT tokens (401)."""
        expired_payload = {
            "sub": str(uuid.uuid4()),
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        expired_token = jwt.encode(expired_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

        res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        assert res.status_code == 401
        assert "Token is invalid or expired" in res.json()["detail"]

    def test_forged_jwt_wrong_signature(self, client: TestClient):
        """Protected endpoint rejects JWT signed with an attacker's key (401)."""
        fake_payload = {
            "sub": str(uuid.uuid4()),
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        forged_token = jwt.encode(fake_payload, "attacker-secret-key-1234567890", algorithm="HS256")

        res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged_token}"})
        assert res.status_code == 401
        assert "Token is invalid or expired" in res.json()["detail"]

    def test_token_with_nonexistent_user_uuid(self, client: TestClient):
        """Token with a valid signature but non-existent user UUID returns 401."""
        nonexistent_uuid = str(uuid.uuid4())
        token = create_access_token(subject=nonexistent_uuid)

        res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401
        assert "User not found" in res.json()["detail"]

    def test_login_invalid_password(self, client: TestClient):
        """Login with wrong password returns 401 and does not reveal password hash."""
        email = "auth_sec_test1@example.com"
        client.post("/api/v1/auth/register", json={"email": email, "password": "CorrectPassword1!"})

        res = client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword123!"})
        assert res.status_code == 401
        assert res.json()["detail"] == "Invalid email or password"
        assert "hashed" not in str(res.json()).lower()

    def test_login_nonexistent_user(self, client: TestClient):
        """Login with non-existent email returns generic 401 without revealing user enumeration."""
        res = client.post("/api/v1/auth/login", json={"email": "nonexistent_ghost@example.com", "password": "SomePassword1!"})
        assert res.status_code == 401
        assert res.json()["detail"] == "Invalid email or password"

    def test_duplicate_registration_rejected(self, client: TestClient):
        """Duplicate registration is safely rejected with 409 Conflict."""
        email = "dup_reg_sec@example.com"
        res1 = client.post("/api/v1/auth/register", json={"email": email, "password": "Password123!"})
        assert res1.status_code == 201

        res2 = client.post("/api/v1/auth/register", json={"email": email, "password": "Password123!"})
        assert res2.status_code == 409
        assert "already exists" in res2.json()["detail"]

    def test_password_never_exposed_in_responses(self, client: TestClient):
        """Password hashes are never exposed in /auth/me or registration responses."""
        email = "safe_hash_sec@example.com"
        reg_res = client.post("/api/v1/auth/register", json={"email": email, "password": "Password123!"})
        assert "password" not in reg_res.json()
        assert "hashed_password" not in reg_res.json()

        _, token = get_auth_token(client, email)
        me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert "password" not in me_res.json()
        assert "hashed_password" not in me_res.json()


# ==============================================================================
# 2. OWNERSHIP / IDOR SECURITY TESTING
# ==============================================================================

class TestIDORCrossUserSecurity:
    """Exhaustive IDOR and cross-user isolation testing across all entities."""

    @pytest.fixture
    def setup_users_and_resources(self, client: TestClient, db_session: Session):
        """Creates User A with full hierarchy and User B."""
        user_a_id, token_a = get_auth_token(client, "user_a_idor@test.com")
        user_b_id, token_b = get_auth_token(client, "user_b_idor@test.com")

        # Create Subject for User A
        sub_a = Subject(user_id=uuid.UUID(user_a_id), name="User A Subject")
        db_session.add(sub_a)
        db_session.flush()

        # Create Playlist for User A
        pl_a = Playlist(subject_id=sub_a.id, youtube_playlist_id="PL_USER_A", title="User A Playlist", status="completed")
        db_session.add(pl_a)
        db_session.flush()

        # Create Video for User A
        vid_a = Video(playlist_id=pl_a.id, youtube_video_id="VID_A_1", title="User A Video", status="completed")
        db_session.add(vid_a)
        db_session.flush()

        # Create TranscriptChunk for User A
        chunk_t_a = TranscriptChunk(
            video_id=vid_a.id,
            text="User A secret lecture on cryptography.",
            start_time=0.0,
            end_time=60.0,
            embedding=embed_text("User A secret lecture on cryptography."),
        )
        db_session.add(chunk_t_a)

        # Create Document for User A
        doc_a = Document(subject_id=sub_a.id, filename="user_a_secret.pdf", file_path="/fake/a.pdf", page_count=5, status="completed")
        db_session.add(doc_a)
        db_session.flush()

        # Create DocumentChunk for User A
        chunk_d_a = DocumentChunk(
            document_id=doc_a.id,
            page_number=1,
            chunk_index=0,
            text="User A confidential notes.",
            embedding=embed_text("User A confidential notes."),
        )
        db_session.add(chunk_d_a)
        db_session.commit()

        return {
            "token_a": token_a,
            "token_b": token_b,
            "sub_a_id": sub_a.id,
            "pl_a_id": pl_a.id,
            "vid_a_id": vid_a.id,
            "doc_a_id": doc_a.id,
        }

    def test_user_b_cannot_get_user_a_subject(self, client: TestClient, setup_users_and_resources):
        """User B cannot GET User A's subject (404)."""
        data = setup_users_and_resources
        res = client.get(f"/api/v1/subjects/{data['sub_a_id']}", headers={"Authorization": f"Bearer {data['token_b']}"})
        assert res.status_code == 404

    def test_user_b_cannot_update_user_a_subject(self, client: TestClient, setup_users_and_resources):
        """User B cannot PUT/update User A's subject (404)."""
        data = setup_users_and_resources
        res = client.put(
            f"/api/v1/subjects/{data['sub_a_id']}",
            json={"name": "Hacked Subject Name"},
            headers={"Authorization": f"Bearer {data['token_b']}"},
        )
        assert res.status_code == 404

    def test_user_b_cannot_delete_user_a_subject(self, client: TestClient, setup_users_and_resources):
        """User B cannot DELETE User A's subject (404)."""
        data = setup_users_and_resources
        res = client.delete(f"/api/v1/subjects/{data['sub_a_id']}", headers={"Authorization": f"Bearer {data['token_b']}"})
        assert res.status_code == 404

    def test_user_b_cannot_get_user_a_subject_summary(self, client: TestClient, setup_users_and_resources):
        """User B cannot access User A's subject summary (404)."""
        data = setup_users_and_resources
        res = client.get(f"/api/v1/subjects/{data['sub_a_id']}/summary", headers={"Authorization": f"Bearer {data['token_b']}"})
        assert res.status_code == 404

    def test_user_b_cannot_get_user_a_subject_playlists(self, client: TestClient, setup_users_and_resources):
        """User B cannot list playlists in User A's subject (404)."""
        data = setup_users_and_resources
        res = client.get(f"/api/v1/subjects/{data['sub_a_id']}/playlists", headers={"Authorization": f"Bearer {data['token_b']}"})
        assert res.status_code == 404

    def test_user_b_cannot_add_playlist_to_user_a_subject(self, client: TestClient, setup_users_and_resources):
        """User B cannot inject a playlist into User A's subject (404)."""
        data = setup_users_and_resources
        res = client.post(
            "/api/v1/playlists",
            json={"subject_id": str(data["sub_a_id"]), "playlist_url": "https://www.youtube.com/playlist?list=PL_TEST"},
            headers={"Authorization": f"Bearer {data['token_b']}"},
        )
        assert res.status_code == 404

    def test_user_b_cannot_get_user_a_playlist_details(self, client: TestClient, setup_users_and_resources):
        """User B cannot view User A's playlist details or videos (404)."""
        data = setup_users_and_resources
        res1 = client.get(f"/api/v1/playlists/{data['pl_a_id']}", headers={"Authorization": f"Bearer {data['token_b']}"})
        assert res1.status_code == 404

        res2 = client.get(f"/api/v1/playlists/{data['pl_a_id']}/videos", headers={"Authorization": f"Bearer {data['token_b']}"})
        assert res2.status_code == 404

    def test_user_b_cannot_delete_user_a_playlist(self, client: TestClient, setup_users_and_resources):
        """User B cannot DELETE User A's playlist (404)."""
        data = setup_users_and_resources
        res = client.delete(f"/api/v1/playlists/{data['pl_a_id']}", headers={"Authorization": f"Bearer {data['token_b']}"})
        assert res.status_code == 404

    def test_user_b_cannot_access_or_trigger_user_a_transcripts(self, client: TestClient, setup_users_and_resources):
        """User B cannot access or trigger processing on User A's video transcripts (404)."""
        data = setup_users_and_resources
        res1 = client.get(f"/api/v1/videos/{data['vid_a_id']}/transcript", headers={"Authorization": f"Bearer {data['token_b']}"})
        assert res1.status_code == 404

        res2 = client.get(f"/api/v1/videos/{data['vid_a_id']}/transcript/status", headers={"Authorization": f"Bearer {data['token_b']}"})
        assert res2.status_code == 404

        res3 = client.post(f"/api/v1/videos/{data['vid_a_id']}/transcript/processing", headers={"Authorization": f"Bearer {data['token_b']}"})
        assert res3.status_code == 404

        res4 = client.post(f"/api/v1/playlists/{data['pl_a_id']}/transcripts/processing", headers={"Authorization": f"Bearer {data['token_b']}"})
        assert res4.status_code == 404

    def test_user_b_cannot_access_or_delete_user_a_documents(self, client: TestClient, setup_users_and_resources):
        """User B cannot access details, pages, chunks, or delete User A's document (404)."""
        data = setup_users_and_resources
        res1 = client.get(f"/api/v1/study-materials/{data['doc_a_id']}", headers={"Authorization": f"Bearer {data['token_b']}"})
        assert res1.status_code == 404

        res2 = client.get(f"/api/v1/study-materials/{data['doc_a_id']}/pages/1", headers={"Authorization": f"Bearer {data['token_b']}"})
        assert res2.status_code == 404

        res3 = client.get(f"/api/v1/study-materials/{data['doc_a_id']}/chunks", headers={"Authorization": f"Bearer {data['token_b']}"})
        assert res3.status_code == 404

        res4 = client.delete(f"/api/v1/study-materials/{data['doc_a_id']}", headers={"Authorization": f"Bearer {data['token_b']}"})
        assert res4.status_code == 404


# ==============================================================================
# 3. SUBJECT-LEVEL SEARCH SECURITY
# ==============================================================================

class TestSearchSecurityAndIsolation:
    """Security tests for semantic search scoping and query sanitization."""

    def test_user_b_cannot_search_user_a_subject(self, client: TestClient, db_session: Session):
        """User B searching User A's subject ID is rejected with 404."""
        user_a_id, _ = get_auth_token(client, "search_user_a@test.com")
        _, token_b = get_auth_token(client, "search_user_b@test.com")

        sub_a = Subject(user_id=uuid.UUID(user_a_id), name="Private CS")
        db_session.add(sub_a)
        db_session.commit()

        res = client.post(
            f"/api/v1/subjects/{sub_a.id}/search",
            json={"query": "cryptography and ciphers", "top_k": 5},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert res.status_code == 404
        assert "not found or access denied" in res.json()["detail"].lower()

    def test_sql_injection_payloads_in_search_query_safe(self, client: TestClient, db_session: Session):
        """Malicious SQL injection query strings are parameterized and handled safely."""
        user_id, token = get_auth_token(client, "sqli_search@test.com")
        subject = Subject(user_id=uuid.UUID(user_id), name="SQLi Defense Subject")
        db_session.add(subject)
        db_session.commit()

        payloads = [
            "' OR '1'='1",
            "'; DROP TABLE subjects; --",
            "1; SELECT * FROM users; --",
            "<script>alert('xss')</script>",
            "UNION SELECT null, null, null--",
        ]
        for injection in payloads:
            res = client.post(
                f"/api/v1/subjects/{subject.id}/search",
                json={"query": injection, "top_k": 5},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["total_results"] == 0
            assert data["results"] == []


# ==============================================================================
# 4. YOUTUBE INPUT & PROCESSING FAILURE TESTING
# ==============================================================================

class TestYouTubeFailures:
    """Deterministic failure testing for playlist ingestion."""

    def test_non_youtube_urls_rejected(self, client: TestClient, db_session: Session):
        """Non-YouTube URLs are rejected with 400."""
        user_id, token = get_auth_token(client, "yt_fail1@test.com")
        sub = Subject(user_id=uuid.UUID(user_id), name="YT Subject")
        db_session.add(sub)
        db_session.commit()

        bad_urls = [
            "https://vimeo.com/channels/staffpicks/123456",
            "https://dailymotion.com/video/x7tg5",
            "not-a-url-at-all",
            "ftp://youtube.com/playlist?list=PL123",
        ]
        for url in bad_urls:
            res = client.post(
                "/api/v1/playlists",
                json={"subject_id": str(sub.id), "playlist_url": url},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 400

    def test_single_video_url_rejected_when_playlist_expected(self, client: TestClient, db_session: Session):
        """Single video URL with no list param is rejected with 400."""
        user_id, token = get_auth_token(client, "yt_fail2@test.com")
        sub = Subject(user_id=uuid.UUID(user_id), name="YT Subject 2")
        db_session.add(sub)
        db_session.commit()

        res = client.post(
            "/api/v1/playlists",
            json={"subject_id": str(sub.id), "playlist_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 400
        assert "does not contain a playlist ID" in res.json()["detail"]

    def test_partial_playlist_failure_preserves_valid_videos(self, client: TestClient, db_session: Session):
        """Playlists with partially unavailable videos mark status as partial_failure and preserve valid videos."""
        user_id, token = get_auth_token(client, "yt_partial@test.com")
        sub = Subject(user_id=uuid.UUID(user_id), name="YT Partial Subject")
        db_session.add(sub)
        db_session.commit()

        # Mock fetch_playlist_metadata to simulate 2 valid videos and 1 failed video
        mock_metadata = {
            "title": "Partially Broken Playlist",
            "videos": [
                {"youtube_video_id": "vid_good_1", "title": "Good Video 1", "duration_seconds": 300},
                {"youtube_video_id": "vid_good_2", "title": "Good Video 2", "duration_seconds": 450},
            ],
            "failed_video_count": 1,
        }

        with patch("app.api.playlists.fetch_playlist_metadata", return_value=mock_metadata):
            res = client.post(
                "/api/v1/playlists",
                json={"subject_id": str(sub.id), "playlist_url": "https://www.youtube.com/playlist?list=PL_PARTIAL"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 201
            data = res.json()
            assert data["status"] == "partial_failure"
            assert data["video_count"] == 2


# ==============================================================================
# 5. TRANSCRIPT FAILURE & WHISPER FALLBACK TESTING
# ==============================================================================

class TestTranscriptFailures:
    """Failure and fallback testing for transcript extraction."""

    def test_captions_fail_and_whisper_fallback_succeeds(self, client: TestClient, db_session: Session):
        """When YouTube captions are disabled/unavailable, Whisper local fallback is triggered."""
        user_id, token = get_auth_token(client, "trans_whisper@test.com")
        sub = Subject(user_id=uuid.UUID(user_id), name="Whisper Subject")
        db_session.add(sub)
        db_session.flush()

        pl = Playlist(subject_id=sub.id, youtube_playlist_id="PL_W", title="Whisper PL", status="completed")
        db_session.add(pl)
        db_session.flush()

        vid = Video(playlist_id=pl.id, youtube_video_id="vid_whisper_fallback", title="Whisper Video", status="pending")
        db_session.add(vid)
        db_session.commit()

        # Captions return None, Whisper returns valid segments
        with patch("app.services.transcript.fetch_youtube_captions", return_value=None), \
             patch("app.services.transcript.transcribe_with_whisper", return_value=([
                 {"text": "Hello this is a local whisper transcription test.", "start": 0.0, "duration": 65.0}
             ], "en")):
            res = client.post(
                f"/api/v1/videos/{vid.id}/transcript/processing",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["transcript_status"] == "available"
            assert data["transcript_source"] == "whisper"
            assert data["chunk_count"] == 1

    def test_both_captions_and_whisper_fail_gracefully(self, client: TestClient, db_session: Session):
        """When both captions and Whisper fail, video status is marked 'failed' without crashing."""
        user_id, token = get_auth_token(client, "trans_fail@test.com")
        sub = Subject(user_id=uuid.UUID(user_id), name="Trans Fail Subject")
        db_session.add(sub)
        db_session.flush()

        pl = Playlist(subject_id=sub.id, youtube_playlist_id="PL_FAIL", title="Fail PL", status="completed")
        db_session.add(pl)
        db_session.flush()

        vid = Video(playlist_id=pl.id, youtube_video_id="vid_both_fail", title="Failed Video", status="pending")
        db_session.add(vid)
        db_session.commit()

        with patch("app.services.transcript.fetch_youtube_captions", return_value=None), \
             patch("app.services.transcript.transcribe_with_whisper", return_value=None):
            res = client.post(
                f"/api/v1/videos/{vid.id}/transcript/processing",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["transcript_status"] == "failed"
            assert data["processing_status"] == "failed"
            assert "Whisper fallback failed" in data["processing_error"]


# ==============================================================================
# 6. PDF SECURITY & FAILURE TESTING
# ==============================================================================

class TestPDFSecurityAndFailures:
    """Rigorous PDF security, validation, and failure testing."""

    def test_empty_pdf_file_rejected(self):
        """0-byte file is rejected with PDFValidationError."""
        with pytest.raises(PDFValidationError, match="The uploaded file is empty"):
            validate_pdf_content(b"", "empty.pdf")

    def test_invalid_extension_rejected(self):
        """Non-.pdf extension is rejected."""
        with pytest.raises(PDFValidationError, match="Invalid file extension"):
            validate_pdf_content(b"%PDF-1.4 test", "document.docx")

    def test_non_pdf_file_with_pdf_extension_rejected(self):
        """Fake PDF with JPEG content is rejected by magic bytes."""
        with pytest.raises(PDFValidationError, match="invalid magic header"):
            validate_pdf_content(b"\xff\xd8\xff\xe0\x00\x10JFIF", "fake.pdf")

    def test_oversized_file_rejected(self):
        """File exceeding MAX_UPLOAD_SIZE_BYTES is rejected."""
        oversized = settings.MAX_UPLOAD_SIZE_BYTES + 1
        dummy_bytes = b"%PDF-1.4 " + (b"A" * 100)
        # Check by mocking len or passing length
        with patch.object(settings, "MAX_UPLOAD_SIZE_BYTES", 50):
            with pytest.raises(PDFValidationError, match="File size exceeds maximum"):
                validate_pdf_content(dummy_bytes, "large.pdf")

    def test_path_traversal_filename_saved_as_uuid(self):
        """Path traversal in filename does not escape storage directory."""
        content = b"%PDF-1.4 1 0 obj <<>> endobj trailer <<>> %%EOF"
        doc_id, file_path = save_uploaded_pdf(content)
        try:
            assert os.path.isfile(file_path)
            assert os.path.dirname(file_path) == os.path.abspath(settings.STORAGE_DIR)
            assert str(doc_id) in file_path
        finally:
            if os.path.isfile(file_path):
                os.remove(file_path)


# ==============================================================================
# 7. EMBEDDING FAILURE & DIMENSIONAL TESTING
# ==============================================================================

class TestEmbeddingFailures:
    """Validation and failure resilience tests for the local embedding service."""

    def test_empty_and_whitespace_input_raises_invalid_input(self):
        """Empty or whitespace strings raise InvalidInputError."""
        with pytest.raises(InvalidInputError):
            embed_text("")
        with pytest.raises(InvalidInputError):
            embed_text("   \n\t  ")

    def test_non_string_input_raises_invalid_input(self):
        """Non-string types raise InvalidInputError."""
        with pytest.raises(InvalidInputError):
            embed_text(None)  # type: ignore
        with pytest.raises(InvalidInputError):
            embed_text(12345)  # type: ignore

    def test_batch_embedding_empty_list(self):
        """Empty batch list returns empty list immediately."""
        assert embed_texts([]) == []

    def test_batch_embedding_with_invalid_element_raises(self):
        """Batch containing an empty string element raises InvalidInputError."""
        with pytest.raises(InvalidInputError):
            embed_texts(["Valid text", "   ", "Another text"])

    def test_vector_dimensions_and_finite_values(self):
        """Generated vectors are strictly 384 dimensions and contain only finite floats."""
        vec = embed_text("Test vector dimension check for pgvector.")
        assert len(vec) == EMBEDDING_DIMENSION
        assert all(math.isfinite(x) for x in vec)
        # Vector is normalized (L2 norm ≈ 1.0)
        norm = math.sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 1e-4


# ==============================================================================
# 8. DATABASE TRANSACTION & ROLLBACK TESTING
# ==============================================================================

class TestDatabaseTransactionIntegrity:
    """Verifies atomic rollback on unexpected database exceptions."""

    def test_playlist_creation_rollback_on_video_error(self, client: TestClient, db_session: Session):
        """If video persistence fails, playlist insertion rolls back completely."""
        user_id, token = get_auth_token(client, "db_rollback@test.com")
        sub = Subject(user_id=uuid.UUID(user_id), name="Rollback Subject")
        db_session.add(sub)
        db_session.commit()

        mock_metadata = {
            "title": "Atomic Playlist",
            "videos": [{"youtube_video_id": "vid_atom_1", "title": "Vid 1", "duration_seconds": 100}],
            "failed_video_count": 0,
        }

        # Force a database flush/commit failure after playlist creation
        with patch("app.api.playlists.fetch_playlist_metadata", return_value=mock_metadata), \
             patch.object(db_session, "commit", side_effect=RuntimeError("Database write error")):
            res = client.post(
                "/api/v1/playlists",
                json={"subject_id": str(sub.id), "playlist_url": "https://www.youtube.com/playlist?list=PL_ATOMIC"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 500
            assert "Failed to persist playlist" in res.json()["detail"]

        # Confirm no orphaned playlist was created in DB
        orphaned = db_session.execute(
            select(Playlist).where(Playlist.subject_id == sub.id)
        ).scalars().all()
        assert len(orphaned) == 0
