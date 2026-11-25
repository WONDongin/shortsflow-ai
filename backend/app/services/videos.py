# 영상 검증·저장·조회·추출 처리
import logging
from os import getenv
from pathlib import Path
from shutil import copyfile, rmtree
from typing import BinaryIO
from uuid import UUID, uuid4

from app.db import get_engine
from app.schemas.video import ExtractionResult, VideoResult
from app.services import video_records
from app.services.media import VideoError, mp4_input, probe_video, run_media
logger = logging.getLogger(__name__)
# 업로드 크기 제한, 저장 경로, 다운로드 형식
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
DEFAULT_STORAGE = Path(__file__).resolve().parents[2] / "storage" / "videos"
DOWNLOADS = {
    "source": ("source.mp4", "video/mp4"),
    "audio": ("audio.wav", "audio/wav"),
    "frame": ("frame.jpg", "image/jpeg"),
    "transcript": ("transcript.json", "application/json"),
}


# UUID별 영상 작업 폴더 경로
def job_directory(video_id: UUID) -> Path:
    return Path(getenv("VIDEO_STORAGE_DIR") or DEFAULT_STORAGE).resolve() / str(video_id)


# DB와 API 응답에 사용할 저장소 기준 상대 경로
def artifact_path(video_id: UUID, filename: str) -> str:
    return f"{video_id}/{filename}"


# MP4 저장 후 분석 결과를 PostgreSQL에 기록
def store_upload(
    file: BinaryIO, filename: str | None, known_size: int | None = None
) -> VideoResult:
    if not filename or Path(filename).suffix.lower() != ".mp4":
        raise VideoError(415, "Upload a file with the .mp4 extension.")
    if len(filename) > 255 or "\x00" in filename:
        raise VideoError(422, "The original filename is invalid.")
    if known_size is not None and known_size > MAX_UPLOAD_BYTES:
        raise VideoError(413, "The video exceeds the 100 MiB upload limit.")

    video_id = uuid4()
    directory = job_directory(video_id)
    directory.mkdir(parents=True)
    source = directory / "source.mp4"
    try:
        size = 0
        with source.open("wb") as output:
            while chunk := file.read(CHUNK_BYTES):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise VideoError(413, "The video exceeds the 100 MiB upload limit.")
                output.write(chunk)
        if not size:
            raise VideoError(422, "The uploaded video is empty.")

        result = VideoResult(video_id=video_id, size_bytes=size, metadata=probe_video(source))
        with get_engine().begin() as connection:
            video_records.insert_video(connection, result, filename, artifact_path(video_id, source.name))
    except Exception:
        # 분석이나 DB 저장 실패 시 신규 작업 폴더 정리
        try:
            rmtree(directory)
        except OSError:
            logger.exception("Could not clean up video job %s", video_id)
        raise
    logger.info("Stored video job %s (%d bytes)", video_id, size)
    return result


# DB에서 영상 조회, 이전 영상은 metadata.json으로 조회
def get_video(video_id: UUID) -> VideoResult:
    directory = job_directory(video_id)
    result = video_records.find_video(video_id)
    legacy_metadata = directory / "metadata.json"
    if result is None:
        try:
            result = VideoResult.model_validate_json(legacy_metadata.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise VideoError(404, "Video job not found.") from exc

    if legacy_metadata.is_file():
        if result.audio_path is None and (directory / "audio.wav").is_file():
            result.audio_path = artifact_path(video_id, "audio.wav")
        if result.frame_path is None and (directory / "frame.jpg").is_file():
            result.frame_path = artifact_path(video_id, "frame.jpg")
    transcript_filename = DOWNLOADS["transcript"][0]
    if (directory / transcript_filename).is_file():
        result.transcript_path = artifact_path(video_id, transcript_filename)
    return result


# 결과물 생성 여부와 실제 파일 확인
def download_file(video_id: UUID, kind: str) -> tuple[Path, str]:
    video = get_video(video_id)
    filename, media_type = DOWNLOADS[kind]
    path = job_directory(video_id) / filename
    if (kind != "source" and getattr(video, f"{kind}_path") is None) or not path.is_file():
        raise VideoError(404, "The requested video file is not available.")
    return path, media_type


# 음성 트랙 확인 후 16kHz 모노 WAV 추출
def extract_audio(video_id: UUID) -> ExtractionResult:
    video = get_video(video_id)
    if not video.metadata.has_audio:
        raise VideoError(422, "The video does not contain an audio track.")
    return extract(
        video, "AUDIO", "audio.wav",
        ["-map", "0:a:0", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le"],
    )


# 영상 길이 범위 확인 후 JPG 추출
def extract_frame(video_id: UUID, timestamp_seconds: float = 0) -> ExtractionResult:
    video = get_video(video_id)
    if not 0 <= timestamp_seconds < video.metadata.duration_seconds:
        raise VideoError(422, "The frame timestamp must be within the video duration.")
    return extract(
        video, "FRAME", "frame.jpg",
        [
            "-ss", f"{timestamp_seconds:.9f}", "-map", "0:V:0",
            "-frames:v", "1", "-c:v", "mjpeg", "-update", "1",
        ],
        timestamp_seconds=timestamp_seconds,
    )


# 임시 결과물 생성 후 파일 교체와 DB 갱신
def extract(
    video: VideoResult, kind: str, filename: str, options: list[str],
    *, timestamp_seconds: float | None = None,
) -> ExtractionResult:
    video_id = video.video_id
    directory = job_directory(video_id)
    target = directory / filename
    pending = directory / f".{uuid4()}{target.suffix}"
    try:
        # FFmpeg로 임시 결과물 생성 및 출력 확인
        run_media(
            "ffmpeg",
            [
                "-nostdin", "-v", "error", "-xerror",
                *mp4_input(directory / "source.mp4"),
                *options, str(pending),
            ],
            timeout=180,
        )
        if not pending.is_file() or pending.stat().st_size == 0:
            raise VideoError(422, "No media could be extracted at the requested position.")
        relative_path = artifact_path(video_id, filename)
        # 같은 영상·유형의 작업 잠금 및 기존 파일 백업
        with video_records.lock_artifact(video_id, kind) as connection:
            backup = pending.with_name(f"{pending.name}.bak")
            published = False
            preserve_backup = False
            try:
                with connection.begin():
                    if (directory / "metadata.json").is_file():
                        # 이전 영상에는 원본 파일명 기록 없음
                        video_records.insert_video(
                            connection, video, "source.mp4", artifact_path(video_id, "source.mp4"), legacy=True
                        )
                    video_records.upsert_artifact(connection, video_id, kind, relative_path, timestamp_seconds)
                    if target.is_file():
                        copyfile(target, backup)
                    pending.replace(target)
                    published = True
            except Exception:
                # DB 저장 실패 시 기존 파일 복원 또는 새 파일 제거
                if published:
                    try:
                        if backup.is_file():
                            backup.replace(target)
                        else:
                            target.unlink()
                    except OSError:
                        preserve_backup = True
                        raise
                raise
            finally:
                if not preserve_backup:
                    # 백업 정리 실패 시 로그만 기록
                    try:
                        backup.unlink(missing_ok=True)
                    except OSError:
                        logger.warning("Could not remove extraction backup for %s", video_id)
    finally:
        pending.unlink(missing_ok=True)
    logger.info("Created %s for video job %s", filename, video_id)
    return ExtractionResult(video_id=video_id, path=relative_path)
