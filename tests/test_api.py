import io
import os

os.environ["SIGHTPOST_SKIP_MODEL_LOAD"] = "true"

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.embedding import EmbeddingResult
from app.main import app


class FakeEmbedder:
    model_name = "buffalo_l"
    embedding_dim = 512
    loaded = True

    def extract(self, image_bytes: bytes) -> EmbeddingResult:
        vector = np.ones(512, dtype=np.float32)
        vector = vector / np.linalg.norm(vector)
        return EmbeddingResult(embedding=vector.astype(float).tolist(), face_detected=True, face_confidence=0.99)


class NoFaceEmbedder(FakeEmbedder):
    def extract(self, image_bytes: bytes) -> EmbeddingResult:
        return EmbeddingResult(embedding=None, face_detected=False, error="No face detected")


def make_png_bytes() -> bytes:
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    return buffer.tobytes()


def test_health_reports_model_loaded():
    with TestClient(app) as client:
        app.state.embedder = FakeEmbedder()
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["model"] == "buffalo_l"
    assert response.json()["embedding_dim"] == 512
    assert response.json()["model_loaded"] is True


def test_extract_embedding_returns_512_floats():
    with TestClient(app) as client:
        app.state.embedder = FakeEmbedder()
        response = client.post(
            "/extract-embedding",
            files={"file": ("face.png", io.BytesIO(make_png_bytes()), "image/png")},
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["face_detected"] is True
    assert len(payload["embedding"]) == 512
    assert abs(np.linalg.norm(np.array(payload["embedding"])) - 1.0) < 1e-6


def test_extract_embedding_handles_no_face():
    with TestClient(app) as client:
        app.state.embedder = NoFaceEmbedder()
        response = client.post(
            "/extract-embedding",
            files={"file": ("blank.png", io.BytesIO(make_png_bytes()), "image/png")},
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is False
    assert payload["face_detected"] is False
    assert payload["embedding"] is None
    assert payload["error"] == "No face detected"


def test_extract_embedding_rejects_non_images():
    with TestClient(app) as client:
        app.state.embedder = FakeEmbedder()
        response = client.post(
            "/extract-embedding",
            files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
        )

    assert response.status_code == 400
