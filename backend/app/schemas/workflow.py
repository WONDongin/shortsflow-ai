# n8n 진행 상태 조회·콜백 요청 모델
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

# 시작·진행·종료 단계 정의
WorkflowUpdateStage = Literal[
    "extracting", "transcribing", "analyzing", "rendering", "completed", "no_candidate", "failed"
]
WorkflowStage = Literal["queued", WorkflowUpdateStage]


# 프론트에 전달할 진행 단계와 결과 정보
class WorkflowStatus(BaseModel):
    video_id: UUID
    stage: WorkflowStage
    analysis_id: UUID | None
    error: str | None


# n8n 콜백의 단계별 필수 값 검증
class WorkflowUpdate(BaseModel):
    stage: WorkflowUpdateStage
    analysis_id: UUID | None = None
    error: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_result(self) -> "WorkflowUpdate":
        if self.stage in ("rendering", "completed", "no_candidate") and self.analysis_id is None:
            raise ValueError("This stage requires an analysis ID.")
        if self.stage in ("no_candidate", "failed") and not self.error:
            raise ValueError("This stage requires an error message.")
        return self
