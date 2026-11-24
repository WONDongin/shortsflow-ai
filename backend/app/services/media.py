import json
import logging
import subprocess
from fractions import Fraction
from os import getenv
from pathlib import Path

from app.schemas.video import VideoMetadata

# FFprobe 메타데이터 파싱, subprocess 실행
logger = logging.getLogger(__name__)


class VideoError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code


def run_media(
    tool: str, arguments: list[str], *, timeout: int, invalid_upload: bool = False
) -> str:
    executable = getenv(f"{tool.upper()}_PATH") or tool
    try:
        result = subprocess.run(
            [executable, *arguments],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=True,
        )
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


def mp4_input(path: Path) -> list[str]:
    return ["-protocol_whitelist", "file", "-f", "mov", "-i", str(path)]


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
        streams = data["streams"]
        video = next(
            stream for stream in streams
            if stream.get("codec_type") == "video"
            and not stream.get("disposition", {}).get("attached_pic")
        )
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
