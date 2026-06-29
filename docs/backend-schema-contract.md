# Sightpost Backend Schema Contract

This file defines the database/API contract the backend should use with the Sightpost ML service.

The ML service only returns face embeddings. The backend owns all identity records, image URLs, pgvector search, match creation, review decisions, role checks, and audit logs.

## Core ML Contract

Endpoint:

```http
POST /extract-embedding
Content-Type: multipart/form-data
field: file
```

Successful response:

```json
{
  "success": true,
  "face_detected": true,
  "embedding": [512 floats],
  "error": null,
  "model": "buffalo_l",
  "embedding_dim": 512,
  "face_confidence": 0.99,
  "inference_ms": 120.5
}
```

No-face response:

```json
{
  "success": false,
  "face_detected": false,
  "embedding": null,
  "error": "No face detected",
  "model": "buffalo_l",
  "embedding_dim": 512,
  "face_confidence": null,
  "inference_ms": 40.2
}
```

Backend rules:

- Store embeddings as `vector(512)`.
- Embeddings returned by ML are already L2-normalized.
- Use cosine similarity for matching.
- Query top 5 candidates.
- Surface only candidates with similarity `>= 0.50`.
- Never auto-confirm identity.
- Always create pending match suggestions for human review.

## Confidence Bands

```text
>= 0.80 High
>= 0.65 Medium
>= 0.50 Low
< 0.50 Not surfaced
```

## Required PostgreSQL Extensions

```sql
create extension if not exists "pgcrypto";
create extension if not exists "vector";
```

## Enum Types

Use check constraints if the backend team prefers not to use enums. These values should stay consistent across backend, frontend, and database.

```sql
create type authority_role as enum ('police', 'medical', 'admin');
create type case_status as enum ('active', 'located', 'closed');
create type patient_status as enum ('unidentified', 'matched', 'closed');
create type match_source_type as enum ('sighting', 'medical_intake', 'reverse_patient');
create type match_status as enum ('pending', 'confirmed', 'dismissed');
create type confidence_band as enum ('High', 'Medium', 'Low');
```

## Tables

### `authority_users`

Stores application-level user profile and role metadata. This can map to Supabase Auth users through `auth_user_id`.

```sql
create table authority_users (
  id uuid primary key default gen_random_uuid(),
  auth_user_id uuid unique,
  role authority_role not null,
  organization_name text not null,
  display_name text not null,
  email text,
  phone text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```

Notes:

- Police users can register missing persons and review matches.
- Medical users can submit patient intake and view only their own intake/matches.
- Admin users can view audit logs and provision users.

### `missing_persons`

Primary registry searched by sightings and medical intakes.

```sql
create table missing_persons (
  id uuid primary key default gen_random_uuid(),
  full_name text not null,
  age integer,
  gender text,
  last_seen_location text,
  last_seen_at timestamptz,
  description text,
  family_contact_name text not null,
  family_contact_phone text not null,
  family_contact_relationship text,
  photo_url text not null,
  embedding vector(512) not null,
  status case_status not null default 'active',
  registered_by uuid references authority_users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```

Backend behavior:

- On `POST /persons`, upload/store image, call ML, save `embedding`.
- After saving, run reverse search against `unidentified_patients` where `status = 'unidentified'`.
- If reverse matches score `>= 0.50`, create `matches` rows with `source_type = 'reverse_patient'`.

### `sightings`

Public anonymous reports. Reporter identity is intentionally not stored.

```sql
create table sightings (
  id uuid primary key default gen_random_uuid(),
  public_reference text unique not null,
  location_text text,
  latitude double precision,
  longitude double precision,
  sighted_at timestamptz,
  notes text,
  photo_url text,
  embedding vector(512),
  created_at timestamptz not null default now()
);
```

Backend behavior:

- Public reporter does not need login.
- If image is included, call ML and store `embedding`.
- Query active `missing_persons` by cosine similarity.
- Create pending `matches` rows for top 5 candidates with score `>= 0.50`.

### `unidentified_patients`

Medical intake records for unconscious/unidentified patients.

```sql
create table unidentified_patients (
  id uuid primary key default gen_random_uuid(),
  hospital_user_id uuid not null references authority_users(id),
  hospital_reference text,
  intake_notes text,
  admitted_at timestamptz,
  photo_url text not null,
  embedding vector(512) not null,
  status patient_status not null default 'unidentified',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```

Backend behavior:

- On `POST /patients/intake`, call ML synchronously.
- Save patient record only if face embedding is generated.
- Query active `missing_persons` immediately.
- Create pending `matches` rows with `source_type = 'medical_intake'`.
- Medical users cannot browse `missing_persons` directly.

### `matches`

Single review queue for police sightings, medical intakes, and reverse patient matches.

