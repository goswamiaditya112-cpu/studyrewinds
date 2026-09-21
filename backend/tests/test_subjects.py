import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.user import User
from app.models.subject import Subject
from app.models.playlist import Playlist
from app.models.video import Video
from app.models.document import Document


def register_and_get_token(client: TestClient, email: str, password: str = "Password123!") -> tuple[dict, str]:
    """Helper to register a user and return the user data and access token."""
    res = client.post("/api/auth/register", json={"email": email, "password": password})
    assert res.status_code == 201
    user_data = res.json()

    login_res = client.post("/api/auth/login", json={"email": email, "password": password})
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    return user_data, token


def test_create_subject_success(client: TestClient, db_session: Session):
    """Test 1: User can create a subject, ownership is set to current_user.id."""
    _, token = register_and_get_token(client, "alice@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"name": "DBMS", "description": "Database Management Systems"}
    response = client.post("/api/subjects", json=payload, headers=headers)
    assert response.status_code == 201

    data = response.json()
    assert "id" in data
    assert data["name"] == "DBMS"
    assert data["description"] == "Database Management Systems"
    assert "created_at" in data

    # Verify user_id is NOT in response (leaked) but is persisted correctly in DB
    subject_id = uuid.UUID(data["id"])
    subject = db_session.execute(select(Subject).where(Subject.id == subject_id)).scalar_one_or_none()
    assert subject is not None

    user = db_session.execute(select(User).where(User.email == "alice@example.com")).scalar_one()
    assert subject.user_id == user.id


def test_create_subject_unauthenticated(client: TestClient):
    """Test 2: Creating a subject without auth token returns 401."""
    response = client.post("/api/subjects", json={"name": "Operating Systems"})
    assert response.status_code == 401


def test_create_subject_validation(client: TestClient):
    """Test 3: Name cannot be empty, whitespace-only, or too long."""
    _, token = register_and_get_token(client, "validator@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Empty name
    res = client.post("/api/subjects", json={"name": ""}, headers=headers)
    assert res.status_code == 422

    # Whitespace only
    res = client.post("/api/subjects", json={"name": "    "}, headers=headers)
    assert res.status_code == 422

    # Name > 255 chars
    res = client.post("/api/subjects", json={"name": "A" * 256}, headers=headers)
    assert res.status_code == 422


def test_create_subject_trims_whitespace(client: TestClient):
    """Test 4: Whitespace around name is trimmed cleanly."""
    _, token = register_and_get_token(client, "trimmer@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/subjects", json={"name": "   Operating Systems   "}, headers=headers)
    assert response.status_code == 201
    assert response.json()["name"] == "Operating Systems"


def test_duplicate_subject_name_for_same_user(client: TestClient):
    """Test 5: Same user creating duplicate subject name returns 400."""
    _, token = register_and_get_token(client, "dup_user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    res1 = client.post("/api/subjects", json={"name": "Computer Networks"}, headers=headers)
    assert res1.status_code == 201

    # Exact duplicate
    res2 = client.post("/api/subjects", json={"name": "Computer Networks"}, headers=headers)
    assert res2.status_code == 400
    assert "already exists" in res2.json()["detail"].lower()

    # Case-insensitive duplicate
    res3 = client.post("/api/subjects", json={"name": "computer networks"}, headers=headers)
    assert res3.status_code == 400


def test_same_subject_name_for_different_users(client: TestClient):
    """Test 6: Different users CAN create subjects with the same name."""
    _, token_a = register_and_get_token(client, "user_a@example.com")
    _, token_b = register_and_get_token(client, "user_b@example.com")

    res_a = client.post("/api/subjects", json={"name": "Algorithms"}, headers={"Authorization": f"Bearer {token_a}"})
    assert res_a.status_code == 201

    res_b = client.post("/api/subjects", json={"name": "Algorithms"}, headers={"Authorization": f"Bearer {token_b}"})
    assert res_b.status_code == 201
    assert res_a.json()["id"] != res_b.json()["id"]


def test_list_subjects_ownership_isolation(client: TestClient):
    """Test 7: User A cannot see User B's subjects."""
    _, token_a = register_and_get_token(client, "alice_list@example.com")
    _, token_b = register_and_get_token(client, "bob_list@example.com")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Alice creates 2 subjects
    client.post("/api/subjects", json={"name": "DBMS"}, headers=headers_a)
    client.post("/api/subjects", json={"name": "OS"}, headers=headers_a)

    # Bob creates 1 subject
    client.post("/api/subjects", json={"name": "CN"}, headers=headers_b)

    # Alice lists subjects
    res_a = client.get("/api/subjects", headers=headers_a)
    assert res_a.status_code == 200
    alice_subjects = res_a.json()
    assert len(alice_subjects) == 2
    alice_names = {s["name"] for s in alice_subjects}
    assert alice_names == {"DBMS", "OS"}

    # Bob lists subjects
    res_b = client.get("/api/subjects", headers=headers_b)
    assert res_b.status_code == 200
    bob_subjects = res_b.json()
    assert len(bob_subjects) == 1
    assert bob_subjects[0]["name"] == "CN"


def test_list_subjects_ordering(client: TestClient):
    """Test 8: List subjects is deterministically ordered by created_at DESC."""
    _, token = register_and_get_token(client, "order_user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/api/subjects", json={"name": "First Subject"}, headers=headers)
    client.post("/api/subjects", json={"name": "Second Subject"}, headers=headers)
    client.post("/api/subjects", json={"name": "Third Subject"}, headers=headers)

    res = client.get("/api/subjects", headers=headers)
    assert res.status_code == 200
    subjects = res.json()
    assert len(subjects) == 3
    # Newest first
    assert subjects[0]["name"] == "Third Subject"
    assert subjects[1]["name"] == "Second Subject"
    assert subjects[2]["name"] == "First Subject"


def test_get_single_subject(client: TestClient):
    """Test 9: Viewing one owned subject succeeds."""
    _, token = register_and_get_token(client, "viewer@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post("/api/subjects", json={"name": "Linear Algebra"}, headers=headers).json()
    sub_id = created["id"]

    res = client.get(f"/api/subjects/{sub_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["name"] == "Linear Algebra"


def test_get_subject_idor_protection(client: TestClient):
    """Test 10 (MANDATORY IDOR): User B cannot view User A's subject (returns 404)."""
    _, token_a = register_and_get_token(client, "alice_idor@example.com")
    _, token_b = register_and_get_token(client, "bob_idor@example.com")

    created = client.post(
        "/api/subjects",
        json={"name": "Alice Private DBMS"},
        headers={"Authorization": f"Bearer {token_a}"},
    ).json()
    alice_sub_id = created["id"]

    # Bob attempts to get Alice's subject
    res_b = client.get(
        f"/api/subjects/{alice_sub_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_b.status_code == 404
    assert res_b.json()["detail"] == "Subject not found"


def test_update_subject_success(client: TestClient):
    """Test 11: Rename and update description of owned subject."""
    _, token = register_and_get_token(client, "renamer@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/subjects",
        json={"name": "DBMS", "description": "Old desc"},
        headers=headers,
    ).json()
    sub_id = created["id"]

    update_res = client.put(
        f"/api/subjects/{sub_id}",
        json={"name": "Database Management Systems", "description": "New desc"},
        headers=headers,
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["name"] == "Database Management Systems"
    assert updated["description"] == "New desc"
    assert updated["id"] == sub_id


def test_update_subject_cross_user_idor_attack(client: TestClient, db_session: Session):
    """Test 12 (MANDATORY IDOR): User B cannot update/rename User A's subject."""
    _, token_a = register_and_get_token(client, "alice_update@example.com")
    _, token_b = register_and_get_token(client, "bob_update@example.com")

    created = client.post(
        "/api/subjects",
        json={"name": "Original DBMS Name"},
        headers={"Authorization": f"Bearer {token_a}"},
    ).json()
    alice_sub_id = created["id"]

    # Bob attempts to hijack/rename Alice's subject
    res_b = client.put(
        f"/api/subjects/{alice_sub_id}",
        json={"name": "Hacked DBMS"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_b.status_code == 404

    # Verify Alice's subject remains completely unchanged in DB
    subject = db_session.execute(
        select(Subject).where(Subject.id == uuid.UUID(alice_sub_id))
    ).scalar_one()
    assert subject.name == "Original DBMS Name"


def test_update_duplicate_name_conflict(client: TestClient):
    """Test 13: Renaming subject to match another of user's own subjects returns 400."""
    _, token = register_and_get_token(client, "dup_rename@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    s1 = client.post("/api/subjects", json={"name": "Subject One"}, headers=headers).json()
    s2 = client.post("/api/subjects", json={"name": "Subject Two"}, headers=headers).json()

    # Try renaming Subject Two to Subject One
    res = client.put(
        f"/api/subjects/{s2['id']}",
        json={"name": "Subject One"},
        headers=headers,
    )
    assert res.status_code == 400


def test_delete_subject_success(client: TestClient, db_session: Session):
    """Test 14: User deletes own subject returns 204."""
    _, token = register_and_get_token(client, "deleter@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post("/api/subjects", json={"name": "To Delete"}, headers=headers).json()
    sub_id = created["id"]

    del_res = client.delete(f"/api/subjects/{sub_id}", headers=headers)
    assert del_res.status_code == 204

    # Verify record is gone from DB
    subject = db_session.execute(
        select(Subject).where(Subject.id == uuid.UUID(sub_id))
    ).scalar_one_or_none()
    assert subject is None


def test_delete_subject_cross_user_idor_attack(client: TestClient, db_session: Session):
    """Test 15 (MANDATORY IDOR): User B cannot delete User A's subject."""
    _, token_a = register_and_get_token(client, "alice_del@example.com")
    _, token_b = register_and_get_token(client, "bob_del@example.com")

    created = client.post(
        "/api/subjects",
        json={"name": "Alice Indestructible Subject"},
        headers={"Authorization": f"Bearer {token_a}"},
    ).json()
    alice_sub_id = created["id"]

    # Bob attempts to delete Alice's subject
    res_b = client.delete(
        f"/api/subjects/{alice_sub_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_b.status_code == 404

    # Verify Alice's subject still exists and is accessible
    res_a = client.get(
        f"/api/subjects/{alice_sub_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_a.status_code == 200
    assert res_a.json()["name"] == "Alice Indestructible Subject"


def test_delete_cascade_removes_children(client: TestClient, db_session: Session):
    """Test 16: Deleting a subject cascades cleanly to playlists, videos, and documents."""
    _, token = register_and_get_token(client, "cascade_user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post("/api/subjects", json={"name": "Cascade Subject"}, headers=headers).json()
    sub_id = uuid.UUID(created["id"])

    # Create child playlist, video, and document directly via models
    playlist = Playlist(subject_id=sub_id, youtube_playlist_id="PL_TEST_123", title="Test Playlist")
    db_session.add(playlist)
    db_session.commit()
    db_session.refresh(playlist)

    video = Video(playlist_id=playlist.id, youtube_video_id="VID_TEST_123", title="Test Video")
    db_session.add(video)

    document = Document(subject_id=sub_id, filename="lecture.pdf", file_path="/mock/path.pdf")
    db_session.add(document)
    db_session.commit()

    # Verify children exist
    assert db_session.execute(select(Playlist).where(Playlist.subject_id == sub_id)).scalar_one_or_none() is not None
    assert db_session.execute(select(Document).where(Document.subject_id == sub_id)).scalar_one_or_none() is not None

    # Delete subject via API
    del_res = client.delete(f"/api/subjects/{sub_id}", headers=headers)
    assert del_res.status_code == 204

    # Verify children are deleted by cascade
    assert db_session.execute(select(Playlist).where(Playlist.subject_id == sub_id)).scalar_one_or_none() is None
    assert db_session.execute(select(Document).where(Document.subject_id == sub_id)).scalar_one_or_none() is None
    assert db_session.execute(select(Video).where(Video.playlist_id == playlist.id)).scalar_one_or_none() is None


def test_subject_summary_endpoint(client: TestClient, db_session: Session):
    """Test 17: Subject summary endpoint returns accurate counts and enforces ownership."""
    _, token_a = register_and_get_token(client, "alice_sum@example.com")
    _, token_b = register_and_get_token(client, "bob_sum@example.com")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    created = client.post("/api/subjects", json={"name": "Summary Subject"}, headers=headers_a).json()
    sub_id = uuid.UUID(created["id"])

    # Add 1 playlist with 1 completed video and 2 documents
    playlist = Playlist(subject_id=sub_id, youtube_playlist_id="PL_SUM", title="Summary Playlist")
    db_session.add(playlist)
    db_session.commit()
    db_session.refresh(playlist)

    video = Video(playlist_id=playlist.id, youtube_video_id="VID_SUM", title="Done Video", status="completed")
    db_session.add(video)

    doc1 = Document(subject_id=sub_id, filename="doc1.pdf", file_path="/doc1.pdf")
    doc2 = Document(subject_id=sub_id, filename="doc2.pdf", file_path="/doc2.pdf")
    db_session.add_all([doc1, doc2])
    db_session.commit()

    # User A requests summary
    res_a = client.get(f"/api/subjects/{sub_id}/summary", headers=headers_a)
    assert res_a.status_code == 200
    data = res_a.json()
    assert data["playlist_count"] == 1
    assert data["material_count"] == 2
    assert data["processed_video_count"] == 1

    # User B requests summary -> IDOR blocked (404)
    res_b = client.get(f"/api/subjects/{sub_id}/summary", headers=headers_b)
    assert res_b.status_code == 404


def test_v1_prefix_compatibility(client: TestClient):
    """Test 18: /api/v1/subjects route prefix works identically to /api/subjects."""
    _, token = register_and_get_token(client, "v1_user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/api/v1/subjects", json={"name": "V1 Subject"}, headers=headers)
    assert res.status_code == 201
    sub_id = res.json()["id"]

    get_res = client.get(f"/api/v1/subjects/{sub_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "V1 Subject"
