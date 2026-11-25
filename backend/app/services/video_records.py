# PostgreSQL 영상·결과물 조회 및 저장 SQL
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db import get_engine
from app.schemas.video import VideoResult


# 영상 UUID, 원본 파일명, 경로, 메타데이터 저장
def insert_video(
    connection: Connection, video: VideoResult, filename: str, path: str, *, legacy: bool = False
) -> None:
    conflict = " ON CONFLICT (id) DO NOTHING" if legacy else ""
    connection.execute(
        text("""
            INSERT INTO shortsflow_app.videos (
                id, original_filename, file_path, file_size, duration_seconds,
                width, height, fps, video_codec, has_audio
            ) VALUES (
                :id, :filename, :path, :size, :duration_seconds,
                :width, :height, :fps, :video_codec, :has_audio
            )
        """ + conflict),
        {
            "id": video.video_id, "filename": filename, "path": path,
            "size": video.size_bytes, **video.metadata.model_dump(),
        },
    )


# UUID로 영상 정보와 결과물 경로 조회
def find_video(video_id: UUID) -> VideoResult | None:
    with get_engine().connect() as connection:
        row = connection.execute(
            text("""
                SELECT v.id, v.file_size, v.duration_seconds, v.width, v.height,
                       v.fps, v.video_codec, v.has_audio,
                       audio.file_path AS audio_path,
                       frame.file_path AS frame_path
                FROM shortsflow_app.videos AS v
                LEFT JOIN shortsflow_app.video_artifacts AS audio
                  ON audio.video_id = v.id AND audio.artifact_type = 'AUDIO'
                LEFT JOIN shortsflow_app.video_artifacts AS frame
                  ON frame.video_id = v.id AND frame.artifact_type = 'FRAME'
                WHERE v.id = :id
            """),
            {"id": video_id},
        ).mappings().one_or_none()
    if row is None:
        return None
    return VideoResult.model_validate({
        "video_id": row["id"], "size_bytes": row["file_size"], "metadata": dict(row),
        "audio_path": row["audio_path"], "frame_path": row["frame_path"],
    })


# 같은 영상·유형의 결과물 갱신 잠금
@contextmanager
def lock_artifact(video_id: UUID, kind: str) -> Iterator[Connection]:
    # DB 커밋 또는 파일 복원 완료까지 잠금 유지
    key = {"key": f"shortsflow_app:{video_id}:{kind}"}
    with get_engine().connect() as connection:
        try:
            connection.execute(text("SELECT pg_advisory_lock(hashtextextended(:key, 0))"), key)
            connection.commit()
            yield connection
        finally:
            if not connection.invalidated:
                try:
                    connection.rollback()
                    # 커밋 실패 후 드라이버에 남은 트랜잭션 롤백
                    connection.connection.rollback()
                    connection.execute(
                        text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"), key
                    )
                    connection.commit()
                except Exception:
                    # 잠금 해제 실패 시 연결 풀에서 해당 연결 폐기
                    connection.invalidate()


# 영상 UUID와 유형 기준으로 결과물 경로·추출 시점 갱신
def upsert_artifact(
    connection: Connection, video_id: UUID, kind: str, path: str, timestamp: float | None
) -> None:
    connection.execute(
        text("""
            INSERT INTO shortsflow_app.video_artifacts (video_id, artifact_type, file_path, timestamp_seconds)
            VALUES (:id, :kind, :path, :timestamp)
            ON CONFLICT (video_id, artifact_type) DO UPDATE
            SET file_path = EXCLUDED.file_path,
                timestamp_seconds = EXCLUDED.timestamp_seconds,
                updated_at = now()
        """),
        {"id": video_id, "kind": kind, "path": path, "timestamp": timestamp},
    )
