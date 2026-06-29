from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np


class InvalidImageError(ValueError):
    pass


@dataclass(frozen=True)
class EmbeddingResult:
    embedding: Optional[list[float]]
    face_detected: bool
    face_confidence: Optional[float] = None
    error: Optional[str] = None


class FaceEmbeddingService:
    def __init__(self, model_name: str = "buffalo_l", det_size: tuple[int, int] = (640, 640)) -> None:
        self.model_name = model_name
        self.det_size = det_size
        self.embedding_dim = 512
        self._model = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self._model is not None:
            return

        from insightface.app import FaceAnalysis

        app = FaceAnalysis(name=self.model_name, providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=self.det_size)
        self._model = app

    def extract(self, image_bytes: bytes) -> EmbeddingResult:
        if self._model is None:
            raise RuntimeError("Face embedding model is not loaded")

        image = decode_image(image_bytes)
        faces = self._model.get(image)

        if not faces:
            return EmbeddingResult(embedding=None, face_detected=False, error="No face detected")

        face = choose_primary_face(faces)
        raw_embedding = getattr(face, "normed_embedding", None)
        if raw_embedding is None:
            raw_embedding = getattr(face, "embedding", None)
        if raw_embedding is None:
            return EmbeddingResult(embedding=None, face_detected=False, error="Face embedding unavailable")

        embedding = l2_normalize(np.asarray(raw_embedding, dtype=np.float32))
        confidence = float(getattr(face, "det_score", 0.0))

        return EmbeddingResult(
            embedding=embedding.astype(float).tolist(),
            face_detected=True,
            face_confidence=round(confidence, 6),
        )


def decode_image(image_bytes: bytes) -> np.ndarray:
    if not image_bytes:
        raise InvalidImageError("Uploaded image is empty")

    buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise InvalidImageError("Uploaded file is not a valid image")

    return image


def choose_primary_face(faces: list[object]) -> object:
    def face_rank(face: object) -> tuple[float, float]:
        bbox = np.asarray(getattr(face, "bbox", [0, 0, 0, 0]), dtype=np.float32)
        width = max(float(bbox[2] - bbox[0]), 0.0)
        height = max(float(bbox[3] - bbox[1]), 0.0)
        area = width * height
        score = float(getattr(face, "det_score", 0.0))
        return area, score

    return max(faces, key=face_rank)


def l2_normalize(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    if norm == 0:
        raise ValueError("Cannot normalize a zero vector")
    return vector / norm
