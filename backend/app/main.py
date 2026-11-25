# FastAPI 앱, 라우터, CORS, 공통 오류 처리
import logging
from os import getenv

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.routes.health import router as health_router
from app.routes.videos import router as videos_router
from app.services.media import VideoError

# FastAPI 앱과 서버 로거 초기화
app = FastAPI(title="ShortsFlow AI")
logger = logging.getLogger("uvicorn.error").getChild("shortsflow")


# DB 작업 실패 시 상세 정보 없이 HTTP 503 반환
@app.exception_handler(SQLAlchemyError)
async def handle_database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.error("Database operation failed for %s %s", request.method, request.url.path)
    return JSONResponse(status_code=503, content={"detail": "The video database is unavailable."})


# 영상 처리 오류를 지정된 상태 코드와 메시지로 반환
@app.exception_handler(VideoError)
async def handle_video_error(request: Request, exc: VideoError) -> JSONResponse:
    logger.warning("%s %s returned %d: %s", request.method, request.url.path, exc.status_code, exc)
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


# 파일 작업 오류 로깅 및 HTTP 500 반환
@app.exception_handler(OSError)
async def handle_storage_error(request: Request, exc: OSError) -> JSONResponse:
    logger.error("File operation failed for %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "A video file operation failed."})

# CORS 허용 출처와 GET·POST 설정
default_origins = "http://localhost:5173,http://127.0.0.1:5173"
origins = [
    origin.strip()
    for origin in getenv("CORS_ORIGINS", default_origins).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST"],
)
# 상태 확인·영상 처리 라우터 등록
app.include_router(health_router)
app.include_router(videos_router)
