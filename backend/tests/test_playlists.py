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
from app.services.youtube import extract_playlist_id, PlaylistIngestionError


def register_and_login(client: TestClient, email: str, password: str = "Password123!") -> tuple[dict, str]:
    """Helper to register and login a user."""
    client.post("/api/auth/register", json={"email": email, "password": password})
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    token = res.json()["access_token"]
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    return me_res.json(), token


def create_subject(client: TestClient, token: str, name: str = "Computer Science") -> str:
    """Helper to create a subject and return its ID."""
    res = client.post(
        "/api/subjects",
        json={"name": name, "description": "Test subject"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201
    return res.json()["id"]


# ============================================================
# UNIT TESTS: URL Validation & Playlist ID Extraction
# ============================================================

def test_extract_playlist_id_valid_formats():
    """Test standard valid YouTube playlist URLs and bare IDs."""
    url1 = "https://www.youtube.com/playlist?list=PLxCzCOWd7aiGz9donHRrE9I3Mwn6XdP8p"
    assert extract_playlist_id(url1) == "PLxCzCOWd7aiGz9donHRrE9I3Mwn6XdP8p"

    url2 = "https://youtube.com/playlist?list=PL_TEST_ID_12345"
    assert extract_playlist_id(url2) == "PL_TEST_ID_12345"

    url3 = "https://m.youtube.com/watch?v=abc12345&list=PL_MOBILE_LIST_12"
    assert extract_playlist_id(url3) == "PL_MOBILE_LIST_12"

    bare_id = "PLxCzCOWd7aiFAN6I8CuViBuCdJgiOkT2Y"
    assert extract_playlist_id(bare_id) == "PLxCzCOWd7aiFAN6I8CuViBuCdJgiOkT2Y"


def test_extract_playlist_id_invalid_formats():
    """Test rejection of invalid, non-playlist, or non-YouTube URLs."""
    with pytest.raises(ValueError, match="cannot be empty"):
        extract_playlist_id("")

    with pytest.raises(ValueError, match="cannot be empty"):
        extract_playlist_id("   ")

    with pytest.raises(ValueError, match="supported YouTube domain"):
        extract_playlist_id("https://google.com/search?q=playlist")

    with pytest.raises(ValueError, match="'list' query parameter is required"):
        extract_playlist_id("https://www.youtube.com/watch?v=bkSWJJZNgf8")

    with pytest.raises(ValueError, match="'list' query parameter is required"):
        extract_playlist_id("https://www.youtube.com/")


# ============================================================
# INTEGRATION TESTS: Playlist Ingestion API
# ============================================================

def test_create_playlist_unauthenticated(client: TestClient):
    """Test 1: Unauthenticated playlist creation returns 401."""
    res = client.post("/api/playlists", json={
        "subject_id": str(uuid.uuid4()),
        "playlist_url": "https://www.youtube.com/playlist?list=PL_TEST_123",
    })
    assert res.status_code == 401


def test_create_playlist_missing_subject(client: TestClient):
    """Test 6: Ingesting to non-existent subject returns 404."""
    _, token = register_and_login(client, "user_nosubject@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/api/playlists", json={
        "subject_id": str(uuid.uuid4()),
        "playlist_url": "https://www.youtube.com/playlist?list=PL_TEST_123",
    }, headers=headers)
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_create_playlist_idor_cross_user_subject(client: TestClient):
    """Test 7: User B cannot attach a playlist to User A's subject."""
    _, token_a = register_and_login(client, "alice_sub_idor@example.com")
    _, token_b = register_and_login(client, "bob_sub_idor@example.com")

    sub_id_a = create_subject(client, token_a, "Alice Private Subject")

    # Bob attempts to attach playlist to Alice's subject
    res_b = client.post("/api/playlists", json={
        "subject_id": sub_id_a,
        "playlist_url": "https://www.youtube.com/playlist?list=PL_BOB_ATTACK",
    }, headers={"Authorization": f"Bearer {token_b}"})

    assert res_b.status_code == 404


def test_create_playlist_invalid_urls(client: TestClient):
    """Test 3, 4, 5: Invalid URLs rejected before external calls."""
    _, token = register_and_login(client, "user_invalid_urls@example.com")
    sub_id = create_subject(client, token, "Validations")
    headers = {"Authorization": f"Bearer {token}"}

    # Non-YouTube URL
    res1 = client.post("/api/playlists", json={
        "subject_id": sub_id,
        "playlist_url": "https://vimeo.com/playlist/123",
    }, headers=headers)
    assert res1.status_code == 400

    # Video only without playlist
    res2 = client.post("/api/playlists", json={
        "subject_id": sub_id,
        "playlist_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    }, headers=headers)
    assert res2.status_code == 400

    # Random string
    res3 = client.post("/api/playlists", json={
        "subject_id": sub_id,
        "playlist_url": "not a url at all",
    }, headers=headers)
    assert res3.status_code == 400


@patch("app.api.playlists.fetch_playlist_metadata")
def test_create_playlist_success(mock_fetch, client: TestClient, db_session: Session):
    """Test 2, 8, 9, 10, 13: Ingestion succeeds, stores playlist & videos, preserves order."""
    mock_playlist_id = "PL_DYNAMIC_TEST_001"
    mock_fetch.return_value = {
        "youtube_playlist_id": mock_playlist_id,
        "title": "Data Structures & Algorithms Course",
        "videos": [
            {"youtube_video_id": "VID_01", "title": "Intro to Arrays", "duration_seconds": 600},
            {"youtube_video_id": "VID_02", "title": "Linked Lists Deep Dive", "duration_seconds": 1200},
            {"youtube_video_id": "VID_03", "title": "Binary Trees Explained", "duration_seconds": 950},
        ],
    }

    _, token = register_and_login(client, "alice_ingest@example.com")
    sub_id = create_subject(client, token, "Algorithms")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/api/playlists", json={
        "subject_id": sub_id,
        "playlist_url": f"https://www.youtube.com/playlist?list={mock_playlist_id}",
    }, headers=headers)

    assert res.status_code == 201
    data = res.json()
    assert data["youtube_playlist_id"] == mock_playlist_id
    assert data["title"] == "Data Structures & Algorithms Course"
    assert data["video_count"] == 3
    assert data["status"] == "completed"

    playlist_id = uuid.UUID(data["id"])

    # Verify videos stored in database with order preserved
    videos = db_session.execute(
        select(Video).where(Video.playlist_id == playlist_id).order_by(Video.created_at.asc())
    ).scalars().all()

    assert len(videos) == 3
    assert videos[0].youtube_video_id == "VID_01"
    assert videos[0].title == "Intro to Arrays"
    assert videos[0].duration_seconds == 600
    assert videos[0].status == "pending"
    assert videos[0].transcript_source == "none"

    assert videos[1].youtube_video_id == "VID_02"
    assert videos[2].youtube_video_id == "VID_03"


@patch("app.api.playlists.fetch_playlist_metadata")
def test_create_duplicate_playlist_prevented(mock_fetch, client: TestClient):
    """Test 11: Duplicate playlist submission to same subject returns 409 Conflict."""
    mock_playlist_id = "PL_DUPLICATE_CHECK"
    mock_fetch.return_value = {
        "youtube_playlist_id": mock_playlist_id,
        "title": "Operating Systems",
        "videos": [{"youtube_video_id": "OS_01", "title": "OS Intro", "duration_seconds": 300}],
    }

    _, token = register_and_login(client, "alice_dup@example.com")
    sub_id = create_subject(client, token, "OS Subject")
    headers = {"Authorization": f"Bearer {token}"}

    # First submission -> 201
    res1 = client.post("/api/playlists", json={
        "subject_id": sub_id,
        "playlist_url": f"https://www.youtube.com/playlist?list={mock_playlist_id}",
    }, headers=headers)
    assert res1.status_code == 201

    # Second submission to same subject -> 409
    res2 = client.post("/api/playlists", json={
        "subject_id": sub_id,
        "playlist_url": f"https://www.youtube.com/playlist?list={mock_playlist_id}",
    }, headers=headers)
    assert res2.status_code == 409
    assert "already been added" in res2.json()["detail"].lower()


@patch("app.api.playlists.fetch_playlist_metadata")
def test_list_playlists_scoped_to_user_and_subject(mock_fetch, client: TestClient):
    """Test 14, 17: Playlists are isolated by user and scoped by subject."""
    mock_fetch.side_effect = lambda pid: {
        "youtube_playlist_id": pid,
        "title": f"Title {pid}",
        "videos": [{"youtube_video_id": f"v_{pid}", "title": "Vid", "duration_seconds": 100}],
    }

    _, token_a = register_and_login(client, "alice_lists@example.com")
    _, token_b = register_and_login(client, "bob_lists@example.com")

    sub_a = create_subject(client, token_a, "Alice Subject")
    sub_b = create_subject(client, token_b, "Bob Subject")

    # Alice creates 2 playlists
    client.post("/api/playlists", json={"subject_id": sub_a, "playlist_url": "https://www.youtube.com/playlist?list=PL_A1"}, headers={"Authorization": f"Bearer {token_a}"})
    client.post("/api/playlists", json={"subject_id": sub_a, "playlist_url": "https://www.youtube.com/playlist?list=PL_A2"}, headers={"Authorization": f"Bearer {token_a}"})

    # Bob creates 1 playlist
    client.post("/api/playlists", json={"subject_id": sub_b, "playlist_url": "https://www.youtube.com/playlist?list=PL_B1"}, headers={"Authorization": f"Bearer {token_b}"})

    # Alice lists all her playlists
    res_a = client.get("/api/playlists", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a.status_code == 200
    alice_pls = res_a.json()
    assert len(alice_pls) == 2
    assert {p["youtube_playlist_id"] for p in alice_pls} == {"PL_A1", "PL_A2"}

    # Bob lists all his playlists
    res_b = client.get("/api/playlists", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b.status_code == 200
    bob_pls = res_b.json()
    assert len(bob_pls) == 1
    assert bob_pls[0]["youtube_playlist_id"] == "PL_B1"

    # User B attempts to list playlists of User A's subject -> 404
    res_b_attack = client.get(f"/api/subjects/{sub_a}/playlists", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b_attack.status_code == 404


@patch("app.api.playlists.fetch_playlist_metadata")
def test_get_playlist_details_and_videos_idor(mock_fetch, client: TestClient):
    """Test 15, 16, 17, 18: Playlist details and video lists are protected from IDOR."""
    mock_fetch.return_value = {
        "youtube_playlist_id": "PL_ALICE_SECRET",
        "title": "Alice Secret Videos",
        "videos": [
            {"youtube_video_id": "SEC_01", "title": "Secret 1", "duration_seconds": 120},
            {"youtube_video_id": "SEC_02", "title": "Secret 2", "duration_seconds": 240},
        ],
    }

    _, token_a = register_and_login(client, "alice_idor_pl@example.com")
    _, token_b = register_and_login(client, "bob_idor_pl@example.com")

    sub_a = create_subject(client, token_a, "Alice Secrets")
    create_res = client.post("/api/playlists", json={
        "subject_id": sub_a,
        "playlist_url": "https://www.youtube.com/playlist?list=PL_ALICE_SECRET",
    }, headers={"Authorization": f"Bearer {token_a}"})
    pl_id = create_res.json()["id"]

    # Alice views playlist details -> 200 OK
    res_a_detail = client.get(f"/api/playlists/{pl_id}", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a_detail.status_code == 200
    assert len(res_a_detail.json()["videos"]) == 2

    # Bob attempts to view Alice's playlist details -> 404 IDOR Defense
    res_b_detail = client.get(f"/api/playlists/{pl_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b_detail.status_code == 404

    # Alice views video list -> 200 OK
    res_a_vids = client.get(f"/api/playlists/{pl_id}/videos", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a_vids.status_code == 200
    vids = res_a_vids.json()
    assert len(vids) == 2
    assert vids[0]["number"] == 1
    assert vids[0]["video_url"] == "https://www.youtube.com/watch?v=SEC_01"

    # Bob attempts to view Alice's videos -> 404 IDOR Defense
    res_b_vids = client.get(f"/api/playlists/{pl_id}/videos", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b_vids.status_code == 404


@patch("app.api.playlists.fetch_playlist_metadata")
def test_delete_playlist_cascade(mock_fetch, client: TestClient, db_session: Session):
    """Test: Deleting a playlist removes the playlist and cascades to all child videos."""
    mock_fetch.return_value = {
        "youtube_playlist_id": "PL_TO_DELETE",
        "title": "Playlist to Delete",
        "videos": [
            {"youtube_video_id": "DEL_01", "title": "V1", "duration_seconds": 100},
            {"youtube_video_id": "DEL_02", "title": "V2", "duration_seconds": 200},
        ],
    }

    _, token = register_and_login(client, "alice_delete_pl@example.com")
    sub_id = create_subject(client, token, "Temp Subject")
    headers = {"Authorization": f"Bearer {token}"}

    create_res = client.post("/api/playlists", json={
        "subject_id": sub_id,
        "playlist_url": "https://www.youtube.com/playlist?list=PL_TO_DELETE",
    }, headers=headers)
    pl_id = create_res.json()["id"]

    # Verify videos exist in DB
    vids_before = db_session.execute(
        select(Video).where(Video.playlist_id == uuid.UUID(pl_id))
    ).scalars().all()
    assert len(vids_before) == 2

    # Delete playlist
    del_res = client.delete(f"/api/playlists/{pl_id}", headers=headers)
    assert del_res.status_code == 204

    # Verify playlist and videos gone from DB
    pl_after = db_session.execute(
        select(Playlist).where(Playlist.id == uuid.UUID(pl_id))
    ).scalar_one_or_none()
    assert pl_after is None

    vids_after = db_session.execute(
        select(Video).where(Video.playlist_id == uuid.UUID(pl_id))
    ).scalars().all()
    assert len(vids_after) == 0


@patch("app.api.playlists.fetch_playlist_metadata")
def test_api_v1_compatibility(mock_fetch, client: TestClient):
    """Test 22: /api/v1 prefix functions identically to /api."""
    mock_fetch.return_value = {
        "youtube_playlist_id": "PL_V1_PREFIX",
        "title": "V1 Test Playlist",
        "videos": [{"youtube_video_id": "V1_01", "title": "V1 Video", "duration_seconds": 120}],
    }

    _, token = register_and_login(client, "v1_user_pl@example.com")
    sub_id = create_subject(client, token, "V1 Subject")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/api/v1/playlists", json={
        "subject_id": sub_id,
        "playlist_url": "https://www.youtube.com/playlist?list=PL_V1_PREFIX",
    }, headers=headers)
    assert res.status_code == 201

    pl_id = res.json()["id"]
    get_res = client.get(f"/api/v1/playlists/{pl_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "V1 Test Playlist"


@patch("app.api.playlists.fetch_playlist_metadata")
def test_private_or_unavailable_playlist(mock_fetch, client: TestClient):
    """Test: Inaccessible or private playlist returns 400 with user-friendly message."""
    mock_fetch.side_effect = PlaylistIngestionError("YouTube playlist is unavailable, private, or not found.")

    _, token = register_and_login(client, "private_pl_user@example.com")
    sub_id = create_subject(client, token, "Private Test Subject")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/api/playlists", json={
        "subject_id": sub_id,
        "playlist_url": "https://www.youtube.com/playlist?list=PL_PRIVATE_12345",
    }, headers=headers)

    assert res.status_code == 400
    assert "unavailable, private, or not found" in res.json()["detail"]


@patch("app.api.playlists.fetch_playlist_metadata")
def test_duplicate_videos_handled_safely(mock_fetch, client: TestClient):
    """Test 12: Repeated video IDs in external metadata are deduplicated without crashing."""
    mock_fetch.return_value = {
        "youtube_playlist_id": "PL_DUP_VIDS",
        "title": "Dup Video Playlist",
        "videos": [
            {"youtube_video_id": "SAME_VID", "title": "Vid 1", "duration_seconds": 100},
            {"youtube_video_id": "SAME_VID", "title": "Vid 1 duplicate", "duration_seconds": 100},
            {"youtube_video_id": "OTHER_VID", "title": "Vid 2", "duration_seconds": 200},
        ],
    }

    _, token = register_and_login(client, "dup_vids_user@example.com")
    sub_id = create_subject(client, token, "Dup Video Subject")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/api/playlists", json={
        "subject_id": sub_id,
        "playlist_url": "https://www.youtube.com/playlist?list=PL_DUP_VIDS",
    }, headers=headers)

    assert res.status_code == 201


@patch("app.api.playlists.fetch_playlist_metadata")
def test_get_subject_playlists_endpoint(mock_fetch, client: TestClient):
    """Test: GET /api/subjects/{subject_id}/playlists returns playlists for that subject."""
    mock_fetch.return_value = {
        "youtube_playlist_id": "PL_SUB_SPECIFIC",
        "title": "Subject Specific Playlist",
        "videos": [{"youtube_video_id": "V_SPEC", "title": "Spec Vid", "duration_seconds": 90}],
    }

    _, token = register_and_login(client, "sub_spec_user@example.com")
    sub_id = create_subject(client, token, "Specific Subject")
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/api/playlists", json={
        "subject_id": sub_id,
        "playlist_url": "https://www.youtube.com/playlist?list=PL_SUB_SPECIFIC",
    }, headers=headers)

    res = client.get(f"/api/subjects/{sub_id}/playlists", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["youtube_playlist_id"] == "PL_SUB_SPECIFIC"
    assert data[0]["video_count"] == 1


# ============================================================
# FAILURE ISOLATION & PARTIAL FAILURE TESTS
# ============================================================

@patch("app.services.youtube.yt_dlp.YoutubeDL")
def test_fetch_metadata_counts_failures_and_deduplicates(mock_ydl_cls):
    """Test: fetch_playlist_metadata counts None/deleted/private entries without counting duplicates as failures."""
    from app.services.youtube import fetch_playlist_metadata

    mock_instance = mock_ydl_cls.return_value.__enter__.return_value
    mock_instance.extract_info.return_value = {
        "title": "Mixed Status Playlist",
        "entries": [
            {"id": "V_VALID_1", "title": "Valid Lecture 1", "duration": 300},
            None,  # skipped by ignoreerrors
            {"id": "V_DEL", "title": "[Deleted video]", "duration": None},
            {"id": "V_PRIV", "title": "[Private video]", "duration": None},
            {"id": "V_VALID_2", "title": "Valid Lecture 2", "duration": 450},
            {"id": "V_VALID_1", "title": "Valid Lecture 1 Dup", "duration": 300},  # duplicate
        ],
    }

    result = fetch_playlist_metadata("PL_MIXED_FAILURES")
    assert result["title"] == "Mixed Status Playlist"
    assert len(result["videos"]) == 2
    assert result["failed_video_count"] == 3  # None + Deleted + Private (dup is NOT counted as failure)
    assert [v["youtube_video_id"] for v in result["videos"]] == ["V_VALID_1", "V_VALID_2"]


@patch("app.api.playlists.fetch_playlist_metadata")
def test_partial_failure_persists_valid_videos(mock_fetch, client: TestClient, db_session: Session):
    """Test: When some videos fail and others succeed, valid videos are saved and status is partial_failure."""
    mock_fetch.return_value = {
        "youtube_playlist_id": "PL_PARTIAL_FAIL",
        "title": "Partial Failure Course",
        "videos": [
            {"youtube_video_id": "GOOD_1", "title": "Good Video 1", "duration_seconds": 600},
            {"youtube_video_id": "GOOD_2", "title": "Good Video 2", "duration_seconds": 800},
        ],
        "failed_video_count": 2,  # 2 videos failed during extraction
    }

    _, token = register_and_login(client, "partial_fail_user@example.com")
    sub_id = create_subject(client, token, "Partial Fail Subject")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/api/playlists", json={
        "subject_id": sub_id,
        "playlist_url": "https://www.youtube.com/playlist?list=PL_PARTIAL_FAIL",
    }, headers=headers)

    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "partial_failure"
    assert data["video_count"] == 2

    # Verify both valid videos were successfully persisted in PostgreSQL
    pl_id = uuid.UUID(data["id"])
    saved_vids = db_session.execute(
        select(Video).where(Video.playlist_id == pl_id).order_by(Video.created_at.asc())
    ).scalars().all()

    assert len(saved_vids) == 2
    assert saved_vids[0].youtube_video_id == "GOOD_1"
    assert saved_vids[1].youtube_video_id == "GOOD_2"


@patch("app.api.playlists.fetch_playlist_metadata")
def test_all_valid_playlist_status_is_completed(mock_fetch, client: TestClient):
    """Test: When all videos succeed and failed_video_count is 0, status is completed."""
    mock_fetch.return_value = {
        "youtube_playlist_id": "PL_ALL_GOOD",
        "title": "All Good Course",
        "videos": [
            {"youtube_video_id": "PERFECT_1", "title": "P1", "duration_seconds": 100},
            {"youtube_video_id": "PERFECT_2", "title": "P2", "duration_seconds": 200},
        ],
        "failed_video_count": 0,
    }

    _, token = register_and_login(client, "all_good_user@example.com")
    sub_id = create_subject(client, token, "All Good Subject")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/api/playlists", json={
        "subject_id": sub_id,
        "playlist_url": "https://www.youtube.com/playlist?list=PL_ALL_GOOD",
    }, headers=headers)

    assert res.status_code == 201
    assert res.json()["status"] == "completed"


