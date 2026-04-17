from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from loguru import logger

from ..contracts import PassageExamDocument, PassageGroup
from ..graphql import ExamOperations, GraphQLError, HasuraGraphQLClient, PassageQuestionOperations
from ..utils import (
    append_hash_marker,
    canonical_document_hash,
    deterministic_material_id,
    ensure_html_paragraphs,
    source_hash_marker,
)

DEFAULT_LAYOUT_ANSWER = 2
DEFAULT_QUESTION_TIME = 60
DEFAULT_QUESTION_POINT = 0
SUPPORTED_IDEMPOTENCY_MODES = {"off", "skip", "fail"}


class DuplicateExamError(Exception):
    """Raised when an upload is blocked by idempotency rules."""


@dataclass
class UploadResult:
    source_hash: str
    parent_question_ids: List[str] = field(default_factory=list)
    child_question_ids: List[str] = field(default_factory=list)
    exam_id: Optional[str] = None
    material_id: Optional[str] = None
    skipped: bool = False
    duplicate_material_id: Optional[str] = None


class CategoryResolver:

    def __init__(self, categories: Iterable[Dict[str, Any]]):
        self.categories = list(categories)

    def resolve(self, *codes: str) -> str:
        matches = self._find_terminal_matches(self.categories, list(codes))
        if not matches:
            raise ValueError(
                f"question category path not found: {' -> '.join(codes)}")
        if len(matches) > 1:
            matched_ids = ", ".join(
                sorted(match.get("id", "<missing>") for match in matches))
            raise ValueError(
                f"question category path is ambiguous for {' -> '.join(codes)}: {matched_ids}"
            )

        category_id = matches[0].get("id")
        if not category_id:
            raise ValueError(
                f"question category id missing for path: {' -> '.join(codes)}")
        return category_id

    def _find_terminal_matches(
        self,
        nodes: Iterable[Dict[str, Any]],
        remaining_codes: List[str],
    ) -> List[Dict[str, Any]]:
        if not remaining_codes:
            return []

        current_code = remaining_codes[0]
        matches: List[Dict[str, Any]] = []
        for node in nodes:
            if node.get("code") != current_code:
                continue
            if len(remaining_codes) == 1:
                matches.append(node)
                continue
            matches.extend(
                self._find_terminal_matches(node.get("children", []),
                                            remaining_codes[1:]))
        return matches

    def group_category_id(self) -> str:
        return self.resolve("basic_question", "group")

    def single_choice_category_id(self) -> str:
        return self.resolve("basic_question", "multiple_choice",
                            "single_choice")


def build_passage_group_payload(group: PassageGroup, *, created_by: str,
                                resolver: CategoryResolver) -> Dict[str, Any]:
    group_category_id = resolver.group_category_id()
    single_choice_category_id = resolver.single_choice_category_id()

    child_questions = []
    for question in sorted(group.questions, key=lambda item: item.order):
        child_questions.append({
            "category_id":
            single_choice_category_id,
            "name":
            ensure_html_paragraphs(question.question),
            "created_by":
            created_by,
            "is_deleted":
            False,
            "is_bank":
            False,
            "is_show":
            True,
            "is_published":
            False,
            "must_response":
            False,
            "layout_answer":
            DEFAULT_LAYOUT_ANSWER,
            "point":
            DEFAULT_QUESTION_POINT,
            "time":
            DEFAULT_QUESTION_TIME,
            "asset_type":
            "",
            "asset_url":
            "",
            "embedded_url":
            "",
            "content_preview":
            "",
            "order_number":
            question.order,
            "questions_hotspots": {
                "data": [{
                    "content": ensure_html_paragraphs(choice.content),
                    "is_correct": choice.is_correct,
                    "order_number": index,
                    "created_by": created_by,
                    "is_deleted": False,
                    "asset_type": "",
                    "asset_url": "",
                    "embedded_url": "",
                } for index, choice in enumerate(question.choices, start=1)]
            },
        })

    return {
        "category_id": group_category_id,
        "name": ensure_html_paragraphs(group.passage),
        "created_by": created_by,
        "is_deleted": False,
        "is_bank": False,
        "is_show": True,
        "is_published": False,
        "must_response": False,
        "layout_answer": DEFAULT_LAYOUT_ANSWER,
        "point": DEFAULT_QUESTION_POINT,
        "time": DEFAULT_QUESTION_TIME,
        "asset_type": "",
        "asset_url": "",
        "embedded_url": "",
        "content_preview": "",
        "order_number": group.order,
        "questions_hotspots": {
            "data": []
        },
        "sub_questions": {
            "data": child_questions
        },
    }


