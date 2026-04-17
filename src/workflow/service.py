from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from pydantic import ValidationError

from ..contracts import PassageExamDocument
from ..generator import PassageExamGenerator
from ..graphql import HasuraGraphQLClient, PassageExamWorkflowOperations
from ..parser import ParsedSourceDocument, parse_source_bytes
from ..uploader import PassageExamUploader
from .contracts import (
    DraftDetail,
    DraftEvent,
    DraftGenerateRequest,
    DraftStatus,
    DraftSummary,
    DraftUpdateRequest,
    PublishResultPayload,
    ValidationIssue,
    ValidationResponse,
)


class DraftNotFoundError(Exception):
    """Raised when a draft cannot be found in the workflow store."""


def validate_document_payload(payload: Dict[str, Any]) -> PassageExamDocument:
    return PassageExamDocument.model_validate(payload)


def document_to_payload(document: PassageExamDocument) -> Dict[str, Any]:
    return document.model_dump()


def model_to_payload(model: Any) -> Dict[str, Any]:
    return model.model_dump()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_validation_issues(error: ValidationError) -> List[ValidationIssue]:
    issues = []
    for item in error.errors():
        path = ".".join(str(part) for part in item.get("loc", [])) or "$"
        issues.append(
            ValidationIssue(
                path=path,
                message=item.get("msg", "invalid value"),
                issue_type=item.get("type", "validation_error"),
            ))
    return issues


def _coerce_publish_result(
        value: Optional[Dict[str, Any]]) -> Optional[PublishResultPayload]:
    if not value:
        return None
    return PublishResultPayload.model_validate(value)


def _coerce_event(row: Dict[str, Any]) -> DraftEvent:
    payload = dict(row)
    payload["payload_json"] = payload.get("payload_json") or {}
    return DraftEvent.model_validate(payload)


def _coerce_summary(row: Dict[str, Any]) -> DraftSummary:
    payload = dict(row)
    payload["publish_result"] = _coerce_publish_result(
        payload.pop("publish_result_json", None))
    return DraftSummary.model_validate(payload)


def _coerce_detail(row: Dict[str, Any],
                   events: Iterable[Dict[str, Any]]) -> DraftDetail:
    payload = dict(row)
    payload["publish_result"] = _coerce_publish_result(
        payload.pop("publish_result_json", None))
    payload["events"] = [_coerce_event(event) for event in events]
    return DraftDetail.model_validate(payload)


