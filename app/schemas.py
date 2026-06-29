from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "sightpost-ml"
    model: str
    model_loaded: bool
    embedding_dim: int = 512


class EmbeddingResponse(BaseModel):
    success: bool
    face_detected: bool
    embedding: Optional[List[float]] = Field(default=None, min_length=512, max_length=512)
    error: Optional[str] = None
    model: str
    embedding_dim: int = 512
    face_confidence: Optional[float] = None
    inference_ms: Optional[float] = None


class ScoreBand(BaseModel):
    label: Literal["High", "Medium", "Low", "Not surfaced"]
    min_score: float
    max_score: Optional[float]
