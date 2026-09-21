import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    filename: str
    page_count: int = 0
    status: str = "pending"
    processing_error: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentChunkResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    chunk_index: int
    text: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentPageResponse(BaseModel):
    page_number: int
    text: str
    chunk_count: int = 0


class DocumentDetailResponse(BaseModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    filename: str
    page_count: int = 0
    status: str = "pending"
    processing_error: Optional[str] = None
    created_at: datetime
    chunk_count: int = 0
    chunks: List[DocumentChunkResponse] = []

    model_config = {"from_attributes": True}
