import logging
from os import getenv
from pathlib import Path
from shutil import rmtree
from typing import BinaryIO
from uuid import UUID, uuid4

from app.schemas.video import ExtractionResult, VideoResult
from app.services.media import VideoError, mp4_input, probe_video, run_media
# 파일 검증, UUID별 저장 및 결과물 관리
logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
DEFAULT_STORAGE = Path(__file__).resolve().parents[2] / "storage" / "videos"


def job_directory(video_id: UUID) -> Path:
    return Path(getenv("VIDEO_STORAGE_DIR") or DEFAULT_STORAGE).resolve() / str(video_id)


def artifact_path(video_id: UUID, filename: str) -> str:
    return f"{video_id}/{filename}"


def store_upload(
    file: BinaryIO, filename: str | None, known_size: int | None = None
) -> VideoResult:
    if Path(filename or "").suffix.lower() != ".mp4":
        raise VideoError(415, "Upload a file with the .mp4 extension.")
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
        pending = directory / "metadata.tmp"
        pending.write_text(result.model_dump_json(), encoding="utf-8")
        pending.replace(directory / "metadata.json")
    except Exception:
        try:
            rmtree(directory)
        except OSError:
            logger.exception("Could not clean up video job %s", video_id)
        raise
    logger.info("Stored video job %s (%d bytes)", video_id, size)
    return result


def get_video(video_id: UUID) -> VideoResult:
    directory = job_directory(video_id)
    try:
        payload = (directory / "metadata.json").read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise VideoError(404, "Video job not found.") from exc

    result = VideoResult.model_validate_json(payload)
    if (directory / "audio.wav").is_file():
        result.audio_path = artifact_path(video_id, "audio.wav")
    if (directory / "frame.jpg").is_file():
        result.frame_path = artifact_path(video_id, "frame.jpg")
    return result


def extract_audio(video_id: UUID) -> ExtractionResult:
    if not get_video(video_id).metadata.has_audio:
        raise VideoError(422, "The video does not contain an audio track.")
    return extract(
        video_id, "audio.wav",
        ["-map", "0:a:0", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le"],
    )


def extract_frame(video_id: UUID, timestamp_seconds: float = 0) -> ExtractionResult:
    if not 0 <= timestamp_seconds < get_video(video_id).metadata.duration_seconds:
        raise VideoError(422, "The frame timestamp must be within the video duration.")
    return extract(
        video_id, "frame.jpg",
        [
            "-ss", f"{timestamp_seconds:.9f}", "-map", "0:V:0",
            "-frames:v", "1", "-c:v", "mjpeg", "-update", "1",
        ],
    )


def extract(video_id: UUID, filename: str, options: list[str]) -> ExtractionResult:
    directory = job_directory(video_id)
    target = directory / filename
    pending = directory / f".{uuid4()}{target.suffix}"
    try:
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
        pending.replace(target)
    finally:
        pending.unlink(missing_ok=True)
    logger.info("Created %s for video job %s", filename, video_id)
    return ExtractionResult(video_id=video_id, path=artifact_path(video_id, filename))
