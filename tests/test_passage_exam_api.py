import importlib.util
import io
import os
import unittest


FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None


if FASTAPI_AVAILABLE:
    from fastapi.testclient import TestClient

    from src.api.app import create_app, get_workflow_service
    from src.workflow import DraftGenerateRequest


    class FakeWorkflowService:
        async def list_drafts(self, **kwargs):
            del kwargs
            return []

        async def get_draft(self, draft_id):
            return {
                "id": draft_id,
                "title": "Draft",
                "description": "",
                "status": "uploaded",
                "source_filename": "sample.txt",
                "source_extension": "txt",
                "created_by": "user-1",
                "updated_by": "user-1",
                "created_at": "2026-04-17T00:00:00+00:00",
                "updated_at": "2026-04-17T00:00:00+00:00",
                "published_at": None,
                "error_message": None,
                "publish_result": None,
                "source_text": "Passage",
                "normalized_document_json": None,
                "generation_params_json": None,
                "events": [],
            }

        async def upload_source(self, *, filename, content, actor_id):
            return {
                "id": "draft-1",
                "title": filename,
                "description": "",
                "status": "uploaded",
                "source_filename": filename,
                "source_extension": "txt",
                "created_by": actor_id,
                "updated_by": actor_id,
                "created_at": "2026-04-17T00:00:00+00:00",
                "updated_at": "2026-04-17T00:00:00+00:00",
                "published_at": None,
                "error_message": None,
                "publish_result": None,
                "source_text": content.decode("utf-8"),
                "normalized_document_json": None,
                "generation_params_json": None,
                "events": [],
            }

        async def generate(self, draft_id, request: DraftGenerateRequest, *, actor_id):
            del request, actor_id
            return await self.get_draft(draft_id)

        async def update_draft(self, draft_id, request, *, actor_id):
            del request, actor_id
            return await self.get_draft(draft_id)

        async def validate_draft(self, draft_id):
            del draft_id
            return {"valid": True, "issues": []}

        async def publish(self, draft_id, *, actor_id, idempotency):
            del actor_id, idempotency
            return await self.get_draft(draft_id)


class PassageExamApiTests(unittest.TestCase):
    @unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
    def test_upload_endpoint_accepts_file_and_actor_header(self):
        app = create_app()
        app.dependency_overrides[get_workflow_service] = lambda: FakeWorkflowService()
        client = TestClient(app)

        response = client.post(
            "/drafts/upload",
            headers={"X-User-Id": "api-user"},
            files={"file": ("sample.txt", io.BytesIO(b"Hello workflow"), "text/plain")},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("sample.txt", response.json()["source_filename"])

    @unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
    def test_publish_endpoint_prefers_env_created_by_over_header(self):
        app = create_app()
        app.dependency_overrides[get_workflow_service] = lambda: FakeWorkflowService()
        client = TestClient(app)

        previous = os.environ.get("PASSAGE_EXAM_CREATED_BY")
        os.environ["PASSAGE_EXAM_CREATED_BY"] = "env-user"
        try:
            response = client.post(
                "/drafts/draft-1/publish",
                headers={"X-User-Id": "header-user"},
            )
        finally:
            if previous is None:
                os.environ.pop("PASSAGE_EXAM_CREATED_BY", None)
            else:
                os.environ["PASSAGE_EXAM_CREATED_BY"] = previous

        self.assertEqual(200, response.status_code)

    @unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
    def test_upload_endpoint_returns_401_when_no_actor_id_provided(self):
        app = create_app()
        app.dependency_overrides[get_workflow_service] = lambda: FakeWorkflowService()
        client = TestClient(app)

        previous = os.environ.get("PASSAGE_EXAM_CREATED_BY")
        os.environ.pop("PASSAGE_EXAM_CREATED_BY", None)
        try:
            response = client.post(
                "/drafts/upload",
                files={"file": ("sample.txt", io.BytesIO(b"Hello workflow"), "text/plain")},
            )
        finally:
            if previous is not None:
                os.environ["PASSAGE_EXAM_CREATED_BY"] = previous

        self.assertEqual(401, response.status_code)
        self.assertEqual("PASSAGE_EXAM_CREATED_BY env or X-User-Id header is required", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
