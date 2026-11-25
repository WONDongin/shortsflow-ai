# 영상 메타데이터와 API 응답 구조
from uuid import UUID

from pydantic import BaseModel, Field

# 영상 길이, 해상도, 프레임률, 코덱, 음성 트랙 정보 검증
class VideoMetadata(BaseModel):
    duration_seconds: float = Field(gt=0, allow_inf_nan=False)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0, allow_inf_nan=False)
    video_codec: str = Field(min_length=1)
    has_audio: bool


# 업로드·조회 응답에 사용할 UUID, 용량, 메타데이터, 결과물 경로
class VideoResult(BaseModel):
    video_id: UUID
    size_bytes: int
    metadata: VideoMetadata
    audio_path: str | None = None
    frame_path: str | None = None
    transcript_path: str | None = None


# 추출 응답에 사용할 영상 UUID와 결과물 상대 경로
class ExtractionResult(BaseModel):
    video_id: UUID
    path: str


class TranscriptSegment(BaseModel):
    start_seconds: float = Field(ge=0, allow_inf_nan=False)
    end_seconds: float = Field(gt=0, allow_inf_nan=False)
    text: str


class Transcript(BaseModel):
    video_id: UUID
    language: str
    segments: list[TranscriptSegment]
