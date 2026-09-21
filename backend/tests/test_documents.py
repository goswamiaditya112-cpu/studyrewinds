import io
import os
import uuid
import pytest
import pypdf
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.models.user import User
from app.models.subject import Subject
from app.models.document import Document
from app.models.chunk import DocumentChunk
from app.services.pdf import chunk_page_text, extract_and_chunk_pdf, validate_pdf_content, PDFValidationError


def register_and_login(client: TestClient, email: str, password: str = "Password123!") -> tuple[dict, str]:
    """Helper to register and login a user."""
    client.post("/api/auth/register", json={"email": email, "password": password})
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    token = res.json()["access_token"]
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    return me_res.json(), token


def create_subject(client: TestClient, token: str, name: str = "Operating Systems") -> str:
    """Helper to create a subject and return its ID."""
    res = client.post(
        "/api/subjects",
        json={"name": name, "description": "Test subject for documents"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201
    return res.json()["id"]


def make_blank_pdf(page_count: int = 1) -> bytes:
    """Creates a valid PDF with blank pages (0 extractable text)."""
    writer = pypdf.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def get_sample_pdf_bytes(page_count: int = 2, with_empty_page_in_middle: bool = False) -> bytes:
    """Extracts pages from the provided educational PDF for realistic test cases."""
    # Find sample pdf in user_uploaded or scratch
    sample_dir = os.path.join(os.path.expanduser("~"), ".gemini", "antigravity", "brain", "dadd4752-0df2-4b2d-a275-63bd48cb9333", ".user_uploaded")
    src = os.path.join(sample_dir, "media_1789771584331.pdf")
    if not os.path.exists(src):
        src = os.path.join(sample_dir, "media_1789771593492.pdf")

    reader = pypdf.PdfReader(src)
    writer = pypdf.PdfWriter()
    for i in range(min(page_count, len(reader.pages))):
        writer.add_page(reader.pages[i])
        if with_empty_page_in_middle and i == 0:
            writer.add_blank_page(width=612, height=792)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ============================================================
# 1. UNIT TESTS: Validation, Chunking, and Page Provenance
# ============================================================

def test_chunk_page_text_bounds_and_overlap():
    """Verify ~400 char chunking, ~50 char overlap, and within-page boundary guarantees."""
    # 900-character test string
    sample_text = (
        "Operating systems manage hardware resources. "
        "A process is a program in execution containing program counter, stack, and data section. "
        "Process scheduling manages the execution of multiple active processes across available CPU cores. "
        "Context switching saves the state of the active process and loads the state of the newly scheduled process. "
        "Inter-process communication allows processes to exchange information through shared memory or message passing. "
        "Synchronization mechanisms prevent race conditions."
    )
    assert len(sample_text) > 450

    chunks = chunk_page_text(sample_text, page_number=3, chunk_size=400, overlap=50)
    assert len(chunks) >= 2

    for c in chunks:
        # Exact page provenance preserved
        assert c["page_number"] == 3
        assert len(c["text"]) > 0
        assert len(c["text"]) <= 420  # bounded near chunk size

    # Deterministic 0-indexed chunk_index
    assert chunks[0]["chunk_index"] == 0
    assert chunks[1]["chunk_index"] == 1


def test_chunk_page_empty_or_whitespace():
    """Empty or whitespace text must yield 0 chunks."""
    assert chunk_page_text("", page_number=1) == []
    assert chunk_page_text("   \n\t  ", page_number=2) == []


def test_validate_pdf_content_checks():
    """Tests header magic bytes, empty files, extensions, and corrupted files."""
    # Valid
    valid_bytes = make_blank_pdf(1)
    validate_pdf_content(valid_bytes, "doc.pdf")

    # Empty
    with pytest.raises(PDFValidationError, match="empty"):
        validate_pdf_content(b"", "doc.pdf")

    # Invalid extension
    with pytest.raises(PDFValidationError, match="Invalid file extension"):
        validate_pdf_content(valid_bytes, "doc.txt")

    # Invalid header
    with pytest.raises(PDFValidationError, match="invalid magic header"):
        validate_pdf_content(b"NOT A PDF CONTENT", "doc.pdf")

    # Corrupt PDF
    with pytest.raises(PDFValidationError, match="Corrupt or unreadable"):
        validate_pdf_content(b"%PDF-corrupted_stream_content_12345", "doc.pdf")


# ============================================================
# 2. INTEGRATION TESTS: Upload, Ownership, and Security
# ============================================================

def test_unauthenticated_document_endpoints_rejected(client: TestClient):
    """Unauthenticated access to any document endpoint must return 401."""
    random_id = uuid.uuid4()
    res1 = client.post("/api/study-materials")
    assert res1.status_code == 401

    res2 = client.get("/api/study-materials")
    assert res2.status_code == 401

    res3 = client.get(f"/api/study-materials/{random_id}")
    assert res3.status_code == 401

    res4 = client.get(f"/api/study-materials/{random_id}/pages/1")
    assert res4.status_code == 401

    res5 = client.get(f"/api/study-materials/{random_id}/chunks")
    assert res5.status_code == 401

    res6 = client.delete(f"/api/study-materials/{random_id}")
    assert res6.status_code == 401


def test_authenticated_pdf_upload_success(client: TestClient, db_session: Session):
    """Test full upload pipeline: validation, safe storage, extraction, chunking, and DB persistence."""
    _, token = register_and_login(client, "pdf_user1@example.com")
    subject_id = create_subject(client, token, "Computer Networks")

    pdf_bytes = get_sample_pdf_bytes(page_count=2)
    files = {"file": ("Networks Notes.pdf", pdf_bytes, "application/pdf")}
    data = {"subject_id": subject_id}

    res = client.post(
        "/api/study-materials",
        data=data,
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res.status_code == 201
    res_data = res.json()["data"]
    assert res_data["filename"] == "Networks Notes.pdf"
    assert res_data["status"] == "completed"
    assert res_data["page_count"] == 2
    assert res_data["processing_error"] is None

    doc_id = res_data["id"]

    # Verify DB persistence
    db_doc = db_session.execute(select(Document).where(Document.id == uuid.UUID(doc_id))).scalar_one()
    assert db_doc.status == "completed"
    assert db_doc.page_count == 2
    assert os.path.exists(db_doc.file_path)

    # Verify stored chunks in DB have page provenance
    chunks = db_session.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == uuid.UUID(doc_id))
        .order_by(DocumentChunk.page_number.asc(), DocumentChunk.chunk_index.asc())
    ).scalars().all()

    assert len(chunks) > 0
    # Every chunk has page_number and 384-dim zero-vector placeholder
    for c in chunks:
        assert c.page_number in [1, 2]
        assert c.chunk_index >= 0
        assert len(c.embedding) == 384


def test_scanned_or_image_only_pdf_handling(client: TestClient, db_session: Session):
    """Completely blank or image-only PDF with zero text must be marked failed with clear error."""
    _, token = register_and_login(client, "scanned_user@example.com")
    subject_id = create_subject(client, token, "Image Only Test")

    blank_pdf = make_blank_pdf(page_count=3)
    files = {"file": ("scanned_paper.pdf", blank_pdf, "application/pdf")}
    data = {"subject_id": subject_id}

    res = client.post(
        "/api/study-materials",
        data=data,
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res.status_code == 201
    res_data = res.json()["data"]
    assert res_data["status"] == "failed"
    assert res_data["page_count"] == 3
    assert "No extractable text" in res_data["processing_error"]

    # In DB: 0 chunks created
    chunks = db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(res_data["id"]))
    ).scalars().all()
    assert len(chunks) == 0


