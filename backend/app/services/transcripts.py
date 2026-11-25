import logging
from os import getenv
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.schemas.video import Transcript, TranscriptSegment
from app.services import videos
from app.services.media import VideoError, audio_start_offset

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)
_model: "WhisperModel | None" = None
_model_lock = Lock()


def get_model() -> "WhisperModel":
    global _model
    with _model_lock:
        if _model is None:
            try:
                from faster_whisper import WhisperModel

                model_name = getenv("WHISPER_MODEL") or "small"
                _model = WhisperModel(model_name, device="cpu", compute_type="int8")
            except Exception as exc:
                logger.exception("Could not load the Whisper model")
                raise VideoError(503, "Whisper model could not be loaded.") from exc
        return _model


def recognize_audio(
    model: "WhisperModel", video_id: UUID, audio: Path, offset: float, *, vad_filter: bool
) -> Transcript:
    segments, info = model.transcribe(str(audio), vad_filter=vad_filter)
    aligned_segments = []
    for segment in segments:
        text = segment.text.strip()
        start = round(max(0.0, segment.start + offset), 6)
        end = round(segment.end + offset, 6)
        if text and end > start:
            aligned_segments.append(TranscriptSegment(start_seconds=start, end_seconds=end, text=text))
    return Transcript(video_id=video_id, language=info.language, segments=aligned_segments)


def transcribe_video(video_id: UUID) -> Transcript:
    video = videos.get_video(video_id)
    directory = videos.job_directory(video_id)
    audio = directory / "audio.wav"
    source = directory / "source.mp4"
    if video.audio_path is None or not audio.is_file():
        raise VideoError(409, "Extract the WAV audio before generating a transcript.")
    if not source.is_file():
        raise VideoError(404, "The original video file is not available.")

    offset = audio_start_offset(source)
    model = get_model()
    try:
        transcript = recognize_audio(model, video_id, audio, offset, vad_filter=True)
        if not transcript.segments:
            # Singing over music can be removed entirely by the speech filter.
            logger.info("Retrying transcription without VAD for video job %s", video_id)
            transcript = recognize_audio(model, video_id, audio, offset, vad_filter=False)
    except Exception as exc:
        logger.exception("Whisper transcription failed for video job %s", video_id)
        raise VideoError(500, "Whisper could not transcribe the WAV audio.") from exc

    filename = videos.DOWNLOADS["transcript"][0]
    save_transcript(directory / filename, transcript)
    return transcript


def save_transcript(target: Path, transcript: Transcript) -> None:
    pending = target.with_name(f".{uuid4()}.json")
    try:
        pending.write_text(transcript.model_dump_json(indent=2) + "\n", encoding="utf-8")
        pending.replace(target)
    finally:
        try:
            pending.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not remove temporary transcript %s", pending, exc_info=True)


def get_transcript(video_id: UUID) -> Transcript:
    path, _ = videos.download_file(video_id, "transcript")
    try:
        return Transcript.model_validate_json(path.read_bytes())
    except ValidationError as exc:
        logger.exception("Could not read transcript for video job %s", video_id)
        raise VideoError(500, "The saved transcript is invalid.") from exc
