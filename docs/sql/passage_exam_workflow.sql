begin;

create extension if not exists pgcrypto;

create schema if not exists passage_exam;

create table if not exists passage_exam.passage_exam_drafts (
    id uuid primary key default gen_random_uuid(),
    title text not null,
    description text not null default '',
    status text not null,
    source_filename text not null,
    source_extension text not null,
    source_text text not null,
    normalized_document_json jsonb,
    generation_params_json jsonb,
    publish_result_json jsonb,
    error_message text,
    created_by text not null,
    updated_by text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    published_at timestamptz,
    constraint passage_exam_drafts_status_check
        check (status in ('uploaded', 'generated', 'reviewing', 'publish_failed', 'published'))
);

create table if not exists passage_exam.passage_exam_events (
    id uuid primary key default gen_random_uuid(),
    draft_id uuid not null references passage_exam.passage_exam_drafts(id) on delete cascade,
    event_type text not null,
    payload_json jsonb not null default '{}'::jsonb,
    actor_id text not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_passage_exam_drafts_status
    on passage_exam.passage_exam_drafts (status);

create index if not exists idx_passage_exam_drafts_updated_at
    on passage_exam.passage_exam_drafts (updated_at desc);

create index if not exists idx_passage_exam_drafts_created_by
    on passage_exam.passage_exam_drafts (created_by);

create index if not exists idx_passage_exam_events_draft_id
    on passage_exam.passage_exam_events (draft_id, created_at desc);

comment on table passage_exam.passage_exam_drafts is
    'Workflow drafts for passage exam upload/generate/review/publish before writing into public.materials/public.exams.';

comment on table passage_exam.passage_exam_events is
    'Audit trail for passage exam workflow actions.';

commit;
