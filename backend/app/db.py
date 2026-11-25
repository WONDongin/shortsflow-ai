# PostgreSQL 연결 설정과 테이블 읽기 확인
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


# backend/.env로 PostgreSQL 연결 풀 생성 및 재사용
@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = dotenv_values(ENV_FILE, interpolate=False, encoding="utf-8-sig")
    url = URL.create(
        "postgresql+psycopg",
        host=settings.get("DB_HOST") or "localhost",
        port=int(settings.get("DB_PORT") or "5432"),
        database=settings.get("DB_NAME") or "shortsflow",
        username=settings.get("DB_USER") or "shortsflow_user",
        password=settings.get("DB_PASSWORD") or None,
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
    )


# 영상·결과물 테이블에 읽기 쿼리 실행
def check_video_tables() -> None:
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1 FROM shortsflow_app.videos LIMIT 1"))
        connection.execute(text("SELECT 1 FROM shortsflow_app.video_artifacts LIMIT 1"))
