import io
import os
import uuid
import logging
from typing import List, Dict, Tuple, Optional
import pypdf

from app.core.config import settings

logger = logging.getLogger("studyrewinds.services.pdf")


class PDFValidationError(ValueError):
    """Raised when an uploaded file fails PDF validation."""
    pass


def validate_pdf_content(file_bytes: bytes, original_filename: str) -> None:
    """
    Validates that the file:
    - Exists and is not empty
    - Has .pdf extension (case-insensitive)
    - Does not exceed MAX_UPLOAD_SIZE_BYTES
    - Starts with valid PDF magic bytes (%PDF-)
    - Can be successfully parsed by pypdf as a readable PDF
    """
    if not file_bytes or len(file_bytes) == 0:
        raise PDFValidationError("The uploaded file is empty.")

    if len(file_bytes) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise PDFValidationError(
            f"File size exceeds maximum allowed limit of {settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB."
        )

    ext = os.path.splitext(original_filename)[1].lower()
    if ext != ".pdf":
        raise PDFValidationError(f"Invalid file extension '{ext}'. Only .pdf files are permitted.")

    # Check PDF magic bytes (%PDF-)
    if not file_bytes.startswith(b"%PDF-"):
        raise PDFValidationError("File content does not appear to be a valid PDF (invalid magic header).")

    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        if len(reader.pages) == 0:
            raise PDFValidationError("The PDF file contains zero pages.")
    except Exception as e:
        logger.warning("pypdf failed to parse uploaded file '%s': %s", original_filename, e)
        raise PDFValidationError(f"Corrupt or unreadable PDF document: {str(e)}")


def save_uploaded_pdf(file_bytes: bytes) -> Tuple[uuid.UUID, str]:
    """
    Safely stores an uploaded PDF in the configured project storage directory.
    Uses a generated UUID to prevent directory traversal and collision attacks.
    Returns:
        (document_uuid, absolute_file_path)
    """
    os.makedirs(settings.STORAGE_DIR, exist_ok=True)
    doc_id = uuid.uuid4()
    safe_filename = f"{doc_id}.pdf"
    file_path = os.path.abspath(os.path.join(settings.STORAGE_DIR, safe_filename))

    # Verify that the resolved file_path is strictly within settings.STORAGE_DIR (path traversal defense)
    if not file_path.startswith(os.path.abspath(settings.STORAGE_DIR)):
        raise PDFValidationError("Invalid storage path generated (path traversal detected).")

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    logger.info("Safely stored document '%s' to '%s'", doc_id, file_path)
    return doc_id, file_path


def delete_stored_pdf(file_path: str) -> None:
    """Safely removes a stored PDF file from the filesystem."""
    try:
        if file_path and os.path.isfile(file_path):
            # Verify file is inside STORAGE_DIR before deleting
            if os.path.abspath(file_path).startswith(os.path.abspath(settings.STORAGE_DIR)):
                os.remove(file_path)
                logger.info("Successfully deleted stored PDF file '%s'", file_path)
            else:
                logger.warning("Refused to delete file outside storage directory: '%s'", file_path)
    except Exception as e:
        logger.error("Failed to delete stored PDF file '%s': %s", file_path, e)


def chunk_page_text(
    raw_text: str,
    page_number: int,
    chunk_size: int = 400,
    overlap: int = 50,
) -> List[Dict]:
    """
    Chunks text within a single page.
    Target: ~400 characters, ~50 character overlap.
    Guarantees that chunks NEVER cross page boundaries.
    """
    cleaned = " ".join(raw_text.split()).strip()
    if not cleaned:
        return []

    if len(cleaned) <= chunk_size:
        return [{
            "page_number": page_number,
            "chunk_index": 0,
            "text": cleaned,
        }]

    chunks: List[Dict] = []
    start = 0
    chunk_idx = 0
    total_len = len(cleaned)

    while start < total_len:
        end = min(start + chunk_size, total_len)

        # Snap to word boundary if not at end of page text
        if end < total_len:
            space_pos = cleaned.rfind(" ", start, end)
            if space_pos > start + (chunk_size // 2):
                end = space_pos

        chunk_str = cleaned[start:end].strip()
        if chunk_str:
            chunks.append({
                "page_number": page_number,
                "chunk_index": chunk_idx,
                "text": chunk_str,
            })
            chunk_idx += 1

        if end >= total_len:
            break

        # Move forward, respecting overlap
        start = max(end - overlap, start + 1)
        # Align start with word boundary
        if start < total_len:
            next_space = cleaned.find(" ", start, min(start + 25, total_len))
            if next_space != -1 and next_space < total_len - 1:
                start = next_space + 1

    return chunks


def extract_and_chunk_pdf(
    file_path: str,
    chunk_size: int = 400,
    overlap: int = 50,
) -> Tuple[int, List[Dict], bool]:
    """
    Extracts text page-by-page from a stored PDF and chunks it.
    
    Returns:
        (page_count, chunks, is_extractable)
    
    Rules:
    - page_count is the physical page count of the PDF.
    - Physical page numbers are 1-indexed (1, 2, 3...).
    - Empty pages contribute to page_count, but produce 0 chunks.
    - Chunks never span across page boundaries.
    - If 0 text is extractable across all pages, is_extractable is False (scanned/image-only).
    """
    reader = pypdf.PdfReader(file_path)
    page_count = len(reader.pages)
    all_chunks: List[Dict] = []

    for page_idx in range(page_count):
        physical_page_num = page_idx + 1
        page = reader.pages[page_idx]
        text = page.extract_text() or ""
        
        page_chunks = chunk_page_text(
            raw_text=text,
            page_number=physical_page_num,
            chunk_size=chunk_size,
            overlap=overlap,
        )
        all_chunks.extend(page_chunks)

    is_extractable = len(all_chunks) > 0
    logger.info(
        "Extracted PDF '%s': %d pages, %d chunks, extractable=%s",
        file_path, page_count, len(all_chunks), is_extractable
    )
    return page_count, all_chunks, is_extractable