def build_exam_payload(
    document: PassageExamDocument,
    *,
    created_by: str,
    exam_category_id: str,
    material_id: Optional[str],
    resolver: CategoryResolver,
    source_hash: str,
) -> Dict[str, Any]:
    description_with_hash = append_hash_marker(document.description,
                                               source_hash)
    material_data = {
        "title": document.title,
        "description": description_with_hash,
        "category_id": exam_category_id,
        "created_by": created_by,
        "is_published": False,
        "is_deleted": False,
        "is_storaged": False,
        "is_class": False,
        "status": True,
    }
    if material_id:
        material_data["id"] = material_id

    return {
        "object": {
            "description": description_with_hash,
            "created_by": created_by,
            "is_deleted": False,
            "materials": {
                "data": material_data
            },
            "exam_questions": {
                "data": [{
                    "created_by": created_by,
                    "is_deleted": False,
                    "question": {
                        "data":
                        build_passage_group_payload(
                            group,
                            created_by=created_by,
                            resolver=resolver,
                        )
                    },
                } for group in sorted(document.groups,
                                      key=lambda item: item.order)]
            },
        }
    }


class PassageExamUploader:

    def __init__(
        self,
        *,
        question_operations: Optional[PassageQuestionOperations] = None,
        exam_operations: Optional[ExamOperations] = None,
    ):
        if question_operations is None or exam_operations is None:
            client = HasuraGraphQLClient()
            question_operations = question_operations or PassageQuestionOperations(
                client)
            exam_operations = exam_operations or ExamOperations(client)
        self.question_operations = question_operations
        self.exam_operations = exam_operations

    async def upload(
        self,
        document: PassageExamDocument,
        *,
        created_by: str,
        idempotency: str = "skip",
    ) -> UploadResult:
        if idempotency not in SUPPORTED_IDEMPOTENCY_MODES:
            raise ValueError(
                f"idempotency must be one of {sorted(SUPPORTED_IDEMPOTENCY_MODES)}"
            )

        source_hash = canonical_document_hash(document)
        result = UploadResult(source_hash=source_hash)
        hash_marker = source_hash_marker(source_hash)
        locked_material_id = deterministic_material_id(
            source_hash) if idempotency != "off" else None

        if idempotency != "off":
            existing_material = await self.exam_operations.find_existing_material(
                document.title, hash_marker)
            if existing_material:
                material_id = existing_material.get("id")
                if idempotency == "fail":
                    raise DuplicateExamError(
                        f"existing material found for source hash {source_hash}: {material_id}"
                    )
                logger.info(
                    "Skipping upload for '{}' because matching source hash already exists",
                    document.title)
                result.skipped = True
                result.duplicate_material_id = material_id
                result.material_id = material_id
                return result

        categories = await self.question_operations.get_categories()
        resolver = CategoryResolver(categories)
        exam_category_id = await self._resolve_exam_category_id()

        logger.info("Building exam payload for '{}'", document.title)
        exam_payload = build_exam_payload(
            document,
            created_by=created_by,
            exam_category_id=exam_category_id,
            material_id=locked_material_id,
            resolver=resolver,
            source_hash=source_hash,
        )
        try:
            logger.info("Uploading exam '{}' to Hasura", document.title)
            inserted_exam = await self.exam_operations.create_exam(exam_payload
                                                                   )
            logger.info(
                "Successfully uploaded exam '{}' with material_id: {} and exam_id: {}",
                document.title, inserted_exam.get("material_id"),
                inserted_exam.get("id"))
        except GraphQLError as error:
            duplicate_material = None
            if locked_material_id:
                duplicate_material = await self.exam_operations.find_material_by_id(
                    locked_material_id)
            if duplicate_material:
                if idempotency == "fail":
                    raise DuplicateExamError(
                        f"existing material found for source hash {source_hash}: {locked_material_id}"
                    ) from error

                logger.info(
                    "Skipping upload for '{}' because deterministic material id {} already exists",
                    document.title,
                    locked_material_id,
                )
                result.skipped = True
                result.duplicate_material_id = duplicate_material.get("id")
                result.material_id = duplicate_material.get("id")
                return result
            raise

        result.exam_id = inserted_exam.get("id")
        result.material_id = inserted_exam.get("material_id")
        for exam_question in inserted_exam.get("exam_questions", []):
            question_id = exam_question.get("question_id")
            if question_id:
                result.parent_question_ids.append(question_id)

            question = exam_question.get("question") or {}
            result.child_question_ids.extend(
                sub_question.get("id")
                for sub_question in question.get("sub_questions", [])
                if sub_question.get("id"))
        return result

    async def _resolve_exam_category_id(self) -> str:
        material_categories = await self.exam_operations.get_material_categories(
        )
        for category in material_categories:
            if category.get("code") == "exam":
                category_id = category.get("id")
                if category_id:
                    return category_id
        raise ValueError("material category with code 'exam' not found")
