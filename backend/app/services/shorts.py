from decimal import Decimal
from os import getenv
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
from textwrap import fill
from typing import Literal
from uuid import UUID

from app.schemas.video import ShortsResult, TranscriptSegment, VideoResult
from app.services import analysis_records, transcripts, videos
from app.services.media import VideoError, mp4_input, run_media, video_seek_offset

ShortsKind = Literal["shorts", "thumbnail"]
OUTPUTS: dict[ShortsKind, tuple[str, str]] = {
    "shorts": ("shorts.mp4", "video/mp4"),
    "thumbnail": ("thumbnail.jpg", "image/jpeg"),
}
THUMBNAIL_OFFSET = 3
CAPTIONED_FOLDER = "captioned"
PAD_FILTER = "pad=ceil(iw/2)*2:ceil(ih/2)*2"


def output_result(video: VideoResult, analysis_id: UUID, output: Path) -> ShortsResult:
    analysis = analysis_records.find_analysis(video.video_id, analysis_id)
    if analysis is None:
        raise VideoError(404, "Analysis job not found for this video.")
    candidate = analysis.candidate
    if analysis.status != "succeeded" or candidate is None:
        raise VideoError(409, "The analysis must finish with a candidate before generating shorts.")

    start, end = candidate.start_seconds, candidate.end_seconds
    if not 0 <= start < end <= video.metadata.duration_seconds:
        raise VideoError(422, "The analysis timestamps are outside the original video.")
    duration = float(Decimal(str(end)) - Decimal(str(start)))
    offset = THUMBNAIL_OFFSET if duration > THUMBNAIL_OFFSET else duration / 2
    directory = output.relative_to(videos.job_directory(video.video_id)).as_posix()
    return ShortsResult(
        video_id=video.video_id, analysis_id=analysis_id,
        start_seconds=start, end_seconds=end, duration_seconds=duration,
        thumbnail_timestamp_seconds=float(Decimal(str(start)) + Decimal(str(offset))),
        thumbnail_text=candidate.thumbnail_text,
        shorts_path=videos.artifact_path(video.video_id, f"{directory}/{OUTPUTS['shorts'][0]}"),
        thumbnail_path=videos.artifact_path(video.video_id, f"{directory}/{OUTPUTS['thumbnail'][0]}"),
    )


def output_directory(video_id: UUID, analysis_id: UUID) -> Path:
    return videos.job_directory(video_id) / "shorts" / str(analysis_id)


def outputs_available(directory: Path) -> bool:
    return all(path.is_file() and path.stat().st_size > 0 for path in (
        directory / filename for filename, _ in OUTPUTS.values()
    ))


def thumbnail_font() -> Path:
    configured = getenv("THUMBNAIL_FONT_PATH")
    if configured:
        font = Path(configured)
        if font.is_file():
            return font
        raise VideoError(503, "THUMBNAIL_FONT_PATH does not point to a readable font.")

    for font in (
        Path(getenv("SystemRoot", "C:/Windows")) / "Fonts" / "malgunbd.ttf",
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ):
        if font.is_file():
            return font
    raise VideoError(503, "Set THUMBNAIL_FONT_PATH to a font that supports Korean.")


def caption_filter(staging: Path, filename: str, text: str) -> str:
    # Paths are generated locally. Text stays in a UTF-8 file and is rendered literally.
    caption = fill(" ".join(text.split()), width=13)
    (staging / filename).write_text(caption, encoding="utf-8", newline="\n")
    lines = caption.count("\n") + 1
    return (
        f"drawtext=fontfile=font:textfile={filename}:expansion=none:fontcolor=white:"
        f"fontsize=min(w*0.058\\,h*0.65/{lines}):"
        "x=(w-text_w)/2:y=h-text_h-h*0.12:fix_bounds=1:"
        "box=1:boxcolor=black@0.66:boxborderw=12:line_spacing=8"
    )


