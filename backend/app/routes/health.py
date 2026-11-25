# FastAPI·PostgreSQL 상태 확인 라우터
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.db import check_video_tables

router = APIRouter(prefix="/api")


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


# 데이터베이스 접속 없이 FastAPI 응답 상태 확인
@router.get("/health")
def get_health() -> HealthResponse:
    return HealthResponse()


# 두 테이블 읽기 확인, 실패 시 HTTP 503 반환
@router.get("/health/db", responses={503: {"description": "Database check failed"}})
def get_db_health() -> HealthResponse:
    try:
        check_video_tables()
    except (SQLAlchemyError, ValueError, OSError):
        raise HTTPException(503, "Database check failed.") from None
    return HealthResponse()
