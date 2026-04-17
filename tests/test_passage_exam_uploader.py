import unittest

from src.contracts import PassageExamDocument
from src.graphql import GraphQLError
from src.uploader import (
    CategoryResolver,
    DuplicateExamError,
    PassageExamUploader,
    build_exam_payload,
    build_passage_group_payload,
)
from src.utils import canonical_document_hash, deterministic_material_id


QUESTION_CATEGORIES = [
    {
        "id": "root-basic-wrong-branch",
        "code": "basic_question",
        "children": [],
    },
    {
        "id": "root-basic-right-branch",
        "code": "basic_question",
        "children": [
            {
                "id": "group-category",
                "code": "group",
                "children": [],
            },
            {
                "id": "mc-category",
                "code": "multiple_choice",
                "children": [
                    {
                        "id": "single-choice-category",
                        "code": "single_choice",
                        "children": [],
                    }
                ],
            },
        ],
    }
]


def validate_document(payload):
    validate_method = getattr(PassageExamDocument, "model_validate", PassageExamDocument.parse_obj)
    return validate_method(payload)


class FakeQuestionOperations:
    async def get_categories(self):
        return QUESTION_CATEGORIES


class FakeExamOperations:
    def __init__(self):
        self.find_calls = []
        self.create_calls = []
        self.materials_by_id = {}

    async def get_material_categories(self):
        return [{"id": "exam-category", "code": "exam"}]

    async def find_existing_material(self, title, hash_marker):
        self.find_calls.append((title, hash_marker))
        return None

    async def find_material_by_id(self, material_id):
        return self.materials_by_id.get(material_id)

    async def create_exam(self, payload):
        self.create_calls.append(payload)
        exam_questions = []
        for index, item in enumerate(payload["object"]["exam_questions"]["data"], start=1):
            sub_questions = item["question"]["data"]["sub_questions"]["data"]
            exam_questions.append(
                {
                    "id": f"eq-{index}",
                    "question_id": f"parent-{index}",
                    "question": {
                        "id": f"parent-{index}",
                        "sub_questions": [
                            {"id": f"child-{index}-{child_index + 1}"}
                            for child_index, _ in enumerate(sub_questions)
                        ],
                    },
                }
            )
        return {
            "id": "exam-1",
            "material_id": "material-1",
            "exam_questions": exam_questions,
        }


class FailingExamOperations(FakeExamOperations):
    async def create_exam(self, payload):
        self.create_calls.append(payload)
        raise RuntimeError("exam insert failed")


class ConflictingExamOperations(FakeExamOperations):
    def __init__(self, material_id):
        super().__init__()
        self.materials_by_id[material_id] = {
            "id": material_id,
            "title": "De doc hieu",
            "description": "Sinh tu de mau",
        }

    async def create_exam(self, payload):
        self.create_calls.append(payload)
        raise GraphQLError(
            [
                {
                    "message": 'Uniqueness violation. duplicate key value violates unique constraint "materials_pkey"'
                }
            ]
        )


class PassageExamUploaderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.document = validate_document(
            {
                "title": "De doc hieu",
                "description": "Sinh tu de mau",
                "groups": [
                    {
                        "order": 1,
                        "passage": "Doan van 1",
                        "questions": [
                            {
                                "order": 1,
                                "type": "multiple_choice",
                                "question": "Cau hoi 1",
                                "choices": [
                                    {"content": "Lua chon A", "is_correct": True},
                                    {"content": "Lua chon B", "is_correct": False},
                                    {"content": "Lua chon C", "is_correct": False},
                                    {"content": "Lua chon D", "is_correct": False},
                                ],
                            }
                        ],
                    }
                ],
            }
        )

    def test_category_resolver(self):
        resolver = CategoryResolver(QUESTION_CATEGORIES)

        self.assertEqual("group-category", resolver.group_category_id())
        self.assertEqual("single-choice-category", resolver.single_choice_category_id())

    def test_build_passage_group_payload_preserves_existing_inline_html(self):
        resolver = CategoryResolver(QUESTION_CATEGORIES)
        copy_method = getattr(self.document.groups[0], "model_copy", self.document.groups[0].copy)
        group = copy_method(update={"passage": "<strong>Doan van 1</strong>"})

        payload = build_passage_group_payload(
            group,
            created_by="user-1",
            resolver=resolver,
        )

        self.assertEqual("<strong>Doan van 1</strong>", payload["name"])

    def test_build_passage_group_payload(self):
        resolver = CategoryResolver(QUESTION_CATEGORIES)

        payload = build_passage_group_payload(
            self.document.groups[0],
            created_by="user-1",
            resolver=resolver,
        )

        self.assertEqual("group-category", payload["category_id"])
        self.assertEqual(1, len(payload["sub_questions"]["data"]))
        self.assertEqual("single-choice-category", payload["sub_questions"]["data"][0]["category_id"])
        self.assertEqual(4, len(payload["sub_questions"]["data"][0]["questions_hotspots"]["data"]))

    def test_build_exam_payload_builds_nested_atomic_object(self):
        resolver = CategoryResolver(QUESTION_CATEGORIES)
        material_id = deterministic_material_id("abc123")
        payload = build_exam_payload(
            self.document,
            created_by="user-1",
            exam_category_id="exam-category",
            material_id=material_id,
            resolver=resolver,
            source_hash="abc123",
        )

        exam_object = payload["object"]
        self.assertEqual("De doc hieu", exam_object["materials"]["data"]["title"])
        self.assertEqual(material_id, exam_object["materials"]["data"]["id"])
        self.assertIn("[source_hash:abc123]", exam_object["materials"]["data"]["description"])
        self.assertEqual(1, len(exam_object["exam_questions"]["data"]))
        self.assertEqual(
            "group-category",
            exam_object["exam_questions"]["data"][0]["question"]["data"]["category_id"],
        )

    async def test_upload_flow_uses_parent_question_links(self):
        question_operations = FakeQuestionOperations()
        exam_operations = FakeExamOperations()
        uploader = PassageExamUploader(
            question_operations=question_operations,
            exam_operations=exam_operations,
        )

        result = await uploader.upload(
            self.document,
            created_by="user-1",
            idempotency="skip",
        )

        self.assertFalse(result.skipped)
        self.assertEqual(["parent-1"], result.parent_question_ids)
        self.assertEqual(["child-1-1"], result.child_question_ids)
        self.assertEqual("exam-1", result.exam_id)
        self.assertEqual(1, len(exam_operations.create_calls))
        self.assertEqual(
            "group-category",
            exam_operations.create_calls[0]["object"]["exam_questions"]["data"][0]["question"]["data"]["category_id"],
        )

    async def test_upload_propagates_atomic_exam_insert_failure(self):
        question_operations = FakeQuestionOperations()
        exam_operations = FailingExamOperations()
        uploader = PassageExamUploader(
            question_operations=question_operations,
            exam_operations=exam_operations,
        )

        with self.assertRaisesRegex(RuntimeError, "exam insert failed"):
            await uploader.upload(
                self.document,
                created_by="user-1",
                idempotency="skip",
            )

    async def test_upload_skips_when_material_primary_key_conflict_detects_race_duplicate(self):
        document = self.document
        material_id = deterministic_material_id(canonical_document_hash(document))
        question_operations = FakeQuestionOperations()
        exam_operations = ConflictingExamOperations(material_id)
        uploader = PassageExamUploader(
            question_operations=question_operations,
            exam_operations=exam_operations,
        )

        result = await uploader.upload(
            document,
            created_by="user-1",
            idempotency="skip",
        )

        self.assertTrue(result.skipped)
        self.assertEqual(material_id, result.material_id)
        self.assertEqual(material_id, result.duplicate_material_id)

    async def test_upload_fails_when_material_primary_key_conflict_detects_race_duplicate(self):
        material_id = deterministic_material_id(canonical_document_hash(self.document))
        question_operations = FakeQuestionOperations()
        exam_operations = ConflictingExamOperations(material_id)
        uploader = PassageExamUploader(
            question_operations=question_operations,
            exam_operations=exam_operations,
        )

        with self.assertRaises(DuplicateExamError):
            await uploader.upload(
                self.document,
                created_by="user-1",
                idempotency="fail",
            )


if __name__ == "__main__":
    unittest.main()
