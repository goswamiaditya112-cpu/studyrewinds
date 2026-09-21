"""
Phase 9 - Semantic Search API Tests
Tests semantic retrieval across YouTube transcript chunks and PDF document chunks.
Verifies source provenance, similarity scoring, input validation,
strict cross-user isolation, top_k capping, error handling, and dual prefix routing.
"""

import uuid
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.subject import Subject
from app.models.playlist import Playlist
from app.models.video import Video
from app.models.document import Document
from app.models.chunk import TranscriptChunk, DocumentChunk
from app.services.embedding import embed_text


def register_and_login(client: TestClient, email: str, password: str = "Password123!") -> tuple[dict, str]:
    """Helper to register and login a user."""
    client.post("/api/auth/register", json={"email": email, "password": password})
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    token = res.json()["access_token"]
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    return me_res.json(), token


def create_user_subject(db: Session, email: str, subject_name: str = "Computer Science") -> tuple[User, Subject]:
    """Helper to create a user and subject directly via DB session."""
    user = User(email=email, hashed_password="hashed_pw_test")
    db.add(user)
    db.flush()

    subject = Subject(user_id=user.id, name=subject_name)
    db.add(subject)
    db.flush()
    return user, subject


class TestSemanticSearchValidation:
    """Tests input validation and authentication for semantic search endpoint."""

    def test_search_unauthenticated_rejected(self, client: TestClient):
        """Unauthenticated requests must be rejected with 401."""
        random_id = uuid.uuid4()
        res = client.post(
            f"/api/v1/subjects/{random_id}/search",
            json={"query": "test query", "top_k": 5},
        )
        assert res.status_code == 401

    def test_search_nonexistent_subject_returns_404(self, client: TestClient):
        """Searching a subject that does not exist returns 404."""
        _, token = register_and_login(client, "user_nonexistent@example.com")
        random_id = uuid.uuid4()
        res = client.post(
            f"/api/v1/subjects/{random_id}/search",
            json={"query": "test query", "top_k": 5},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 404
        assert "not found or access denied" in res.json()["detail"].lower()

    def test_search_unowned_subject_returns_404(self, client: TestClient, db_session: Session):
        """User A searching User B's subject returns 404 (IDOR protection)."""
        # User A logs in via API
        _, token_a = register_and_login(client, "usera_idor@example.com")

        # User B created in DB with a subject
        _, subject_b = create_user_subject(db_session, "userb_idor@example.com", "User B Private Subject")
        db_session.commit()

        res = client.post(
            f"/api/v1/subjects/{subject_b.id}/search",
            json={"query": "operating systems", "top_k": 5},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert res.status_code == 404
        assert "not found or access denied" in res.json()["detail"].lower()

    def test_search_validation_empty_query(self, client: TestClient, db_session: Session):
        """Empty query string fails with 422."""
        user_info, token = register_and_login(client, "val_user1@example.com")
        subject = Subject(user_id=uuid.UUID(user_info["id"]), name="Validations")
        db_session.add(subject)
        db_session.commit()

        res = client.post(
            f"/api/v1/subjects/{subject.id}/search",
            json={"query": "", "top_k": 5},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 422

    def test_search_validation_whitespace_query(self, client: TestClient, db_session: Session):
        """Whitespace-only query string fails with 422."""
        user_info, token = register_and_login(client, "val_user2@example.com")
        subject = Subject(user_id=uuid.UUID(user_info["id"]), name="Validations")
        db_session.add(subject)
        db_session.commit()

        res = client.post(
            f"/api/v1/subjects/{subject.id}/search",
            json={"query": "    ", "top_k": 5},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 422

    def test_search_validation_invalid_top_k(self, client: TestClient, db_session: Session):
        """top_k < 1 or top_k > 50 fails with 422."""
        user_info, token = register_and_login(client, "val_user3@example.com")
        subject = Subject(user_id=uuid.UUID(user_info["id"]), name="Validations")
        db_session.add(subject)
        db_session.commit()

        # top_k = 0
        res0 = client.post(
            f"/api/v1/subjects/{subject.id}/search",
            json={"query": "test", "top_k": 0},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res0.status_code == 422

        # top_k = 51
        res51 = client.post(
            f"/api/v1/subjects/{subject.id}/search",
            json={"query": "test", "top_k": 51},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res51.status_code == 422


class TestSemanticSearchExecution:
    """Tests semantic search retrieval, scoring, provenance, and isolation."""

    def test_search_empty_subject_returns_empty_results(self, client: TestClient, db_session: Session):
        """An owned subject with no chunks returns 200 with total_results = 0."""
        user_info, token = register_and_login(client, "empty_search@example.com")
        subject = Subject(user_id=uuid.UUID(user_info["id"]), name="Empty Subject")
        db_session.add(subject)
        db_session.commit()

        res = client.post(
            f"/api/v1/subjects/{subject.id}/search",
            json={"query": "anything", "top_k": 5},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["query"] == "anything"
        assert data["subject_id"] == str(subject.id)
        assert data["total_results"] == 0
        assert data["results"] == []

    def test_search_youtube_transcript_provenance(self, client: TestClient, db_session: Session):
        """Verifies YouTube chunk retrieval with complete provenance metadata."""
        user_info, token = register_and_login(client, "yt_user@example.com")
        user_id = uuid.UUID(user_info["id"])

        # Setup hierarchy
        subject = Subject(user_id=user_id, name="Operating Systems")
        db_session.add(subject)
        db_session.flush()

        playlist = Playlist(subject_id=subject.id, youtube_playlist_id="PL_OS_1", title="OS Lectures")
        db_session.add(playlist)
        db_session.flush()

        video = Video(playlist_id=playlist.id, youtube_video_id="vid_deadlock", title="Deadlock Detection")
        db_session.add(video)
        db_session.flush()

        text_content = "A deadlock occurs when a set of processes are blocked because each process is holding a resource."
        vec = embed_text(text_content)
        chunk = TranscriptChunk(
            video_id=video.id,
            text=text_content,
            start_time=12.5,
            end_time=25.0,
            embedding=vec,
        )
        db_session.add(chunk)
        db_session.commit()

        # Query
        res = client.post(
            f"/api/v1/subjects/{subject.id}/search",
            json={"query": "What causes deadlocks in operating systems?", "top_k": 5},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total_results"] == 1
        item = data["results"][0]

        assert item["source_type"] == "youtube"
        assert item["chunk_id"] == str(chunk.id)
        assert 0.0 <= item["score"] <= 1.0
        assert item["score"] > 0.5  # Semantically highly relevant

        # Video metadata
        assert item["video"]["id"] == str(video.id)
        assert item["video"]["youtube_video_id"] == "vid_deadlock"
        assert item["video"]["title"] == "Deadlock Detection"

        # Transcript metadata
        assert item["transcript"]["text"] == text_content
        assert item["transcript"]["start_time"] == 12.5
        assert item["transcript"]["end_time"] == 25.0

    def test_search_pdf_document_provenance(self, client: TestClient, db_session: Session):
        """Verifies PDF document chunk retrieval with complete provenance metadata."""
        user_info, token = register_and_login(client, "pdf_user@example.com")
        user_id = uuid.UUID(user_info["id"])

        subject = Subject(user_id=user_id, name="Software Engineering")
        db_session.add(subject)
        db_session.flush()

        doc = Document(
            subject_id=subject.id,
            filename="uml_diagrams.pdf",
            file_path="/storage/uml_diagrams.pdf",
            page_count=10,
            status="completed",
        )
        db_session.add(doc)
        db_session.flush()

        doc_text = "Unified Modeling Language includes class diagrams, sequence diagrams, and use case diagrams."
        vec = embed_text(doc_text)
        chunk = DocumentChunk(
            document_id=doc.id,
            page_number=4,
            chunk_index=2,
            text=doc_text,
            embedding=vec,
        )
        db_session.add(chunk)
        db_session.commit()

        res = client.post(
            f"/api/v1/subjects/{subject.id}/search",
            json={"query": "What types of UML diagrams exist?", "top_k": 5},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total_results"] == 1
        item = data["results"][0]

        assert item["source_type"] == "pdf"
        assert item["chunk_id"] == str(chunk.id)
        assert 0.0 <= item["score"] <= 1.0
        assert item["score"] > 0.5

        # Document provenance
        assert item["document"]["id"] == str(doc.id)
        assert item["document"]["filename"] == "uml_diagrams.pdf"
        assert item["page_number"] == 4
        assert item["chunk_index"] == 2
        assert item["text"] == doc_text

    def test_search_mixed_sources_ranking_and_top_k(self, client: TestClient, db_session: Session):
        """Verifies mixed YouTube and PDF results ranked strictly by score descending."""
        user_info, token = register_and_login(client, "mixed_user@example.com")
        user_id = uuid.UUID(user_info["id"])

        subject = Subject(user_id=user_id, name="Database Systems")
        db_session.add(subject)
        db_session.flush()

        playlist = Playlist(subject_id=subject.id, youtube_playlist_id="PL_DB", title="DB Course")
        db_session.add(playlist)
        db_session.flush()

        video = Video(playlist_id=playlist.id, youtube_video_id="vid_db", title="Relational Normalization")
        db_session.add(video)
        db_session.flush()

        doc = Document(
            subject_id=subject.id,
            filename="db_notes.pdf",
            file_path="/storage/db_notes.pdf",
            page_count=8,
            status="completed",
        )
        db_session.add(doc)
        db_session.flush()

        # Chunk 1: highly relevant PDF chunk (Boyce-Codd Normal Form)
        text1 = "Boyce-Codd Normal Form BCNF requires that for every functional dependency X to Y, X must be a superkey."
        chunk1 = DocumentChunk(
            document_id=doc.id, page_number=3, chunk_index=0, text=text1,
            embedding=embed_text(text1),
        )

        # Chunk 2: moderately relevant YouTube chunk (Relational tables)
        text2 = "In relational databases, data is organized into tables of rows and columns with primary keys."
        chunk2 = TranscriptChunk(
            video_id=video.id, text=text2, start_time=0.0, end_time=15.0,
            embedding=embed_text(text2),
        )

        # Chunk 3: irrelevant PDF chunk (Hardware registers)
        text3 = "Instruction pipeline hazards can be resolved using hardware branch predictors and operand forwarding."
        chunk3 = DocumentChunk(
            document_id=doc.id, page_number=7, chunk_index=1, text=text3,
            embedding=embed_text(text3),
        )

        db_session.add_all([chunk1, chunk2, chunk3])
        db_session.commit()

        # Query specifically for BCNF normalization
        res = client.post(
            f"/api/v1/subjects/{subject.id}/search",
            json={"query": "What is Boyce-Codd Normal Form BCNF in relational schemas?", "top_k": 2},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total_results"] == 2  # capped by top_k = 2

        results = data["results"]
        # Highest score should be the BCNF document chunk
        assert results[0]["source_type"] == "pdf"
        assert results[0]["chunk_id"] == str(chunk1.id)
        assert results[0]["score"] >= results[1]["score"]

        # All scores must be descending
        for i in range(len(results) - 1):
            assert results[i]["score"] >= results[i + 1]["score"]

    def test_search_strict_cross_user_isolation(self, client: TestClient, db_session: Session):
        """
        User A searching Subject A NEVER retrieves chunks from User B's subject,
        even if User B's chunks have identical or higher semantic match.
        """
        user_a_info, token_a = register_and_login(client, "isolated_a@example.com")
        user_b_info, token_b = register_and_login(client, "isolated_b@example.com")

        # Subject A for User A
        sub_a = Subject(user_id=uuid.UUID(user_a_info["id"]), name="User A Subject")
        db_session.add(sub_a)
        db_session.flush()

        doc_a = Document(subject_id=sub_a.id, filename="user_a_doc.pdf", file_path="/p/a.pdf", page_count=1, status="completed")
        db_session.add(doc_a)
        db_session.flush()

        text_a = "User A notes on Operating System Process Scheduling Algorithms."
        chunk_a = DocumentChunk(
            document_id=doc_a.id, page_number=1, chunk_index=0, text=text_a,
            embedding=embed_text(text_a),
        )
        db_session.add(chunk_a)

        # Subject B for User B
        sub_b = Subject(user_id=uuid.UUID(user_b_info["id"]), name="User B Subject")
        db_session.add(sub_b)
        db_session.flush()

        doc_b = Document(subject_id=sub_b.id, filename="user_b_doc.pdf", file_path="/p/b.pdf", page_count=1, status="completed")
        db_session.add(doc_b)
        db_session.flush()

        # Text B is identical to search query
        query_text = "Operating System Process Scheduling Algorithms"
        chunk_b = DocumentChunk(
            document_id=doc_b.id, page_number=1, chunk_index=0, text=query_text,
            embedding=embed_text(query_text),
        )
        db_session.add(chunk_b)
        db_session.commit()

        # User A searches User A's subject
        res_a = client.post(
            f"/api/v1/subjects/{sub_a.id}/search",
            json={"query": query_text, "top_k": 10},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert res_a.status_code == 200
        data_a = res_a.json()

        retrieved_ids_a = [item["chunk_id"] for item in data_a["results"]]
        assert str(chunk_a.id) in retrieved_ids_a
        assert str(chunk_b.id) not in retrieved_ids_a  # User B's chunk MUST NOT appear!

        # User B searches User B's subject
        res_b = client.post(
            f"/api/v1/subjects/{sub_b.id}/search",
            json={"query": query_text, "top_k": 10},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert res_b.status_code == 200
        data_b = res_b.json()

        retrieved_ids_b = [item["chunk_id"] for item in data_b["results"]]
        assert str(chunk_b.id) in retrieved_ids_b
        assert str(chunk_a.id) not in retrieved_ids_b  # User A's chunk MUST NOT appear!

    def test_search_dual_prefix_compatibility(self, client: TestClient, db_session: Session):
        """Verifies both /api and /api/v1 prefixes function identically."""
        user_info, token = register_and_login(client, "prefix_user@example.com")
        subject = Subject(user_id=uuid.UUID(user_info["id"]), name="Dual Prefix")
        db_session.add(subject)
        db_session.commit()

        # /api/v1/...
        res_v1 = client.post(
            f"/api/v1/subjects/{subject.id}/search",
            json={"query": "test query", "top_k": 5},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_v1.status_code == 200

        # /api/...
        res_legacy = client.post(
            f"/api/subjects/{subject.id}/search",
            json={"query": "test query", "top_k": 5},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_legacy.status_code == 200
        assert res_v1.json() == res_legacy.json()


class TestSemanticSearchErrorHandling:
    """Tests error handling for internal embedding failures or database errors."""

    def test_embedding_generation_failure_returns_500(self, client: TestClient, db_session: Session):
        """When embedding generation fails, API returns clean 500 error."""
        user_info, token = register_and_login(client, "embed_fail@example.com")
        subject = Subject(user_id=uuid.UUID(user_info["id"]), name="Fail Subject")
        db_session.add(subject)
        db_session.commit()

        with patch("app.services.search.embed_text", side_effect=RuntimeError("Model crashed")):
            res = client.post(
                f"/api/v1/subjects/{subject.id}/search",
                json={"query": "anything", "top_k": 5},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 500
            assert "Failed to generate query embedding" in res.json()["detail"]

    def test_database_vector_query_failure_returns_500(self, client: TestClient, db_session: Session):
        """When database vector query raises an error, API returns clean 500."""
        user_info, token = register_and_login(client, "db_fail@example.com")
        subject = Subject(user_id=uuid.UUID(user_info["id"]), name="DB Fail Subject")
        db_session.add(subject)
        db_session.commit()

        # Mock db.execute to fail on the vector query
        original_execute = db_session.execute

        def mock_execute(stmt, *args, **kwargs):
            stmt_str = str(stmt).lower()
            if "transcript_chunks" in stmt_str or "document_chunks" in stmt_str:
                raise RuntimeError("pgvector index corrupted")
            return original_execute(stmt, *args, **kwargs)

        with patch.object(db_session, "execute", side_effect=mock_execute):
            res = client.post(
                f"/api/v1/subjects/{subject.id}/search",
                json={"query": "anything", "top_k": 5},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 500
            assert "Database vector search failed" in res.json()["detail"]


class TestSemanticSearchBugFix:
    """Regression tests for the un-embedded chunks and response contract bug."""

    def test_search_self_heals_unembedded_chunks(self, client: TestClient, db_session: Session):
        """
        When chunks have placeholder zero embeddings [0.0]*384, search_subject
        self-heals them by embedding them via Phase 8 vector storage rather than
        producing NaN cosine distance and returning empty results.
        """
        user_info, token = register_and_login(client, "heal_user@example.com")
        user_id = uuid.UUID(user_info["id"])
        subject = Subject(user_id=user_id, name="Self Healing Systems")
        db_session.add(subject)
        db_session.flush()

        playlist = Playlist(subject_id=subject.id, title="OS Course", youtube_playlist_id="PL1")
        db_session.add(playlist)
        db_session.flush()

        video = Video(playlist_id=playlist.id, youtube_video_id="vid_heal", title="Processes and Threads")
        db_session.add(video)
        db_session.flush()

        # Insert chunks with legacy zero embeddings
        t_chunk = TranscriptChunk(
            video_id=video.id,
            start_time=10.0,
            end_time=70.0,
            text="Operating system manages processes, CPU scheduling, and memory.",
            embedding=[0.0] * 384,
        )
        db_session.add(t_chunk)

        doc = Document(subject_id=subject.id, filename="OS_Notes.pdf", file_path="/tmp/fake.pdf", page_count=1)
        db_session.add(doc)
        db_session.flush()

        d_chunk = DocumentChunk(
            document_id=doc.id,
            page_number=1,
            chunk_index=0,
            text="Deadlock avoidance requires algorithms like Banker's algorithm in operating systems.",
            embedding=[0.0] * 384,
        )
        db_session.add(d_chunk)
        db_session.commit()

        # Search should self-heal and return results, NOT 0 results
        res = client.post(
            f"/api/v1/subjects/{subject.id}/search",
            json={"query": "What is an operating system and process scheduling?", "top_k": 5},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total_results"] > 0
        assert len(data["results"]) > 0

        # Verify chunks now have valid, non-zero embeddings in DB
        db_session.refresh(t_chunk)
        db_session.refresh(d_chunk)
        assert sum(x * x for x in t_chunk.embedding) > 0.1
        assert sum(x * x for x in d_chunk.embedding) > 0.1

    def test_search_response_shape_contract(self, client: TestClient, db_session: Session):
        """
        Guarantees backend search response structure matches frontend SearchResponse
        contract (query, subject_id, total_results, results).
        """
        user_info, token = register_and_login(client, "contract_user@example.com")
        user_id = uuid.UUID(user_info["id"])
        subject = Subject(user_id=user_id, name="Contract Validation")
        db_session.add(subject)
        db_session.commit()

        res = client.post(
            f"/api/v1/subjects/{subject.id}/search",
            json={"query": "architecture design", "top_k": 5},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()

        assert "query" in data
        assert "subject_id" in data
        assert "total_results" in data
        assert "results" in data
        assert isinstance(data["results"], list)
        assert data["total_results"] == len(data["results"])