def subtitle_filters(
    staging: Path, segments: list[TranscriptSegment], start_seconds: float, end_seconds: float
) -> list[str]:
    start = Decimal(str(start_seconds))
    end = Decimal(str(end_seconds))
    cues = sorted(
        (max(start, Decimal(str(segment.start_seconds))) - start,
         min(end, Decimal(str(segment.end_seconds))) - start, segment.text.strip())
        for segment in segments
        if segment.start_seconds < end_seconds and segment.end_seconds > start_seconds and segment.text.strip()
    )
    filters = []
    for index, (cue_start, cue_end, text) in enumerate(cues):
        if index + 1 < len(cues):
            # Keep consecutive captions from drawing over one another on overlapping Whisper timestamps.
            cue_end = min(cue_end, cues[index + 1][0])
        if cue_start < cue_end:
            drawtext = caption_filter(staging, f"subtitle-{index}.txt", text)
            filters.append(f"{drawtext}:enable='gte(t,{cue_start:f})*lt(t,{cue_end:f})'")
    return filters


def generate_shorts(video_id: UUID, analysis_id: UUID) -> ShortsResult:
    video = videos.get_video(video_id)
    output = output_directory(video_id, analysis_id) / CAPTIONED_FOLDER
    result = output_result(video, analysis_id, output)
    if outputs_available(output):
        return result

    source = videos.job_directory(video_id) / videos.DOWNLOADS["source"][0]
    if not source.is_file():
        raise VideoError(404, "The original video file is not available.")
    if not video.metadata.has_audio:
        raise VideoError(422, "The original video does not contain an audio track.")

    transcript = transcripts.get_transcript(video_id)
    if transcript.video_id != video_id:
        raise VideoError(422, "The saved transcript belongs to a different video.")
    font = thumbnail_font()
    source_offset = video_seek_offset(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".render-", dir=output.parent) as temporary:
        staging = Path(temporary)
        rendered = staging / "rendered"
        rendered.mkdir()
        copyfile(font, staging / "font")
        subtitles = subtitle_filters(staging, transcript.segments, result.start_seconds, result.end_seconds)
        if not subtitles:
            raise VideoError(422, "There are no subtitles within the selected clip.")
        (staging / "clip-filter.txt").write_text(",".join([PAD_FILTER, *subtitles]), encoding="utf-8")
        run_media(
            "ffmpeg",
            [
                "-nostdin", "-v", "error", "-xerror",
                "-ss", f"{result.start_seconds + source_offset:.9f}", *mp4_input(source),
                "-t", f"{result.duration_seconds:.9f}", "-map", "0:V:0", "-map", "0:a:0",
                "-c:v", "libx264", "-preset", "fast",
                "-/filter:v", "clip-filter.txt", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-movflags", "+faststart", str(rendered / OUTPUTS["shorts"][0]),
            ],
            timeout=180,
            cwd=staging,
        )
        drawtext = caption_filter(staging, "caption.txt", result.thumbnail_text)
        run_media(
            "ffmpeg",
            [
                "-nostdin", "-v", "error", "-xerror",
                "-ss", f"{result.thumbnail_timestamp_seconds + source_offset:.9f}", *mp4_input(source),
                "-map", "0:V:0", "-frames:v", "1", "-vf", drawtext,
                "-c:v", "mjpeg", "-q:v", "2", "-update", "1", str(rendered / OUTPUTS["thumbnail"][0]),
            ],
            timeout=60,
            cwd=staging,
        )
        if not outputs_available(rendered):
            raise VideoError(422, "The clip or thumbnail could not be generated for this interval.")
        try:
            rendered.rename(output)
        except OSError:
            # Another request may have published the same analysis while this one was rendering.
            if not outputs_available(output):
                raise
    return result


def get_shorts(video_id: UUID, analysis_id: UUID) -> ShortsResult:
    video = videos.get_video(video_id)
    legacy_output = output_directory(video_id, analysis_id)
    captioned_output = legacy_output / CAPTIONED_FOLDER
    output = captioned_output if outputs_available(captioned_output) else legacy_output
    result = output_result(video, analysis_id, output)
    if not outputs_available(output):
        raise VideoError(404, "Shorts files have not been generated for this analysis.")
    return result


def download_file(video_id: UUID, analysis_id: UUID | None, kind: ShortsKind) -> tuple[Path, str]:
    if analysis_id is None:
        raise VideoError(422, "analysis_id is required to download shorts or a thumbnail.")
    result = get_shorts(video_id, analysis_id)
    relative_path = result.shorts_path if kind == "shorts" else result.thumbnail_path
    return videos.job_directory(video_id).parent / relative_path, OUTPUTS[kind][1]
