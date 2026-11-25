# MP4 업로드·조회·추출·다운로드 라우터
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, Query, Response, UploadFile
from fastapi.responses import FileResponse

from app.schemas.analysis import AnalysisResult
from app.schemas.video import ExtractionResult, ShortsResult, Transcript, VideoResult
from app.services import analysis_records, content_analysis, shorts, transcripts, videos
from app.services.media import VideoError

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
def download_video(
    video_id: UUID,
    kind: Literal["source", "audio", "frame", "transcript", "shorts", "thumbnail"],
    analysis_id: Annotated[UUID | None, Query(description="Required for shorts and thumbnail")] = None,
) -> Response:
    if kind in ("shorts", "thumbnail"):
        path, media_type = shorts.download_file(video_id, analysis_id, kind)
    else:
        path, media_type = videos.download_file(video_id, kind)
    headers = {"Cache-Control": "no-store"}
    if kind == "transcript":
        # Read one snapshot so a simultaneous replacement cannot change the response length.
        headers["Content-Disposition"] = 'attachment; filename="transcript.json"'
        return Response(path.read_bytes(), media_type=media_type, headers=headers)
    return FileResponse(
        path, media_type=media_type, filename=path.name, headers=headers
    )


# 음성 트랙을 WAV로 추출
@router.post("/{video_id}/extract-audio", responses={404: {"description": "Video job not found"}})
def extract_audio(video_id: UUID) -> ExtractionResult:
    return videos.extract_audio(video_id)


@router.post(
    "/{video_id}/transcribe",
    responses={
        404: {"description": "Video job or original file not found"},
        409: {"description": "WAV audio has not been extracted"},
        503: {"description": "Whisper model, media tool, or video database unavailable"},
    },
)
def transcribe_video(video_id: UUID) -> Transcript:
    return transcripts.transcribe_video(video_id)


@router.get("/{video_id}/transcript", responses={404: {"description": "Video job or transcript not found"}})
def read_transcript(video_id: UUID, response: Response) -> Transcript:
    response.headers["Cache-Control"] = "no-store"
    return transcripts.get_transcript(video_id)


@router.post(
    "/{video_id}/analyze",
    status_code=202,
    responses={404: {"description": "Video job not found"}, 503: {"description": "Video database unavailable"}},
)
def analyze_video(video_id: UUID, background_tasks: BackgroundTasks, response: Response) -> AnalysisResult:
    video = videos.get_video(video_id)
    analysis, created = analysis_records.request_analysis(video)
    if created:
        background_tasks.add_task(
            content_analysis.run_analysis, analysis.analysis_id, video_id, video.metadata.duration_seconds
        )
    response.headers["Location"] = f"/api/videos/{video_id}/analysis?analysis_id={analysis.analysis_id}"
    return analysis


@router.get(
    "/{video_id}/analysis",
    responses={404: {"description": "Analysis job not found"}, 503: {"description": "Video database unavailable"}},
)
def read_analysis(video_id: UUID, response: Response, analysis_id: UUID | None = None) -> AnalysisResult:
    response.headers["Cache-Control"] = "no-store"
    analysis = analysis_records.find_analysis(video_id, analysis_id)
    if analysis is None:
        raise VideoError(404, "Analysis job not found.")
    return analysis


@router.post(
    "/{video_id}/generate-shorts",
    responses={
        404: {"description": "Video, analysis job, original file, or transcript not found"},
        409: {"description": "Analysis has no completed candidate"},
        422: {"description": "Invalid clip range, missing captions in the clip, or original video without audio"},
        503: {"description": "Media tool, thumbnail font, or database unavailable"},
    },
)
def generate_shorts(video_id: UUID, analysis_id: UUID) -> ShortsResult:
    return shorts.generate_shorts(video_id, analysis_id)


@router.get(
    "/{video_id}/shorts",
    responses={
        404: {"description": "Video, analysis job, or rendered files not found"},
        409: {"description": "Analysis has no completed candidate"},
    },
)
def read_shorts(video_id: UUID, analysis_id: UUID, response: Response) -> ShortsResult:
    response.headers["Cache-Control"] = "no-store"
    return shorts.get_shorts(video_id, analysis_id)


# 지정한 시점의 프레임을 JPG로 추출
@router.post("/{video_id}/extract-frame", responses={404: {"description": "Video job not found"}})
def extract_frame(
    video_id: UUID,
    timestamp_seconds: Annotated[float, Query(ge=0, allow_inf_nan=False)] = 0,
) -> ExtractionResult:
    return videos.extract_frame(video_id, timestamp_seconds)
