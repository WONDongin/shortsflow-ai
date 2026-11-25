# 자막 분석 입력·쇼츠 후보·분석 결과 모델
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.video import Transcript, TranscriptSegment


# 저장된 자막 구간과 기존 구간 ID
class SavedAnalysisSegment(TranscriptSegment):
    segment_id: int | None = Field(default=None, strict=True)


class AnalysisTranscript(Transcript):
    segments: list[SavedAnalysisSegment]


# 모델이 선택하는 구간 ID 범위와 쇼츠 문구
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


# 선택 구간에 원본 영상 기준 시작·종료 시각 추가
class ShortsCandidate(SegmentSelection):
    start_seconds: float
    end_seconds: float


# 분석 상태와 실패 코드 정의
AnalysisStatus = Literal["queued", "running", "succeeded", "no_candidate", "failed"]
FailureCode = Literal[
    "transcript_not_ready", "invalid_transcript", "input_too_long",
    "api_error", "invalid_segment", "interrupted", "internal_error",
]


class AnalysisIssue(BaseModel):
    code: FailureCode
    message: str


# 분석 상태·후보·오류 조회 응답
class AnalysisResult(BaseModel):
    analysis_id: UUID
    video_id: UUID
    status: AnalysisStatus
    candidate: ShortsCandidate | None
    error: AnalysisIssue | None
    created_at: datetime
    updated_at: datetime
