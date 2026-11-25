from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.video import Transcript, TranscriptSegment


class SavedAnalysisSegment(TranscriptSegment):
    segment_id: int | None = Field(default=None, strict=True)


class AnalysisTranscript(Transcript):
    segments: list[SavedAnalysisSegment]


class SegmentSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    start_segment_id: int
    end_segment_id: int
    title: str
    thumbnail_text: str
    reason: str


class ContentSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    candidate: SegmentSelection | None


class ShortsCandidate(SegmentSelection):
    start_seconds: float
    end_seconds: float


AnalysisStatus = Literal["queued", "running", "succeeded", "no_candidate", "failed"]
FailureCode = Literal[
    "transcript_not_ready", "invalid_transcript", "input_too_long",
    "api_error", "invalid_segment", "interrupted", "internal_error",
]


class AnalysisIssue(BaseModel):
    code: FailureCode
    message: str


class AnalysisResult(BaseModel):
    analysis_id: UUID
    video_id: UUID
    status: AnalysisStatus
    candidate: ShortsCandidate | None
    error: AnalysisIssue | None
    created_at: datetime
    updated_at: datetime
