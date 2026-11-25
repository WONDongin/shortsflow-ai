# MP4 업로드·조회·추출·다운로드 라우터
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import FileResponse

from app.schemas.video import ExtractionResult, VideoResult
from app.services import videos

router = APIRouter(prefix="/api/videos", tags=["videos"])


# MP4 업로드 후 UUID와 메타데이터 반환
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


# UUID로 영상 정보와 결과물 경로 조회
@router.get("/{video_id}", responses={404: {"description": "Video job not found"}})
def read_video(video_id: UUID) -> VideoResult:
    return videos.get_video(video_id)


# 파일 첨부 응답, 파일이 없으면 HTTP 404
@router.get(
    "/{video_id}/download/{kind}",
    response_class=FileResponse,
    responses={404: {"description": "Video file not found"}},
)
def download_video(video_id: UUID, kind: Literal["source", "audio", "frame"]) -> FileResponse:
    path, media_type = videos.download_file(video_id, kind)
    return FileResponse(
        path, media_type=media_type, filename=path.name, headers={"Cache-Control": "no-store"}
    )


# 음성 트랙을 WAV로 추출
@router.post("/{video_id}/extract-audio", responses={404: {"description": "Video job not found"}})
def extract_audio(video_id: UUID) -> ExtractionResult:
    return videos.extract_audio(video_id)


# 지정한 시점의 프레임을 JPG로 추출
@router.post("/{video_id}/extract-frame", responses={404: {"description": "Video job not found"}})
def extract_frame(
    video_id: UUID,
    timestamp_seconds: Annotated[float, Query(ge=0, allow_inf_nan=False)] = 0,
) -> ExtractionResult:
    return videos.extract_frame(video_id, timestamp_seconds)
