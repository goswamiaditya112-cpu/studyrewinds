import uuid
from typing import List, Optional
from pydantic import BaseModel, Field


class TranscriptSegmentResponse(BaseModel):
    segment_index: int
    text: str
    start_time_seconds: float
    end_time_seconds: float
    language: Optional[str] = "en"


class VideoTranscriptResponse(BaseModel):
    video_id: uuid.UUID
    transcript_source: str
    chunk_count: int
    data: List[TranscriptSegmentResponse]

    model_config = {"from_attributes": True}


class VideoTranscriptStatusResponse(BaseModel):
    transcript_status: str
    processing_status: str
    transcript_source: str
    processing_error: Optional[str] = None


class VideoTranscriptProcessingResponse(BaseModel):
    transcript_status: str
    processing_status: str
    transcript_source: str
    chunk_count: int = 0
    embedding_status: str = "pending"
    processing_error: Optional[str] = None
    message: Optional[str] = None


class PlaylistTranscriptProcessingResponse(BaseModel):
    message: str
    total: int
    completed: int
    failed: int
    skipped: int = 0
