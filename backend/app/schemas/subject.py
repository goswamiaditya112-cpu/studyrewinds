import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator

class SubjectCreateRequest(BaseModel):
    name: str = Field(..., max_length=255, description="Name of the subject")
    description: Optional[str] = Field(None, max_length=2000, description="Optional subject description")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Subject name cannot be empty or whitespace only")
        if len(cleaned) > 255:
            raise ValueError("Subject name cannot exceed 255 characters")
        return cleaned

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            return cleaned if cleaned else None
        return None

class SubjectUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=255, description="Updated name of the subject")
    description: Optional[str] = Field(None, max_length=2000, description="Updated description")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("Subject name cannot be empty or whitespace only")
            if len(cleaned) > 255:
                raise ValueError("Subject name cannot exceed 255 characters")
            return cleaned
        return None

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            return cleaned if cleaned else None
        return None

class SubjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}

class SubjectSummaryResponse(BaseModel):
    playlist_count: int = 0
    material_count: int = 0
    processed_video_count: int = 0
