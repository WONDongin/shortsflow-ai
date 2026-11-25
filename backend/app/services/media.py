# FFmpeg·FFprobe 실행과 MP4 메타데이터 분석
import json
import logging
import subprocess
from fractions import Fraction
from math import isfinite
from os import getenv
from pathlib import Path

from app.schemas.video import VideoMetadata

logger = logging.getLogger(__name__)


# 영상 처리 오류의 HTTP 상태 코드와 메시지
class VideoError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code


# 실행 경로와 제한 시간을 적용해 미디어 도구 실행
def run_media(
    tool: str, arguments: list[str], *, timeout: int, invalid_upload: bool = False,
    cwd: Path | None = None,
) -> str:
    executable = getenv(f"{tool.upper()}_PATH") or tool
    if cwd is not None and Path(executable).is_file():
        executable = str(Path(executable).resolve())
    try:
        result = subprocess.run(
            [executable, *arguments],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=cwd,
            check=True,
        )
    # 실행 불가·시간 초과·처리 실패를 API 오류로 변환
    except OSError as exc:
        logger.exception("Could not start %s", tool)
        raise VideoError(503, f"{tool} is unavailable.") from exc
    except subprocess.TimeoutExpired as exc:
        logger.warning("%s exceeded the %d second timeout", tool, timeout)
        raise VideoError(504, f"{tool} processing timed out.") from exc
    except subprocess.CalledProcessError as exc:
        logger.warning("%s exited with code %d", tool, exc.returncode)
        if invalid_upload:
            raise VideoError(422, "The file is not a readable MP4 video.") from exc
        raise VideoError(500, "Video extraction failed.") from exc
    return result.stdout


# 입력 형식을 MOV 계열로 고정하고 로컬 파일만 허용
def mp4_input(path: Path) -> list[str]:
    return ["-protocol_whitelist", "file", "-f", "mov", "-i", str(path)]


# 탐색 시각 보정에 쓸 컨테이너와 영상 시작 차이 계산
def video_seek_offset(path: Path) -> float:
    # Input seeking is relative to the container start. Transcript times start at the video stream.
    output = run_media(
        "ffprobe",
        [
            "-v", "error", *mp4_input(path), "-select_streams", "V:0",
            "-show_entries", "format=start_time:stream=start_time", "-of", "json",
        ],
        timeout=30,
    )
    try:
        data = json.loads(output)
        stream = data["streams"][0]
        container_start = float(data["format"].get("start_time", 0))
        offset = float(stream.get("start_time", container_start)) - container_start
        if not isfinite(offset):
            raise ValueError("Non-finite video offset")
        return offset
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise VideoError(422, "Could not align the clip with the original video timeline.") from exc


# 자막 시각 보정에 쓸 영상과 음성 시작 차이 계산
def audio_start_offset(path: Path) -> float:
    # WAV starts at its first audio sample. Use the same streams as the extractors.
    output = run_media(
        "ffprobe",
        [
            "-v", "error", *mp4_input(path), "-show_entries",
            "stream=codec_type,start_time:stream_disposition=attached_pic", "-of", "json",
        ],
        timeout=30,
    )
    try:
        streams = json.loads(output)["streams"]
        audio = next(stream for stream in streams if stream.get("codec_type") == "audio")
        video = next(
            stream for stream in streams
            if stream.get("codec_type") == "video"
            and not stream.get("disposition", {}).get("attached_pic")
        )
        offset = float(audio["start_time"]) - float(video["start_time"])
        if not isfinite(offset):
            raise ValueError("Non-finite stream start time")
        return offset
    except (KeyError, StopIteration, TypeError, ValueError) as exc:
        raise VideoError(422, "Could not align the WAV with the original video timeline.") from exc


# FFprobe JSON 응답에서 MP4 형식과 영상·음성 스트림 정보 확인
def probe_video(path: Path) -> VideoMetadata:
    output = run_media(
        "ffprobe",
        [
            "-v", "error", *mp4_input(path),
            "-show_entries",
            "format=duration:format_tags=major_brand:"
            "stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate:"
            "stream_disposition=attached_pic",
            "-of", "json",
        ],
        timeout=30,
        invalid_upload=True,
    )
    try:
        data = json.loads(output)
        container = data["format"]
        brand = container["tags"]["major_brand"].strip().lower()
        if not brand or brand.startswith(("qt", "3gp", "3g2", "mj2")):
            raise ValueError("Unsupported MP4 brand")
        # 첨부 이미지를 제외한 첫 영상 스트림 선택
        streams = data["streams"]
        video = next(
            stream for stream in streams
            if stream.get("codec_type") == "video"
            and not stream.get("disposition", {}).get("attached_pic")
        )
        # 평균 프레임률이 없거나 유효하지 않으면 기본 프레임률 사용
        rate = video.get("avg_frame_rate")
        if rate in (None, "0/0", "0/1", "N/A"):
            rate = video["r_frame_rate"]
        return VideoMetadata(
            duration_seconds=float(container["duration"]),
            width=video["width"],
            height=video["height"],
            fps=float(Fraction(rate)),
            video_codec=video["codec_name"],
            has_audio=any(stream.get("codec_type") == "audio" for stream in streams),
        )
    except (KeyError, StopIteration, TypeError, ValueError, ZeroDivisionError) as exc:
        raise VideoError(422, "The file does not contain valid MP4 video metadata.") from exc
