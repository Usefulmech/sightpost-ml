create extension if not exists "pgcrypto";
create extension if not exists "vector";

create type authority_role as enum ('police', 'medical', 'admin');
create type case_status as enum ('active', 'located', 'closed');
create type patient_status as enum ('unidentified', 'matched', 'closed');
create type match_source_type as enum ('sighting', 'medical_intake', 'reverse_patient');
create type match_status as enum ('pending', 'confirmed', 'dismissed');
create type confidence_band as enum ('High', 'Medium', 'Low');

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
