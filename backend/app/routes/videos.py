from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Query, UploadFile

from app.schemas.video import ExtractionResult, VideoResult
from app.services import videos

# 업로드, 조회 및 추출 API
router = APIRouter(prefix="/api/videos", tags=["videos"])


@router.post(
    "",
    status_code=201,
    responses={
        413: {"description": "File exceeds 100 MiB"},
        415: {"description": "File extension is not MP4"},
    },
)
def upload_video(
    file: Annotated[UploadFile, File(description="MP4 file up to 100 MiB")],
) -> VideoResult:
    return videos.store_upload(file.file, file.filename, file.size)


@router.get("/{video_id}", responses={404: {"description": "Video job not found"}})
def read_video(video_id: UUID) -> VideoResult:
    return videos.get_video(video_id)


@router.post("/{video_id}/extract-audio", responses={404: {"description": "Video job not found"}})
def extract_audio(video_id: UUID) -> ExtractionResult:
    return videos.extract_audio(video_id)


@router.post("/{video_id}/extract-frame", responses={404: {"description": "Video job not found"}})
def extract_frame(
    video_id: UUID,
    timestamp_seconds: Annotated[float, Query(ge=0, allow_inf_nan=False)] = 0,
) -> ExtractionResult:
    return videos.extract_frame(video_id, timestamp_seconds)