class PassageExamWorkflowService:

    def __init__(
        self,
        *,
        workflow_operations: Optional[PassageExamWorkflowOperations] = None,
        generator: Optional[PassageExamGenerator] = None,
        uploader: Optional[PassageExamUploader] = None,
    ):
        if workflow_operations is None:
            workflow_operations = PassageExamWorkflowOperations(
                HasuraGraphQLClient())
        self.workflow_operations = workflow_operations
        self.generator = generator or PassageExamGenerator()
        self.uploader = uploader or PassageExamUploader()

    async def _create_draft_event(
        self,
        *,
        draft_id: str,
        event_type: str,
        actor_id: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        await self.workflow_operations.create_event({
            "draft_id": draft_id,
            "event_type": event_type,
            "payload_json": payload or {},
            "actor_id": actor_id,
        })

    async def list_drafts(
        self,
        *,
        status: Optional[DraftStatus] = None,
        search: Optional[str] = None,
        created_by: Optional[str] = None,
        updated_after: Optional[str] = None,
        updated_before: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[DraftSummary]:
        where: Dict[str, Any] = {}
        conditions: List[Dict[str, Any]] = []
        if status:
            conditions.append({"status": {"_eq": status.value}})
        if search:
            pattern = f"%{search.strip()}%"
            conditions.append({
                "_or": [
                    {
                        "title": {
                            "_ilike": pattern
                        }
                    },
                    {
                        "source_filename": {
                            "_ilike": pattern
                        }
                    },
                    {
                        "description": {
                            "_ilike": pattern
                        }
                    },
                ]
            })
        if created_by:
            conditions.append({"created_by": {"_eq": created_by}})
        if updated_after:
            conditions.append({"updated_at": {"_gte": updated_after}})
        if updated_before:
            conditions.append({"updated_at": {"_lte": updated_before}})
        if conditions:
            where = {"_and": conditions}

        rows = await self.workflow_operations.list_drafts(where=where,
                                                          limit=limit,
                                                          offset=offset)
        return [_coerce_summary(row) for row in rows]

    async def get_draft(self, draft_id: str) -> DraftDetail:
        result = await self.workflow_operations.get_draft(draft_id)
        draft = result.get("draft")
        if not draft:
            raise DraftNotFoundError(f"draft not found: {draft_id}")
        return _coerce_detail(draft, result.get("events", []))

    async def upload_source(self, *, filename: str, content: bytes,
                            actor_id: str) -> DraftDetail:
        source = parse_source_bytes(filename, content)
        draft = await self.workflow_operations.create_draft({
            "title":
            source.title,
            "description":
            "",
            "status":
            DraftStatus.UPLOADED.value,
            "source_filename":
            filename,
            "source_extension":
            filename.rsplit(".", 1)[-1].lower() if "." in filename else "",
            "source_text":
            source.text,
            "normalized_document_json":
            None,
            "generation_params_json":
            None,
            "publish_result_json":
            None,
            "error_message":
            None,
            "created_by":
            actor_id,
            "updated_by":
            actor_id,
        })
        await self.workflow_operations.create_event({
            "draft_id": draft["id"],
            "event_type": "uploaded",
            "payload_json": {
                "source_filename": filename,
                "source_title": source.title,
                "source_path": source.path,
                "source_text_length": len(source.text),
            },
            "actor_id": actor_id,
        })
        return await self.get_draft(draft["id"])

    async def generate(self, draft_id: str, request: DraftGenerateRequest, *,
                       actor_id: str) -> DraftDetail:
        draft = await self.get_draft(draft_id)
        source = ParsedSourceDocument(
            path=draft.source_filename,
            title=draft.title,
            text=draft.source_text,
        )

        async def report_generation_progress(stage: str,
                                             payload: Dict[str, Any]) -> None:
            await self._create_draft_event(
                draft_id=draft_id,
                event_type="generation_progress",
                actor_id=actor_id,
                payload={
                    "stage": stage,
                    **payload,
                },
            )

        await self._create_draft_event(
            draft_id=draft_id,
            event_type="generation_started",
            actor_id=actor_id,
            payload={
                "questions_per_group": request.questions_per_group,
                "source_filename": draft.source_filename,
                "source_text_length": len(draft.source_text),
                "message": "Generation request started.",
            },
        )
        document = await self.generator.generate(
            source=source,
            title=draft.title,
            description=draft.description,
            questions_per_group=request.questions_per_group,
            progress_callback=report_generation_progress,
        )
        payload = document_to_payload(document)
        updated_at = _now_iso()
        updated = await self.workflow_operations.update_draft(
            draft_id,
            {
                "title": document.title,
                "description": document.description,
                "status": DraftStatus.GENERATED.value,
                "normalized_document_json": payload,
                "generation_params_json": {
                    "questions_per_group": request.questions_per_group,
                    "generated_at": _now_iso(),
                },
                "publish_result_json": None,
                "error_message": None,
                "updated_by": actor_id,
                "updated_at": updated_at,
            },
        )
        if not updated:
            raise DraftNotFoundError(f"draft not found: {draft_id}")
        await self._create_draft_event(
            draft_id=draft_id,
            event_type="generated",
            actor_id=actor_id,
            payload={
                "questions_per_group":
                request.questions_per_group,
                "groups_count":
                len(document.groups),
                "questions_count":
                sum(len(group.questions) for group in document.groups),
            },
        )
        return await self.get_draft(draft_id)

    async def update_draft(self, draft_id: str, request: DraftUpdateRequest, *,
                           actor_id: str) -> DraftDetail:
        draft = await self.get_draft(draft_id)
        current_document = (validate_document_payload(
            draft.normalized_document_json)
                            if draft.normalized_document_json else None)

        if request.normalized_document_json is not None:
            document = validate_document_payload(
                request.normalized_document_json)
        elif current_document is not None:
            update_data: Dict[str, Any] = {}
            if request.title is not None:
                update_data["title"] = request.title
            if request.description is not None:
                update_data["description"] = request.description
            copy_method = getattr(current_document, "model_copy",
                                  current_document.copy)
            document = copy_method(update=update_data)
        else:
            document = None

        status = DraftStatus.REVIEWING.value if document else draft.status.value
        updated_at = _now_iso()
        payload: Dict[str, Any] = {
            "updated_by": actor_id,
            "status": status,
            "error_message": None,
            "updated_at": updated_at,
        }
        if document:
            payload["title"] = document.title
            payload["description"] = document.description
            payload["normalized_document_json"] = document_to_payload(document)
        else:
            if request.title is not None:
                payload["title"] = request.title
            if request.description is not None:
                payload["description"] = request.description

        updated = await self.workflow_operations.update_draft(
            draft_id, payload)
        if not updated:
            raise DraftNotFoundError(f"draft not found: {draft_id}")
        await self.workflow_operations.create_event({
            "draft_id": draft_id,
            "event_type": "edited",
            "payload_json": {
                "has_normalized_document": document is not None,
                "updated_title": payload.get("title"),
                "updated_description": payload.get("description"),
            },
            "actor_id": actor_id,
        })
        return await self.get_draft(draft_id)

    async def validate_draft(self, draft_id: str) -> ValidationResponse:
        draft = await self.get_draft(draft_id)
        if not draft.normalized_document_json:
            return ValidationResponse(
                valid=False,
                issues=[
                    ValidationIssue(
                        path="normalized_document_json",
                        message="draft has no generated normalized document",
                        issue_type="missing_document",
                    )
                ],
            )
        try:
            validate_document_payload(draft.normalized_document_json)
        except ValidationError as error:
            return ValidationResponse(valid=False,
                                      issues=build_validation_issues(error))
        return ValidationResponse(valid=True, issues=[])

    async def publish(self,
                      draft_id: str,
                      *,
                      actor_id: str,
                      idempotency: str = "skip") -> DraftDetail:
        draft = await self.get_draft(draft_id)
        if not draft.normalized_document_json:
            raise ValueError("draft has no normalized document to publish")

        document = validate_document_payload(draft.normalized_document_json)
        try:
            result = await self.uploader.upload(document,
                                                created_by=actor_id,
                                                idempotency=idempotency)
        except Exception as error:
            updated_at = _now_iso()
            updated = await self.workflow_operations.update_draft(
                draft_id,
                {
                    "status": DraftStatus.PUBLISH_FAILED.value,
                    "error_message": str(error),
                    "updated_by": actor_id,
                    "updated_at": updated_at,
                },
            )
            if not updated:
                raise DraftNotFoundError(
                    f"draft not found: {draft_id}") from error
            await self.workflow_operations.create_event({
                "draft_id": draft_id,
                "event_type": "publish_failed",
                "payload_json": {
                    "error_type": error.__class__.__name__,
                    "error_message": str(error),
                },
                "actor_id": actor_id,
            })
            raise

        publish_result = PublishResultPayload(**result.__dict__)
        updated_at = _now_iso()
        updated = await self.workflow_operations.update_draft(
            draft_id,
            {
                "status": DraftStatus.PUBLISHED.value,
                "publish_result_json": model_to_payload(publish_result),
                "error_message": None,
                "updated_by": actor_id,
                "updated_at": updated_at,
                "published_at": updated_at,
            },
        )
        if not updated:
            raise DraftNotFoundError(f"draft not found: {draft_id}")
        await self.workflow_operations.create_event({
            "draft_id":
            draft_id,
            "event_type":
            "published",
            "payload_json":
            model_to_payload(publish_result),
            "actor_id":
            actor_id,
        })
        return await self.get_draft(draft_id)
