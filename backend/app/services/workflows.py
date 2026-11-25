# n8n 웹훅 호출과 PostgreSQL 워크플로우 상태 관리
import logging
from os import getenv
from uuid import UUID, uuid4

import httpx
from dotenv import dotenv_values
from sqlalchemy import text

from app.db import ENV_FILE, get_engine
from app.schemas.workflow import WorkflowStatus, WorkflowUpdate
from app.services.media import VideoError

logger = logging.getLogger(__name__)
RESULT = "video_id, stage, analysis_id, error"
# 콜백으로 전환할 수 있는 이전 단계 목록
PREVIOUS_STAGE = {
    "extracting": ("queued",),
    "transcribing": ("extracting",),
    "analyzing": ("transcribing",),
    "rendering": ("analyzing",),
    "completed": ("rendering",),
    "no_candidate": ("analyzing",),
    "failed": ("extracting", "transcribing", "analyzing", "rendering"),
}


# 시간 초과 작업을 실패 처리하고 저장된 상태 조회
def read_workflow(video_id: UUID) -> WorkflowStatus:
    with get_engine().begin() as connection:
        # 단계별 제한 시간을 넘긴 작업을 실패로 기록
        connection.execute(
            text("""
                UPDATE shortsflow_app.video_workflows
                SET stage = 'failed', error = 'n8n 진행 상태를 기다리는 시간이 초과되었습니다.',
                    updated_at = clock_timestamp()
                WHERE video_id = :video_id AND updated_at + CASE stage
                    WHEN 'queued' THEN interval '1 minute'
                    WHEN 'extracting' THEN interval '4 minutes'
                    WHEN 'transcribing' THEN interval '26 minutes'
                    WHEN 'analyzing' THEN interval '11 minutes'
                    WHEN 'rendering' THEN interval '6 minutes'
                END <= clock_timestamp()
            """),
            {"video_id": video_id},
        )
        row = connection.execute(
            text(f"SELECT {RESULT} FROM shortsflow_app.video_workflows WHERE video_id = :video_id"),
            {"video_id": video_id},
        ).mappings().one_or_none()
    if row is None:
        raise VideoError(404, "No workflow was started for this video.")
    return WorkflowStatus.model_validate(row)


# 최초 요청의 워크플로우만 등록하고 n8n 웹훅 호출
def start_workflow(video_id: UUID) -> WorkflowStatus:
    token = uuid4()
    params = {"video_id": video_id, "token": token}
    with get_engine().begin() as connection:
        created = connection.execute(
            text("""
                INSERT INTO shortsflow_app.video_workflows (video_id, callback_token, stage)
                SELECT id, :token, 'queued' FROM shortsflow_app.videos WHERE id = :video_id
                ON CONFLICT (video_id) DO NOTHING RETURNING video_id
            """),
            params,
        ).scalar_one_or_none()
    # 새 작업의 영상 UUID와 콜백 토큰을 n8n에 전달
    if created is not None:
        settings = dotenv_values(ENV_FILE, interpolate=False, encoding="utf-8-sig")
        webhook = getenv("N8N_WEBHOOK_URL") or settings.get("N8N_WEBHOOK_URL")
        try:
            with httpx.Client(timeout=10, trust_env=False) as client:
                client.post(
                    webhook or "http://127.0.0.1:5678/webhook/shortsflow",
                    json={"video_id": str(video_id), "callback_token": str(token)},
                ).raise_for_status()
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            logger.warning("n8n webhook dispatch failed for %s (%s)", video_id, type(exc).__name__)
            with get_engine().begin() as connection:
                connection.execute(
                    text("""
                        UPDATE shortsflow_app.video_workflows
                        SET stage = 'failed', error = 'n8n 웹훅에 연결하지 못했습니다. 실행 상태와 Production URL을 확인하세요.',
                            updated_at = clock_timestamp()
                        WHERE video_id = :video_id AND callback_token = :token AND stage = 'queued'
                    """),
                    params,
                )
    return read_workflow(video_id)


# 콜백 토큰·단계 순서·분석 소속 확인 후 상태 갱신
def update_workflow(video_id: UUID, token: UUID, update: WorkflowUpdate) -> WorkflowStatus:
    with get_engine().begin() as connection:
        row = connection.execute(
            text(f"""
                UPDATE shortsflow_app.video_workflows AS workflow
                SET stage = :stage, analysis_id = COALESCE(:analysis_id, workflow.analysis_id),
                    error = :error, updated_at = clock_timestamp()
                WHERE workflow.video_id = :video_id AND callback_token = :token
                  AND stage = ANY(:previous)
                  AND (
                    CAST(:analysis_id AS uuid) IS NULL OR EXISTS (
                        SELECT 1 FROM shortsflow_app.video_analyses
                        WHERE id = :analysis_id AND video_id = :video_id
                    )
                  )
                  AND (workflow.analysis_id IS NULL OR CAST(:analysis_id AS uuid) IS NULL
                       OR workflow.analysis_id = :analysis_id)
                RETURNING {RESULT}
            """),
            {
                "video_id": video_id, "token": token, **update.model_dump(),
                "previous": list(PREVIOUS_STAGE[update.stage]),
            },
        ).mappings().one_or_none()
    if row is None:
        raise VideoError(409, "The workflow update could not be applied.")
    return WorkflowStatus.model_validate(row)
