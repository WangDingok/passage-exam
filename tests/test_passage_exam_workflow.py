import unittest

from pydantic import ValidationError

from src.uploader import UploadResult
from src.workflow import DraftGenerateRequest, DraftUpdateRequest, PassageExamWorkflowService


def make_document(title="De doc hieu moi"):
    return {
        "title": title,
        "description": "Sinh tu de mau",
        "groups": [
            {
                "order": 1,
                "passage": "<p>Doan van 1</p>",
                "questions": [
                    {
                        "order": 1,
                        "type": "multiple_choice",
                        "question": "<p>Cau hoi 1</p>",
                        "choices": [
                            {"content": "<p>A</p>", "is_correct": True},
                            {"content": "<p>B</p>", "is_correct": False},
                            {"content": "<p>C</p>", "is_correct": False},
                            {"content": "<p>D</p>", "is_correct": False},
                        ],
                    }
                ],
            }
        ],
    }


class FakeWorkflowOperations:
    def __init__(self):
        self.drafts = {}
        self.events = []
        self.counter = 0

    async def create_draft(self, payload):
        self.counter += 1
        draft_id = f"draft-{self.counter}"
        row = {
            "id": draft_id,
            "created_at": "2026-04-17T00:00:00+00:00",
            "updated_at": "2026-04-17T00:00:00+00:00",
            "published_at": None,
            **payload,
        }
        self.drafts[draft_id] = row
        return row

    async def update_draft(self, draft_id, payload):
        if draft_id not in self.drafts:
            return None
        self.drafts[draft_id].update(payload)
        self.drafts[draft_id]["updated_at"] = "2026-04-17T00:01:00+00:00"
        return self.drafts[draft_id]

    async def create_event(self, payload):
        self.counter += 1
        event = {
            "id": f"event-{self.counter}",
            "created_at": "2026-04-17T00:00:30+00:00",
            **payload,
        }
        self.events.append(event)
        return event

    async def get_draft(self, draft_id):
        return {
            "draft": self.drafts.get(draft_id),
            "events": list(reversed([event for event in self.events if event["draft_id"] == draft_id])),
        }

    async def list_drafts(self, *, where, limit, offset):
        del where, limit, offset
        return list(self.drafts.values())


class FakeGenerator:
    async def generate(self, **kwargs):
        progress_callback = kwargs.get("progress_callback")
        if progress_callback is not None:
            await progress_callback(
                "requesting_groups",
                {"message": "Generating passage groups from the source document."},
            )
            await progress_callback(
                "requesting_answers",
                {"message": "Generating answer key for the draft questions."},
            )
        from src.workflow.service import validate_document_payload

        return validate_document_payload(make_document())


class FakeUploader:
    def __init__(self, skipped=False):
        self.calls = []
        self.skipped = skipped

    async def upload(self, document, *, created_by, idempotency):
        self.calls.append((document.title, created_by, idempotency))
        return UploadResult(
            source_hash="hash-123",
            parent_question_ids=["parent-1"],
            child_question_ids=["child-1"],
            exam_id=None if self.skipped else "exam-1",
            material_id="material-1",
            skipped=self.skipped,
            duplicate_material_id="material-1" if self.skipped else None,
        )


class PassageExamWorkflowServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.operations = FakeWorkflowOperations()
        self.service = PassageExamWorkflowService(
            workflow_operations=self.operations,
            generator=FakeGenerator(),
            uploader=FakeUploader(),
        )

    async def test_upload_source_creates_uploaded_draft_and_event(self):
        draft = await self.service.upload_source(
            filename="reading_sample.txt",
            content=b"Passage one.\n\nQuestion style.",
            actor_id="user-1",
        )

        self.assertEqual("uploaded", draft.status.value)
        self.assertEqual("reading_sample.txt", draft.source_filename)
        self.assertEqual(1, len(draft.events))
        self.assertEqual("uploaded", draft.events[0].event_type)

    async def test_generate_stores_normalized_document(self):
        draft = await self.service.upload_source(
            filename="reading_sample.txt",
            content=b"Passage one.\n\nQuestion style.",
            actor_id="user-1",
        )

        generated = await self.service.generate(
            draft.id,
            DraftGenerateRequest(questions_per_group=1),
            actor_id="user-2",
        )

        self.assertEqual("generated", generated.status.value)
        self.assertEqual("De doc hieu moi", generated.title)
        self.assertIsNotNone(generated.normalized_document_json)
        self.assertEqual("generated", generated.events[0].event_type)
        self.assertEqual("generation_progress", generated.events[1].event_type)
        self.assertEqual("generation_progress", generated.events[2].event_type)
        self.assertEqual("generation_started", generated.events[3].event_type)

    async def test_update_rejects_invalid_document(self):
        draft = await self.service.upload_source(
            filename="reading_sample.txt",
            content=b"Passage one.\n\nQuestion style.",
            actor_id="user-1",
        )

        invalid_payload = make_document()
        invalid_payload["groups"][0]["questions"][0]["choices"][1]["is_correct"] = True

        with self.assertRaises(ValidationError):
            await self.service.update_draft(
                draft.id,
                DraftUpdateRequest(normalized_document_json=invalid_payload),
                actor_id="user-2",
            )

    async def test_publish_stores_publish_result(self):
        draft = await self.service.upload_source(
            filename="reading_sample.txt",
            content=b"Passage one.\n\nQuestion style.",
            actor_id="user-1",
        )
        generated = await self.service.generate(
            draft.id,
            DraftGenerateRequest(questions_per_group=1),
            actor_id="user-2",
        )

        published = await self.service.publish(generated.id, actor_id="publisher-1")

        self.assertEqual("published", published.status.value)
        self.assertEqual("hash-123", published.publish_result.source_hash)
        self.assertEqual("publisher-1", self.service.uploader.calls[0][1])

    async def test_publish_duplicate_skip_is_still_marked_published(self):
        service = PassageExamWorkflowService(
            workflow_operations=self.operations,
            generator=FakeGenerator(),
            uploader=FakeUploader(skipped=True),
        )
        draft = await service.upload_source(
            filename="reading_sample.txt",
            content=b"Passage one.\n\nQuestion style.",
            actor_id="user-1",
        )
        await service.generate(draft.id, DraftGenerateRequest(questions_per_group=1), actor_id="user-2")

        published = await service.publish(draft.id, actor_id="publisher-1")

        self.assertEqual("published", published.status.value)
        self.assertTrue(published.publish_result.skipped)
        self.assertEqual("material-1", published.publish_result.duplicate_material_id)

    async def test_list_drafts(self):
        await self.service.upload_source(
            filename="sample.txt",
            content=b"Passage 1",
            actor_id="user-1",
        )
        drafts = await self.service.list_drafts(search="sample", limit=10)
        self.assertEqual(1, len(drafts))
        self.assertEqual("sample.txt", drafts[0].source_filename)

    async def test_get_draft_not_found(self):
        from src.workflow import DraftNotFoundError
        with self.assertRaises(DraftNotFoundError):
            await self.service.get_draft("non_existent")

    async def test_update_draft_title_and_description(self):
        draft = await self.service.upload_source(
            filename="sample.txt",
            content=b"Passage 1",
            actor_id="user-1",
        )
        updated = await self.service.update_draft(
            draft.id,
            DraftUpdateRequest(title="New Title", description="New Desc"),
            actor_id="user-2",
        )
        self.assertEqual("New Title", updated.title)
        self.assertEqual("New Desc", updated.description)

    async def test_validate_draft_missing_document(self):
        draft = await self.service.upload_source(
            filename="sample.txt",
            content=b"Passage 1",
            actor_id="user-1",
        )
        result = await self.service.validate_draft(draft.id)
        self.assertFalse(result.valid)
        self.assertEqual("missing_document", result.issues[0].issue_type)

    async def test_validate_draft_valid(self):
        draft = await self.service.upload_source(
            filename="sample.txt",
            content=b"Passage 1",
            actor_id="user-1",
        )
        await self.service.generate(
            draft.id,
            DraftGenerateRequest(questions_per_group=1),
            actor_id="user-2",
        )
        result = await self.service.validate_draft(draft.id)
        self.assertTrue(result.valid)

    async def test_publish_missing_document(self):
        draft = await self.service.upload_source(
            filename="sample.txt",
            content=b"Passage 1",
            actor_id="user-1",
        )
        with self.assertRaises(ValueError):
            await self.service.publish(draft.id, actor_id="user-2")

    async def test_default_constructor(self):
        service = PassageExamWorkflowService()
        self.assertIsNotNone(service.workflow_operations)

    async def test_list_drafts_with_filters(self):
        await self.service.upload_source(
            filename="sample.txt",
            content=b"Passage 1",
            actor_id="user-1",
        )
        from src.workflow import DraftStatus
        drafts = await self.service.list_drafts(
            status=DraftStatus.UPLOADED,
            created_by="user-1",
            updated_after="2020-01-01T00:00:00Z",
            updated_before="2030-01-01T00:00:00Z"
        )
        self.assertEqual(1, len(drafts))

    async def test_update_draft_not_found_on_update(self):
        from src.workflow import DraftNotFoundError
        with self.assertRaises(DraftNotFoundError):
            await self.service.update_draft(
                "non_existent",
                DraftUpdateRequest(title="New Title"),
                actor_id="user-2",
            )

    async def test_update_draft_with_existing_document_only_title(self):
        draft = await self.service.upload_source(
            filename="sample.txt",
            content=b"Passage one.\n\nQuestion style.",
            actor_id="user-1",
        )
        generated = await self.service.generate(
            draft.id,
            DraftGenerateRequest(questions_per_group=1),
            actor_id="user-2",
        )
        updated = await self.service.update_draft(
            generated.id,
            DraftUpdateRequest(title="Updated Title Without Doc"),
            actor_id="user-3",
        )
        self.assertEqual("Updated Title Without Doc", updated.title)
        self.assertIsNotNone(updated.normalized_document_json)

    async def test_validate_draft_invalid_document(self):
        draft = await self.service.upload_source(
            filename="sample.txt",
            content=b"Passage one.\n\nQuestion style.",
            actor_id="user-1",
        )
        generated = await self.service.generate(
            draft.id,
            DraftGenerateRequest(questions_per_group=1),
            actor_id="user-2",
        )
        invalid_payload = make_document()
        # Make it invalid by violating single correct choice constraint
        invalid_payload["groups"][0]["questions"][0]["choices"][1]["is_correct"] = True
        
        with self.assertRaises(ValidationError):
            await self.service.update_draft(
                generated.id,
                DraftUpdateRequest(normalized_document_json=invalid_payload),
                actor_id="user-3"
            )
        
        # Bypass direct update validation to simulate bad state in DB
        self.operations.drafts[draft.id]["normalized_document_json"] = invalid_payload
        
        result = await self.service.validate_draft(draft.id)
        self.assertFalse(result.valid)
        self.assertTrue(len(result.issues) > 0)
        self.assertEqual("value_error", result.issues[0].issue_type)

    async def test_publish_failure_records_event(self):
        class FailingUploader(FakeUploader):
            async def upload(self, *args, **kwargs):
                raise RuntimeError("Hasura connection error")

        service = PassageExamWorkflowService(
            workflow_operations=self.operations,
            generator=FakeGenerator(),
            uploader=FailingUploader(),
        )
        draft = await service.upload_source(
            filename="sample.txt",
            content=b"Passage one.\n\nQuestion style.",
            actor_id="user-1",
        )
        generated = await service.generate(
            draft.id,
            DraftGenerateRequest(questions_per_group=1),
            actor_id="user-2",
        )
        with self.assertRaises(RuntimeError):
            await service.publish(generated.id, actor_id="publisher-1")
            
        draft_detail = await service.get_draft(generated.id)
        self.assertEqual("publish_failed", draft_detail.status.value)
        self.assertEqual("Hasura connection error", draft_detail.error_message)
        self.assertEqual("publish_failed", draft_detail.events[0].event_type)


if __name__ == "__main__":
    unittest.main()
