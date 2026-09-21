import os
import uuid
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from app.db.session import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.subject import Subject
from app.models.document import Document
from app.models.chunk import DocumentChunk
from app.schemas.document import (
    DocumentResponse,
    DocumentChunkResponse,
    DocumentDetailResponse,
    DocumentPageResponse,
)
from app.services.pdf import (
    validate_pdf_content,
    save_uploaded_pdf,
    delete_stored_pdf,
    extract_and_chunk_pdf,
    PDFValidationError,
)

logger = logging.getLogger("studyrewinds.api.documents")
router = APIRouter(tags=["Study Materials / Documents"])


def _verify_subject_ownership(db: Session, subject_id: uuid.UUID, user_id: uuid.UUID) -> Subject:
    """Enforces that current_user owns the target Subject. Returns Subject or raises 404."""
    subject = db.execute(
        select(Subject).where(
            Subject.id == subject_id,
            Subject.user_id == user_id,
        )
    ).scalar_one_or_none()

    if not subject:
        logger.warning("User %s attempted to access unowned or nonexistent subject %s", user_id, subject_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found or access denied.",
        )
    return subject


def _verify_document_ownership(db: Session, document_id: uuid.UUID, user_id: uuid.UUID) -> Document:
    """Enforces strict server-side ownership: current_user -> Subject -> Document. Returns Document or raises 404."""
    doc = db.execute(
        select(Document)
        .join(Subject, Document.subject_id == Subject.id)
        .where(
            Document.id == document_id,
            Subject.user_id == user_id,
        )
    ).scalar_one_or_none()

    if not doc:
        logger.warning("User %s attempted to access unowned or nonexistent document %s", user_id, document_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or access denied.",
        )
    return doc


