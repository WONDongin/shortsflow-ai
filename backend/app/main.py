import logging
from os import getenv

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routes.health import router as health_router
from app.routes.videos import router as videos_router
from app.services.media import VideoError

# 라우터 등록, CORS, 오류 응답 및 로깅
app = FastAPI(title="ShortsFlow AI")
logger = logging.getLogger("uvicorn.error").getChild("shortsflow")


@app.exception_handler(VideoError)
async def handle_video_error(request: Request, exc: VideoError) -> JSONResponse:
    logger.warning("%s %s returned %d: %s", request.method, request.url.path, exc.status_code, exc)
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


@app.exception_handler(OSError)
async def handle_storage_error(request: Request, exc: OSError) -> JSONResponse:
    logger.error("File operation failed for %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "A video file operation failed."})

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
app.include_router(health_router)
app.include_router(videos_router)
