# Sightpost ML Service

Isolated FastAPI service for Sightpost face embedding extraction. It is used by both police public-sighting flows and medical unidentified-patient intake flows.

The service does not store images, identities, names, locations, family contacts, or patient information. It accepts one image, returns one 512-dimensional normalized face embedding, and discards the image bytes after the request.

## API contract

### `GET /health`

Returns service/model readiness.

```json
{
  "status": "ok",
  "service": "sightpost-ml",
  "model": "buffalo_l",
  "model_loaded": true,
  "embedding_dim": 512
}
```

### `POST /extract-embedding`

Multipart form upload with field name `file`.

Successful face response:

```json
{
  "success": true,
  "face_detected": true,
  "embedding": [0.0123],
  "error": null,
  "model": "buffalo_l",
  "embedding_dim": 512,
  "face_confidence": 0.99,
  "inference_ms": 124.5
}
```

No-face response, still HTTP 200 so the backend can treat it as a clean validation outcome:

```json
{
  "success": false,
  "face_detected": false,
  "embedding": null,
  "error": "No face detected",
  "model": "buffalo_l",
  "embedding_dim": 512,
  "face_confidence": null,
  "inference_ms": 44.1
}
```

Invalid uploads return HTTP 400. Oversized uploads return HTTP 413. If the model is unavailable, the service returns HTTP 503.

### `GET /score-bands`

Returns the demo confidence bands used by backend/frontend copy.

```text
>= 0.80 High
>= 0.65 Medium
>= 0.50 Low
< 0.50 Not surfaced
```

The backend owns pgvector search and match persistence. This service only extracts embeddings.

## Local setup

Use Python 3.11 for local development. The face embedding stack may not have stable wheels for newer Python versions yet.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```


For full local model inference on Windows, `insightface` may require Microsoft C++ Build Tools because it compiles a native extension. If you do not want to install C++ tooling, use `requirements-dev.txt` locally and run the full model through Docker or Hugging Face Spaces.

Full runtime install, for Linux/Docker/Hugging Face or a Windows machine with C++ Build Tools:

```powershell
python -m pip install -r requirements.txt
```
Open:

```text
http://127.0.0.1:8001/docs
```

Example request:

```powershell
curl.exe -X POST "http://127.0.0.1:8001/extract-embedding" -F "file=@C:\path\to\face.jpg"
```


## Backend schema handoff

This repo includes a backend/database contract so the backend and ML workstreams stay aligned.

Files:

```text
docs/backend-schema-contract.md
supabase/schema.sql
```

Purpose:

- Defines the exact tables the backend needs for missing persons, sightings, unidentified patients, matches, authority users, and audit logs.
- Defines all enum values used across backend/frontend/ML handoff, including match source types and confidence bands.
- Defines `vector(512)` embedding columns for Supabase pgvector.
- Documents how backend should call `/extract-embedding`, store returned vectors, run cosine similarity search, create pending matches, and write audit logs.
- Makes clear that this ML service does not own identity data or database writes. It only converts an image into a normalized 512-dimensional embedding.

Backend teammates can start from `supabase/schema.sql` when creating the Supabase database. They should read `docs/backend-schema-contract.md` before implementing routes or RLS policies.
## Backend integration notes

Backend routes should call this service before writing vectors to Supabase:

- `POST /persons`: extract missing-person photo embedding, store in `missing_persons.embedding`, then optionally reverse-match against `unidentified_patients`.
- `POST /sightings`: extract sighting photo embedding when provided, query top-5 active missing persons by cosine similarity, store surfaced candidates in `matches`.
- `POST /patients/intake`: extract intake photo embedding synchronously, query top-5 active missing persons, store patient and candidate matches.

Expected pgvector behavior:

- Use normalized vectors from this service.
- Query by cosine distance/similarity.
- Surface only scores `>= 0.50`.
- Keep top 5 candidates.
- Always route suggestions to human review.

## Hugging Face Spaces deployment

Create a new Space using the Docker SDK, then push this repo. The container listens on port `7860`.

Recommended environment variables:

```text
SIGHTPOST_MODEL_NAME=buffalo_l
SIGHTPOST_DET_SIZE=640,640
SIGHTPOST_MAX_UPLOAD_MB=8
SIGHTPOST_ALLOWED_ORIGINS=*
```

Warm the Space 5-10 minutes before judging to avoid cold-start delay.

## Model limitations for pitch Q&A

Face similarity is advisory, not proof of identity. Performance can degrade with poor lighting, blur, occlusion, extreme pose, old photos, injuries, age changes, camera artifacts, or demographic imbalance in training data. Sightpost therefore never performs automated identity confirmation, alerts, or case closure. Every suggested match is reviewed by authorized police or medical staff, and every decision is logged.

## Tests

The API tests use fake embedders so they do not download the model.

```powershell
$env:SIGHTPOST_SKIP_MODEL_LOAD='true'
pytest
```



