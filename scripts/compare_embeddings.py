"""Compare two images through a running Sightpost ML service.

Usage:
    python scripts/compare_embeddings.py http://127.0.0.1:8001 image_a.jpg image_b.jpg
"""

from __future__ import annotations

import json
import math
import sys
import urllib.request
from pathlib import Path


def extract(base_url: str, image_path: Path) -> list[float]:
    boundary = "----SightpostBoundary"
    image_bytes = image_path.read_bytes()
    body = b"\r\n".join(
        [
            f"--{boundary}".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{image_path.name}"'.encode(),
            b"Content-Type: image/jpeg",
            b"",
            image_bytes,
            f"--{boundary}--".encode(),
            b"",
        ]
    )
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/extract-embedding",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not payload.get("success"):
        raise SystemExit(f"Embedding failed for {image_path}: {payload.get('error')}")
    return payload["embedding"]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    return dot / (left_norm * right_norm)


def label(score: float) -> str:
    if score >= 0.80:
        return "High"
    if score >= 0.65:
        return "Medium"
    if score >= 0.50:
        return "Low"
    return "Not surfaced"


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)

    base_url = sys.argv[1]
    image_a = Path(sys.argv[2])
    image_b = Path(sys.argv[3])
    emb_a = extract(base_url, image_a)
    emb_b = extract(base_url, image_b)
    score = cosine_similarity(emb_a, emb_b)
    print(json.dumps({"cosine_similarity": round(score, 6), "band": label(score)}, indent=2))


if __name__ == "__main__":
    main()
