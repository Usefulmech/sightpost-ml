from contextlib import asynccontextmanager
from time import perf_counter
from typing import AsyncIterator

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.embedding import FaceEmbeddingService, InvalidImageError
from app.schemas import EmbeddingResponse, HealthResponse, ScoreBand
from app.scoring import SCORE_BANDS

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    embedder = FaceEmbeddingService(model_name=settings.model_name, det_size=settings.det_size)
    if not settings.skip_model_load:
        embedder.load()
    app.state.embedder = embedder
    yield


app = FastAPI(
    title="Sightpost ML Service",
    description="Face embedding extraction service for Sightpost police and medical matching flows.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    embedder: FaceEmbeddingService = request.app.state.embedder
    return HealthResponse(model=embedder.model_name, model_loaded=embedder.loaded)


@app.get("/score-bands", response_model=list[ScoreBand])
def score_bands() -> list[ScoreBand]:
    return SCORE_BANDS


@app.post("/extract-embedding", response_model=EmbeddingResponse)
async def extract_embedding(request: Request, file: UploadFile = File(...)) -> EmbeddingResponse:
    embedder: FaceEmbeddingService = request.app.state.embedder
    if not embedder.loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Face embedding model is not loaded",
        )

    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload must be an image")

    image_bytes = await file.read()
    if len(image_bytes) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image is larger than {settings.max_upload_mb} MB",
        )

    started = perf_counter()
    try:
        result = embedder.extract(image_bytes)
    except InvalidImageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    inference_ms = round((perf_counter() - started) * 1000, 2)

    return EmbeddingResponse(
        success=result.face_detected and result.embedding is not None,
        face_detected=result.face_detected,
        embedding=result.embedding,
        error=result.error,
        model=embedder.model_name,
        embedding_dim=embedder.embedding_dim,
        face_confidence=result.face_confidence,
        inference_ms=inference_ms,
    )