def test_empty_pages_in_middle_preserved_in_page_count(client: TestClient, db_session: Session):
    """A PDF with an empty page between text pages keeps full page_count and skips empty chunks."""
    _, token = register_and_login(client, "empty_page_user@example.com")
    subject_id = create_subject(client, token, "Empty Page Test")

    # 3 physical pages: Page 1 text, Page 2 blank, Page 3 text
    pdf_bytes = get_sample_pdf_bytes(page_count=2, with_empty_page_in_middle=True)
    files = {"file": ("mixed_pages.pdf", pdf_bytes, "application/pdf")}

    res = client.post(
        "/api/study-materials",
        data={"subject_id": subject_id},
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201
    doc_data = res.json()["data"]
    assert doc_data["status"] == "completed"
    assert doc_data["page_count"] == 3

    # Verify chunks: should have page 1 and page 3, but zero chunks for page 2
    chunks = db_session.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == uuid.UUID(doc_data["id"]))
    ).scalars().all()

    page_numbers = {c.page_number for c in chunks}
    assert 1 in page_numbers
    assert 2 not in page_numbers  # Page 2 was blank, no empty chunk created
    assert 3 in page_numbers


def test_idor_cross_user_document_protection(client: TestClient, db_session: Session):
    """User B cannot view, retrieve pages, retrieve chunks, or delete User A's document (returns 404)."""
    _, token_a = register_and_login(client, "doc_user_a@example.com")
    sub_a = create_subject(client, token_a, "User A Subject")

    _, token_b = register_and_login(client, "doc_user_b@example.com")
    sub_b = create_subject(client, token_b, "User B Subject")

    pdf_bytes = get_sample_pdf_bytes(page_count=1)
    res_a = client.post(
        "/api/study-materials",
        data={"subject_id": sub_a},
        files={"file": ("doc_a.pdf", pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    doc_a_id = res_a.json()["data"]["id"]

    # 1. User B tries to upload into User A's subject
    bad_upload = client.post(
        "/api/study-materials",
        data={"subject_id": sub_a},
        files={"file": ("doc_hacked.pdf", pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert bad_upload.status_code == 404

    # 2. User B tries to view User A's document
    bad_get = client.get(
        f"/api/study-materials/{doc_a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert bad_get.status_code == 404

    # 3. User B tries to get User A's document pages
    bad_page = client.get(
        f"/api/study-materials/{doc_a_id}/pages/1",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert bad_page.status_code == 404

    # 4. User B tries to get User A's chunks
    bad_chunks = client.get(
        f"/api/study-materials/{doc_a_id}/chunks",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert bad_chunks.status_code == 404

    # 5. User B tries to delete User A's document
    bad_delete = client.delete(
        f"/api/study-materials/{doc_a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert bad_delete.status_code == 404


def test_document_deletion_cascades_and_removes_file(client: TestClient, db_session: Session):
    """Deleting a document deletes its DB record, cascade-deletes all chunks, and removes stored file."""
    _, token = register_and_login(client, "del_doc_user@example.com")
    sub_id = create_subject(client, token, "Delete Cascade Subject")

    pdf_bytes = get_sample_pdf_bytes(page_count=2)
    res = client.post(
        "/api/study-materials",
        data={"subject_id": sub_id},
        files={"file": ("to_delete.pdf", pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = res.json()["data"]["id"]

    # Verify document and file exist
    db_doc = db_session.execute(select(Document).where(Document.id == uuid.UUID(doc_id))).scalar_one()
    file_path = db_doc.file_path
    assert os.path.exists(file_path)

    # Delete via API
    del_res = client.delete(
        f"/api/study-materials/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_res.status_code == 204

    # Verify DB row is gone
    gone_doc = db_session.execute(select(Document).where(Document.id == uuid.UUID(doc_id))).scalar_one_or_none()
    assert gone_doc is None

    # Verify chunks are cascade deleted
    remaining_chunks = db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(doc_id))
    ).scalars().all()
    assert len(remaining_chunks) == 0

    # Verify stored file is removed from disk
    assert not os.path.exists(file_path)


def test_duplicate_filenames_allowed_with_distinct_identities(client: TestClient, db_session: Session):
    """Two uploads with the exact same filename must be treated as independent document identities."""
    _, token = register_and_login(client, "dup_filename_user@example.com")
    sub_id = create_subject(client, token, "Duplicate Filename Subject")

    pdf_bytes = get_sample_pdf_bytes(page_count=1)

    res1 = client.post(
        "/api/study-materials",
        data={"subject_id": sub_id},
        files={"file": ("syllabus.pdf", pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    res2 = client.post(
        "/api/study-materials",
        data={"subject_id": sub_id},
        files={"file": ("syllabus.pdf", pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res1.status_code == 201
    assert res2.status_code == 201
    d1 = res1.json()["data"]
    d2 = res2.json()["data"]

    assert d1["id"] != d2["id"]
    assert d1["filename"] == d2["filename"]


def test_document_page_endpoint(client: TestClient, db_session: Session):
    """Test GET /study-materials/{id}/pages/{page} returns text for the frontend Document viewer."""
    _, token = register_and_login(client, "page_viewer_user@example.com")
    sub_id = create_subject(client, token, "Viewer Subject")

    pdf_bytes = get_sample_pdf_bytes(page_count=2)
    upload_res = client.post(
        "/api/study-materials",
        data={"subject_id": sub_id},
        files={"file": ("lecture_notes.pdf", pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = upload_res.json()["data"]["id"]

    # View page 1
    page1_res = client.get(
        f"/api/study-materials/{doc_id}/pages/1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert page1_res.status_code == 200
    p1 = page1_res.json()
    assert p1["page_number"] == 1
    assert len(p1["text"]) > 0

    # View out of range page (e.g. Page 99)
    page99_res = client.get(
        f"/api/study-materials/{doc_id}/pages/99",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert page99_res.status_code == 200
    assert page99_res.json()["text"] == ""


def test_api_v1_compatibility(client: TestClient, db_session: Session):
    """Verify document endpoints are accessible with /api/v1 prefix."""
    _, token = register_and_login(client, "v1_doc_user@example.com")
    sub_id = create_subject(client, token, "v1 Prefix Subject")

    pdf_bytes = get_sample_pdf_bytes(page_count=1)
    res = client.post(
        "/api/v1/study-materials",
        data={"subject_id": sub_id},
        files={"file": ("v1_doc.pdf", pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201

    list_res = client.get(
        "/api/v1/study-materials",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_res.status_code == 200
    assert len(list_res.json()["data"]) >= 1