@patch("app.api.playlists.fetch_playlist_metadata")
def test_zero_usable_videos_playlist_status_is_failed(mock_fetch, client: TestClient):
    """Test: When 0 usable videos are extracted, status is failed."""
    mock_fetch.return_value = {
        "youtube_playlist_id": "PL_ZERO_USABLE",
        "title": "Empty/Corrupted Playlist",
        "videos": [],
        "failed_video_count": 4,
    }

    _, token = register_and_login(client, "zero_user@example.com")
    sub_id = create_subject(client, token, "Zero Video Subject")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/api/playlists", json={
        "subject_id": sub_id,
        "playlist_url": "https://www.youtube.com/playlist?list=PL_ZERO_USABLE",
    }, headers=headers)

    assert res.status_code == 201
    assert res.json()["status"] == "failed"
    assert res.json()["video_count"] == 0


@patch("app.api.playlists.fetch_playlist_metadata")
def test_duplicates_do_not_trigger_partial_failure(mock_fetch, client: TestClient):
    """Test: Duplicates within a playlist are deduplicated and do NOT mark playlist as partial_failure."""
    mock_fetch.return_value = {
        "youtube_playlist_id": "PL_CLEAN_DUPS",
        "title": "Clean Playlist with Dups",
        "videos": [
            {"youtube_video_id": "DUP_A", "title": "Vid A", "duration_seconds": 100},
            {"youtube_video_id": "DUP_A", "title": "Vid A repeat", "duration_seconds": 100},
        ],
        "failed_video_count": 0,  # no external failures
    }

    _, token = register_and_login(client, "dup_clean_user@example.com")
    sub_id = create_subject(client, token, "Clean Dup Subject")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/api/playlists", json={
        "subject_id": sub_id,
        "playlist_url": "https://www.youtube.com/playlist?list=PL_CLEAN_DUPS",
    }, headers=headers)

    assert res.status_code == 201
    assert res.json()["status"] == "completed"
    assert res.json()["video_count"] == 1

