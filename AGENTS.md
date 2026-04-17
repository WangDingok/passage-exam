# Passage Exam Agents Guide

This package is a standalone pipeline for passage-based exam generation, draft review, and upload.

It is intentionally isolated from the legacy flow in `src/main.py`. Treat the old flow as reference only. Do not wire new passage logic into the old quiz/material pipeline unless explicitly requested.

## Mission

Build, validate, generate, and upload "câu hỏi chùm" exams using this package only.

The package supports:

- Text-first source ingestion from `txt`, `doc`, and `docx`
- Normalization into one internal JSON contract
- LLM-based generation of new passage questions
- Draft persistence and audit history through the workflow layer
- Review/edit/validate/publish flow through the workflow API and TypeScript UI
- Upload to Hasura GraphQL using the existing DB model

V1 does not support:

- OCR or image-first parsing
- `material_book_attachments`
- direct use of `question_groups`
- non-multiple-choice upload

## Package Layout

- `api/`
  - FastAPI workflow endpoints used by the TypeScript UI
- `contracts.py`
  - Pydantic contract for the normalized passage exam document
- `parser/`
  - text extraction from supported source files
- `generator/`
  - LLM prompt + Azure OpenAI client + normalized contract generation
- `graphql/`
  - isolated Hasura client and GraphQL operations, including workflow tables
- `workflow/`
  - draft contracts and workflow orchestration for upload/generate/edit/validate/publish
- `uploader/`
  - category resolution, payload building, idempotency, upload orchestration
- `main.py`
  - user-facing commands: `generate`, `upload`, `run`, `serve`
- `frontend/`
  - React + TypeScript UI for gallery, review, and publish flow

## Core Data Model

The normalized internal shape is:

```json
{
  "title": "Đề đọc hiểu số 1",
  "description": "Sinh từ đề mẫu ...",
  "groups": [
    {
      "order": 1,
      "passage": "<p>Đoạn văn chung...</p>",
      "questions": [
        {
          "order": 1,
          "type": "multiple_choice",
          "question": "<p>Câu 1...</p>",
          "choices": [
            {"content": "<p>A</p>", "is_correct": false},
            {"content": "<p>B</p>", "is_correct": true}
          ]
        }
      ]
    }
  ]
}
```

This contract is the source of truth for all later stages.

If you add new source parsers or generation modes, convert them into this contract before touching upload logic.

## Workflow Layer

The workflow layer adds a draft-first review cycle before upload:

- upload source into `passage_exam.passage_exam_drafts`
- record audit trail in `passage_exam.passage_exam_events`
- generate normalized `PassageExamDocument`
- allow review/edit/validate in the UI
- publish only after review, using the same uploader rules below

The workflow layer does not change the final DB mapping for published exams. Publish still writes to `materials`, `exams`, `questions`, and `exam_questions` only.

## DB Mapping Rules

For each passage group:

- Create one parent row in `questions`
- Parent category path: `basic_question -> group`
- Parent `name` stores the passage HTML
- Create child rows through `sub_questions`
- Child category path: `basic_question -> multiple_choice -> single_choice`
- Child `questions_hotspots.data` stores flat answer options

Then create one exam:

- Insert one atomic nested mutation into `exams`
- Create nested `materials`
- Create nested `exam_questions.data`
- Create nested parent/child `questions` trees under `exam_questions.question.data`
- Link `exam_questions.data` to parent question ids only

## Hotspot Semantics

In this package, `hotspots` means answer-option rows for a child multiple-choice question.

The wider Hasura schema supports a richer hotspot model with fields and relations such as:

- `hotspots.parent_id`
- `hotspots.children`
- geometry fields like `left`, `top`, and `path`
- fill/drop style metadata

This package does not use that richer capability.

Operationally, the uploader only writes flat answer-option rows with fields such as:

- `content`
- `is_correct`
- `order_number`
- `question_id`

It does not populate or traverse nested hotspot trees. Do not design frontend or upload behavior here around recursive hotspot rendering unless the product scope changes explicitly.

## Important Invariants

Do not break these without an explicit product decision:

- Do not use `question_groups` for passage exams
- Do not create `material_book_attachments`
- Link exams to parent question ids only
- Resolve category ids by `code`, never hardcode UUIDs
- Keep HTML formatting local to this package
- Treat `hotspots` as flat answer options in this package, not as nested geometry nodes
- Every multiple choice question must have exactly 4 choices and exactly 1 correct answer
- Reject empty passages
- Reject groups with zero child questions

## HTML Rules

Before upload:

- Convert plain text to safe paragraph HTML with `ensure_html_paragraphs()`
- Preserve already-formatted HTML if it already contains tags like `<p>` or `<img>`
- Do not push raw plain text directly to Hasura fields intended for rendered content

## Idempotency Rules

Uploader idempotency is based on a canonical source hash of the normalized document.

- The hash is appended into exam/material description as `[source_hash:...]`
- Existing uploads are detected by title + hash marker
- In `skip` and `fail` modes, uploader also locks the write to a deterministic `materials.id`
- Concurrent duplicate uploads are therefore blocked by `materials_pkey` and mapped back to `skip` or `fail`
- Supported modes:
  - `off`: always upload
  - `skip`: return skipped result if duplicate exists
  - `fail`: raise duplicate error if duplicate exists

If you change hashing or duplicate lookup behavior, update tests first.

## Environment

This package reuses only these env vars:

- `PASSAGE_EXAM_CREATED_BY` convenience default for CLI and preferred actor id for workflow publish
- `GRAPHQL_URL`
- `HASURA_ADMIN_SECRET`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_DEPLOYMENT_NAME` optional

Do not introduce dependency on the legacy pipeline env unless there is a real need.

## CLI Usage

Generate normalized JSON from source files:

```bash
python -m src.main generate --input <file-or-dir> --output-dir <dir>
```

Upload normalized JSON:

```bash
python -m src.main upload --input-json <file> --created-by <user-id>
```

Generate and upload in one flow:

```bash
python -m src.main run --input <file-or-dir> --created-by <user-id>
```

Run the workflow API and UI:

For Windows local development, use the bundled launcher to start both the API and Vite UI:

```powershell
.\start.ps1
```

Otherwise, start them separately:

```bash
python -m src.main serve --host 127.0.0.1 --port 8001
```

```bash
cd frontend
npm run dev
```

## Testing

Run package tests with:

```bash
python -m unittest discover -s tests -p "test_passage_exam_*.py"
```

Current tests cover:

- parser behavior for `txt`, `doc`, `docx`
- contract validation
- category resolution
- payload building
- mocked upload flow with atomic parent-only exam links
- duplicate race fallback through deterministic `materials.id`

When changing behavior, add or update tests in `tests/test_passage_exam_*.py`.

## Extension Guidance

If extending this package:

- Add new source parsers under `parser/`
- Add new generation behavior under `generator/`
- Keep GraphQL documents isolated under `graphql/`
- Keep business rules in `uploader/`
- Prefer adding new tests before changing upload behavior

If adding new question types in the future:

- extend `contracts.py`
- add validation rules first
- update `build_passage_group_payload()`
- update generator prompt to emit the new type
- add tests for both validation and payload mapping

## What To Avoid

- Do not reuse `src/main.py` upload orchestration
- Do not copy old material attachment behavior into this package
- Do not silently widen scope to OCR, PDF annotations, or mixed question types
- Do not change exam linking from parent-only to child-only without coordinated frontend/query changes