def _doc_to_dict(doc: Document) -> dict:
    return {
        "id": str(doc.id),
        "subject_id": str(doc.subject_id),
        "filename": doc.filename,
        "page_count": doc.page_count,
        "status": doc.status,
        "processing_error": doc.error_message,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


@router.post(
    "/study-materials",
    status_code=status.HTTP_201_CREATED,
)
def upload_study_material(
    subject_id: uuid.UUID = Form(..., description="Target Subject UUID"),
    file: UploadFile = File(..., description="Uploaded PDF file"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Authenticated PDF upload:
    1. Verifies Subject ownership (current_user -> Subject).
    2. Validates PDF format, magic bytes, readability, and size limit (<= 50MB).
    3. Safely stores PDF in internal storage using generated UUID filename (path traversal protection).
    4. Extracts text page-by-page preserving physical page numbers.
    5. Chunks text (~400 chars, ~50 chars overlap) strictly within page boundaries.
    6. Persists Document and DocumentChunk records.
    """
    # 1. Verify subject ownership
    subject = _verify_subject_ownership(db, subject_id, current_user.id)

    # 2. Read and validate content
    try:
        content = file.file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded file: {str(e)}",
        )

    original_name = file.filename or "uploaded_document.pdf"
    try:
        validate_pdf_content(content, original_name)
    except PDFValidationError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )

    # 3. Store PDF safely with UUID filename
    doc_id, file_path = save_uploaded_pdf(content)

    # 4. Create Document record
    doc = Document(
        id=doc_id,
        subject_id=subject.id,
        filename=original_name,
        file_path=file_path,
        page_count=0,
        status="processing",
        error_message=None,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # 5. Extract and chunk page-by-page
    try:
        page_count, chunks, is_extractable = extract_and_chunk_pdf(file_path)

        doc.page_count = page_count

        if not is_extractable:
            doc.status = "failed"
            doc.error_message = "No extractable text found in PDF. Scanned or image-only PDFs without text layers are not supported."
            db.commit()
            db.refresh(doc)
            logger.info("PDF '%s' has zero extractable text; marked failed.", doc.id)
            return {"data": _doc_to_dict(doc)}

        # Persist document chunks
        db_chunks = [
            DocumentChunk(
                document_id=doc.id,
                page_number=c["page_number"],
                chunk_index=c["chunk_index"],
                text=c["text"],
                embedding=[0.0] * 384,  # Phase 1 schema zero-vector placeholder until Phase 6
            )
            for c in chunks
        ]
        db.add_all(db_chunks)

        doc.status = "completed"
        doc.error_message = None
        db.commit()
        db.refresh(doc)

        # Generate and persist vector embeddings for semantic search (Phase 8 integration)
        try:
            from app.services.vector_storage import store_chunks_embeddings_batch
            store_chunks_embeddings_batch(db, db_chunks, force=True)
            logger.info("Generated and stored vector embeddings for %d document chunks (doc '%s')", len(db_chunks), doc.id)
        except Exception as emb_err:
            logger.error("Failed to generate embeddings for document chunks of doc %s: %s", doc.id, emb_err, exc_info=True)

        logger.info("Successfully ingested PDF '%s' with %d pages and %d chunks", doc.id, page_count, len(chunks))
        return {"data": _doc_to_dict(doc)}

    except Exception as e:
        logger.error("Processing failed for document '%s': %s", doc.id, e)
        db.rollback()
        doc.status = "failed"
        doc.error_message = f"Processing error: {str(e)}"
        db.commit()
        db.refresh(doc)
        return {"data": _doc_to_dict(doc)}


@router.get(
    "/study-materials",
    status_code=status.HTTP_200_OK,
)
def list_study_materials(
    subject_id: Optional[uuid.UUID] = Query(None, description="Filter by Subject UUID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lists uploaded study materials for the current user.
    Optionally filters by subject_id. Enforces ownership isolation.
    """
    query = (
        select(Document)
        .join(Subject, Document.subject_id == Subject.id)
        .where(Subject.user_id == current_user.id)
    )

    if subject_id:
        # Verify subject ownership
        _verify_subject_ownership(db, subject_id, current_user.id)
        query = query.where(Document.subject_id == subject_id)

    query = query.order_by(desc(Document.created_at))
    docs = db.execute(query).scalars().all()

    return {"data": [_doc_to_dict(d) for d in docs]}


@router.get(
    "/study-materials/{document_id}",
    status_code=status.HTTP_200_OK,
)
def get_study_material(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieves document details. Enforces ownership chain: current_user -> Subject -> Document."""
    doc = _verify_document_ownership(db, document_id, current_user.id)
    return {"data": _doc_to_dict(doc)}


@router.get(
    "/study-materials/{document_id}/pages/{page_number}",
    status_code=status.HTTP_200_OK,
)
def get_study_material_page(
    document_id: uuid.UUID,
    page_number: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieves the text content of a specific physical page (1-indexed).
    Combines all chunks extracted from that physical page.
    """
    doc = _verify_document_ownership(db, document_id, current_user.id)

    chunks = db.execute(
        select(DocumentChunk)
        .where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.page_number == page_number,
        )
        .order_by(DocumentChunk.chunk_index.asc())
    ).scalars().all()

    combined_text = "\n\n".join(c.text for c in chunks) if chunks else ""

    page_data = {
        "page_number": page_number,
        "text": combined_text,
        "chunk_count": len(chunks),
    }

    # Support both direct payload and wrapped in .data for frontend compatibility
    return {
        **page_data,
        "data": page_data,
    }


@router.get(
    "/study-materials/{document_id}/chunks",
    status_code=status.HTTP_200_OK,
)
def get_study_material_chunks(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieves all stored chunks for a document, preserving page provenance and chunk order."""
    doc = _verify_document_ownership(db, document_id, current_user.id)

    chunks = db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.page_number.asc(), DocumentChunk.chunk_index.asc())
    ).scalars().all()

    chunk_list = [
        {
            "id": str(c.id),
            "document_id": str(c.document_id),
            "page_number": c.page_number,
            "chunk_index": c.chunk_index,
            "text": c.text,
            "created_at": c.created_at.isoformat(),
        }
        for c in chunks
    ]

    return {"data": chunk_list}


@router.delete(
    "/study-materials/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_study_material(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Deletes a document:
    1. Verifies ownership.
    2. Deletes stored PDF file from filesystem safely.
    3. Deletes Document database row (foreign key cascade removes DocumentChunks).
    """
    doc = _verify_document_ownership(db, document_id, current_user.id)

    # 1. Clean up stored file
    delete_stored_pdf(doc.file_path)

    # 2. Delete database record (cascade deletes chunks)
    db.delete(doc)
    db.commit()

    logger.info("Deleted document '%s' and all associated chunks", document_id)
    return None
