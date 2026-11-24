from uuid import UUID

from pydantic import BaseModel, Field

# Pydantic 응답 모델
class VideoMetadata(BaseModel):
    duration_seconds: float = Field(gt=0, allow_inf_nan=False)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0, allow_inf_nan=False)
    video_codec: str = Field(min_length=1)
    has_audio: bool


class VideoResult(BaseModel):
    video_id: UUID
    size_bytes: int
    metadata: VideoMetadata
    audio_path: str | None = None
    frame_path: str | None = None


class ExtractionResult(BaseModel):
    video_id: UUID
    path: str
