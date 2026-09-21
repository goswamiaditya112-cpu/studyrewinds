import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


class PlaylistCreateRequest(BaseModel):
    subject_id: uuid.UUID = Field(..., description="UUID of the Subject to attach the playlist to")
    playlist_url: Optional[str] = Field(None, description="Public YouTube playlist URL or ID")
    url: Optional[str] = Field(None, description="Alternative alias for playlist_url for frontend compatibility")

    @model_validator(mode="after")
    def validate_url_provided(self) -> "PlaylistCreateRequest":
        raw_url = self.playlist_url or self.url
        if not raw_url or not raw_url.strip():
            raise ValueError("A YouTube playlist URL or ID is required.")
        # Store normalized URL in playlist_url
        self.playlist_url = raw_url.strip()
        return self


class VideoResponse(BaseModel):
    id: uuid.UUID
    playlist_id: uuid.UUID
    youtube_video_id: str
    title: str
    duration_seconds: Optional[int] = None
    transcript_source: str = "none"
    status: str = "pending"
    transcript_status: str = "pending"
    error_message: Optional[str] = None
    number: Optional[int] = None
    video_url: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PlaylistResponse(BaseModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    youtube_playlist_id: str
    title: str
    status: str
    video_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class PlaylistDetailResponse(BaseModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    youtube_playlist_id: str
    title: str
    status: str
    video_count: int = 0
    created_at: datetime
    videos: List[VideoResponse] = []

    model_config = {"from_attributes": True}
