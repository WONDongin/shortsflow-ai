# PostgreSQL 자막 분석 작업 등록·조회·상태 갱신
from uuid import UUID, uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection

from app.db import get_engine
from app.schemas.analysis import AnalysisIssue, AnalysisResult, ShortsCandidate
from app.schemas.video import VideoResult
from app.services import video_records, videos

RESULT_COLUMNS = "id AS analysis_id, video_id, status, candidate, error, created_at, updated_at"
INTERRUPTED = AnalysisIssue(code="interrupted", message="The analysis did not finish within 10 minutes. Request a new analysis.")


# 시간 초과된 대기·실행 분석을 실패로 기록
def expire_active(connection: Connection, video_id: UUID) -> None:
    connection.execute(
        text("""
            UPDATE shortsflow_app.video_analyses
            SET status = 'failed', error = :error, updated_at = clock_timestamp()
            WHERE video_id = :video_id AND status IN ('queued', 'running')
              AND updated_at <= clock_timestamp() - interval '10 minutes'
        """).bindparams(bindparam("error", type_=JSONB)),
        {"video_id": video_id, "error": INTERRUPTED.model_dump()},
    )


# 진행 중인 분석 재사용 또는 새 분석 등록
def request_analysis(video: VideoResult) -> tuple[AnalysisResult, bool]:
    video_id = video.video_id
    params = {"video_id": video_id}
    with get_engine().begin() as connection:
        if (videos.job_directory(video_id) / "metadata.json").is_file():
            video_records.insert_video(
                connection, video, "source.mp4", videos.artifact_path(video_id, "source.mp4"), legacy=True
            )
        # Serialize submissions for this video without holding a lock during the GPT call.
        connection.execute(
            text("SELECT id FROM shortsflow_app.videos WHERE id = :video_id FOR UPDATE"), params
        )
        expire_active(connection, video_id)
        active = connection.execute(
            text(f"""
                SELECT {RESULT_COLUMNS} FROM shortsflow_app.video_analyses
                WHERE video_id = :video_id AND status IN ('queued', 'running')
            """),
            params,
        ).mappings().one_or_none()
        if active is not None:
            return AnalysisResult.model_validate(active), False
        row = connection.execute(
            text(f"""
                INSERT INTO shortsflow_app.video_analyses (id, video_id, status)
                VALUES (:id, :video_id, 'queued') RETURNING {RESULT_COLUMNS}
            """),
            {**params, "id": uuid4()},
        ).mappings().one()
        return AnalysisResult.model_validate(row), True


# 영상별 최신 분석 또는 지정한 분석 조회
def find_analysis(video_id: UUID, analysis_id: UUID | None) -> AnalysisResult | None:
    by_id = "AND id = :id" if analysis_id is not None else ""
    with get_engine().begin() as connection:
        expire_active(connection, video_id)
        row = connection.execute(
            text(f"""
                SELECT {RESULT_COLUMNS} FROM shortsflow_app.video_analyses
                WHERE video_id = :video_id {by_id}
                ORDER BY created_at DESC, id DESC LIMIT 1
            """),
            {"video_id": video_id, "id": analysis_id},
        ).mappings().one_or_none()
    return AnalysisResult.model_validate(row) if row is not None else None


# 대기 중인 분석을 실행 상태로 전환
def start_analysis(analysis_id: UUID) -> bool:
    with get_engine().begin() as connection:
        row = connection.execute(
            text("""
                UPDATE shortsflow_app.video_analyses
                SET status = 'running', updated_at = clock_timestamp()
                WHERE id = :id AND status = 'queued'
                  AND updated_at > clock_timestamp() - interval '10 minutes'
                RETURNING id
            """),
            {"id": analysis_id},
        ).scalar_one_or_none()
    return row is not None


# 후보 유무와 오류에 따른 분석 종료 상태 저장
def finish_analysis(
    analysis_id: UUID, candidate: ShortsCandidate | None, error: AnalysisIssue | None
) -> None:
    status = "no_candidate"
    if error is not None:
        status = "failed"
    elif candidate is not None:
        status = "succeeded"
    with get_engine().begin() as connection:
        connection.execute(
            text("""
                UPDATE shortsflow_app.video_analyses
                SET status = :status, candidate = :candidate, error = :error,
                    updated_at = clock_timestamp()
                WHERE id = :id AND status = 'running'
            """).bindparams(
                bindparam("candidate", type_=JSONB(none_as_null=True)),
                bindparam("error", type_=JSONB(none_as_null=True)),
            ),
            {
                "id": analysis_id, "status": status,
                "candidate": candidate.model_dump() if candidate is not None else None,
                "error": error.model_dump() if error is not None else None,
            },
        )
