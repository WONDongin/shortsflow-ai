from os import getenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.health import router as health_router

app = FastAPI(title="ShortsFlow AI")

default_origins = "http://localhost:5173,http://127.0.0.1:5173"
origins = [
    origin.strip()
    for origin in getenv("CORS_ORIGINS", default_origins).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET"],
)
app.include_router(health_router)
