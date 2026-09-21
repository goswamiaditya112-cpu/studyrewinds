"""
Pydantic Schemas for Semantic Search API (Phase 9)
Defines search request validation and structured response schemas
with YouTube and PDF chunk provenance preservation.
"""

import uuid
from typing import List, Literal, Union
from pydantic import BaseModel, Field, field_validator


class SearchRequest(BaseModel):
    """Search request schema with strict input validation."""
    query: str = Field(..., description="User search query string")
    top_k: int = Field(default=5, ge=1, le=50, description="Maximum number of results to retrieve (1-50)")

    @field_validator("query")
    @classmethod
    def validate_query_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Search query cannot be empty or whitespace-only.")
        return v.strip()


class YouTubeVideoInfo(BaseModel):
    """Metadata identifying the source YouTube video."""
    id: uuid.UUID
    youtube_video_id: str
    title: str


class YouTubeTranscriptInfo(BaseModel):
    """Timestamped transcript content."""
    text: str
    start_time: float
    end_time: float


class YouTubeSearchResult(BaseModel):
    """SearchResult item representing a YouTube transcript chunk."""
    source_type: Literal["youtube"] = "youtube"
    score: float = Field(..., description="Semantic relevance score (higher is more similar)")
    chunk_id: uuid.UUID
    video: YouTubeVideoInfo
    transcript: YouTubeTranscriptInfo


class PDFDocumentInfo(BaseModel):
    """Metadata identifying the source PDF document."""
    id: uuid.UUID
    filename: str


class PDFSearchResult(BaseModel):
    """SearchResult item representing a PDF document chunk."""
    source_type: Literal["pdf"] = "pdf"
    score: float = Field(..., description="Semantic relevance score (higher is more similar)")
    chunk_id: uuid.UUID
    document: PDFDocumentInfo
    page_number: int
    chunk_index: int
    text: str


SearchResultItem = Union[YouTubeSearchResult, PDFSearchResult]


class SearchResponse(BaseModel):
    """Unified semantic search API response."""
    query: str
    subject_id: uuid.UUID
    total_results: int
    results: List[SearchResultItem]
