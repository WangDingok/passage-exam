from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DraftStatus(str, Enum):
    UPLOADED = "uploaded"
    GENERATED = "generated"
    REVIEWING = "reviewing"
    PUBLISH_FAILED = "publish_failed"
    PUBLISHED = "published"


class PublishResultPayload(BaseModel):
    source_hash: str
    parent_question_ids: List[str] = Field(default_factory=list)
    child_question_ids: List[str] = Field(default_factory=list)
    exam_id: Optional[str] = None
    material_id: Optional[str] = None
    skipped: bool = False
    duplicate_material_id: Optional[str] = None


class ValidationIssue(BaseModel):
    path: str
    message: str
    issue_type: str


class DraftSummary(BaseModel):
    id: str
    title: str
    description: str = ""
    status: DraftStatus
    source_filename: str
    source_extension: str
    created_by: str
    updated_by: str
    created_at: str
    updated_at: str
    published_at: Optional[str] = None
    error_message: Optional[str] = None
    publish_result: Optional[PublishResultPayload] = None


class DraftEvent(BaseModel):
    id: str
    draft_id: str
    event_type: str
    payload_json: Dict[str, Any] = Field(default_factory=dict)
    actor_id: str
    created_at: str


class DraftDetail(DraftSummary):
    source_text: str
    normalized_document_json: Optional[Dict[str, Any]] = None
    generation_params_json: Optional[Dict[str, Any]] = None
    events: List[DraftEvent] = Field(default_factory=list)


class DraftUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    normalized_document_json: Optional[Dict[str, Any]] = None


class DraftGenerateRequest(BaseModel):
    questions_per_group: Optional[int] = Field(default=None, ge=1)


class ValidationResponse(BaseModel):
    valid: bool
    issues: List[ValidationIssue] = Field(default_factory=list)