```sql
create table matches (
  id uuid primary key default gen_random_uuid(),
  source_type match_source_type not null,
  source_id uuid not null,
  missing_person_id uuid not null references missing_persons(id),
  similarity_score double precision not null check (similarity_score >= 0 and similarity_score <= 1),
  confidence confidence_band not null,
  status match_status not null default 'pending',
  reviewer_id uuid references authority_users(id),
  reviewed_at timestamptz,
  review_notes text,
  created_at timestamptz not null default now(),
  unique (source_type, source_id, missing_person_id)
);
```

Backend behavior:

- `source_id` points to `sightings.id` when `source_type = 'sighting'`.
- `source_id` points to `unidentified_patients.id` when `source_type = 'medical_intake'` or `reverse_patient`.
- Use one dashboard query for all pending matches.
- Confirm/dismiss actions must write to `audit_logs`.

### `audit_logs`

Append-only human accountability trail.

```sql
create table audit_logs (
  id uuid primary key default gen_random_uuid(),
  actor_id uuid references authority_users(id),
  actor_role authority_role not null,
  action text not null,
  entity_type text not null,
  entity_id uuid not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
```

Recommended `action` values:

```text
person.created
sighting.created
patient.created
match.created
match.confirmed
match.dismissed
audit.exported
```

## Indexes

```sql
create index missing_persons_embedding_idx
on missing_persons
using hnsw (embedding vector_cosine_ops);

create index unidentified_patients_embedding_idx
on unidentified_patients
using hnsw (embedding vector_cosine_ops);

create index matches_status_created_idx on matches (status, created_at desc);
create index matches_source_idx on matches (source_type, source_id);
create index missing_persons_status_idx on missing_persons (status);
create index unidentified_patients_status_idx on unidentified_patients (status);
```

If Supabase does not allow HNSW on the selected plan/version, use IVFFlat after enough rows exist:

```sql
create index missing_persons_embedding_ivfflat_idx
on missing_persons
using ivfflat (embedding vector_cosine_ops)
with (lists = 100);
```

## Matching Queries

### Search missing persons from a sighting or patient embedding

```sql
select
  id as missing_person_id,
  full_name,
  photo_url,
  1 - (embedding <=> :query_embedding::vector) as similarity_score
from missing_persons
where status = 'active'
order by embedding <=> :query_embedding::vector
limit 5;
```

Backend should then keep only rows where:

```text
similarity_score >= 0.50
```

### Reverse search unidentified patients from a new missing-person embedding

```sql
select
  id as patient_id,
  photo_url,
  hospital_user_id,
  1 - (embedding <=> :query_embedding::vector) as similarity_score
from unidentified_patients
where status = 'unidentified'
order by embedding <=> :query_embedding::vector
limit 5;
```

## Confidence Mapping

Backend can implement this directly:

```python
def confidence_band(score: float) -> str | None:
    if score >= 0.80:
        return "High"
    if score >= 0.65:
        return "Medium"
    if score >= 0.50:
        return "Low"
    return None
```

Rows where `confidence_band(score)` returns `None` should not be inserted into `matches`.

## Required Backend Routes

```text
POST /persons
POST /sightings
POST /patients/intake
GET /matches/pending
POST /matches/{id}/review
GET /audit-logs
GET /audit-logs/export.csv
```

## Review Rules

When a match is confirmed:

- Set `matches.status = 'confirmed'`.
- Set `reviewer_id`, `reviewed_at`, and optional `review_notes`.
- Write `audit_logs` row with `action = 'match.confirmed'`.
- If source is `sighting`, backend may mark missing person as `located` after police workflow.
- If source is `medical_intake` or `reverse_patient`, hospital should receive only family contact already stored on the missing-person record after authorized confirmation.

When a match is dismissed:

- Set `matches.status = 'dismissed'`.
- Set `reviewer_id`, `reviewed_at`, and optional `review_notes`.
- Write `audit_logs` row with `action = 'match.dismissed'`.

## Role Boundaries

Police:

- Can create and view missing-person records.
- Can review sighting matches.
- Can access family contact details as part of case workflow.

Medical:

- Can create unidentified patient intakes.
- Can view only matches tied to their own patient intake records.
- Cannot browse all missing-person records.
- Receives family contact only after a confirmed match.

Admin:

- Can view all audit logs.
- Can export audit logs.
- Can provision users.

Public:

- Can create sightings.
- Does not have an account.
- Reporter identity is not stored.

## Image Storage Buckets

Recommended Supabase Storage buckets:

```text
missing-person-photos private
sighting-photos private
patient-intake-photos private
```

Store only URLs/paths in tables. Do not store raw image bytes in Postgres.

## Backend Handoff Summary

The backend team needs to implement this exact loop:

```text
Receive image
Upload image to private storage
Send image/crop to ML /extract-embedding
If no face, return validation message
Store vector(512)
Run pgvector cosine search
Keep top 5 with score >= 0.50
Insert pending matches
Human reviewer confirms/dismisses
Write audit log
```
