import os
import unittest
from unittest.mock import patch

from src.generator import (
    AnswerKeyPayload,
    GeneratedGroupsPayload,
    PassageExamGenerator,
    AzureOpenAIPassageClient,
    build_document_from_state,
    build_generation_state,
)
from src.parser import ParsedSourceDocument


def validate_groups(payload):
    validate_method = getattr(GeneratedGroupsPayload, "model_validate", GeneratedGroupsPayload.parse_obj)
    return validate_method(payload)


def validate_answers(payload):
    validate_method = getattr(AnswerKeyPayload, "model_validate", AnswerKeyPayload.parse_obj)
    return validate_method(payload)


class FakePassageClient:
    def __init__(self, groups_payload, answers_payload):
        self.groups_payload = groups_payload
        self.answers_payload = answers_payload
        self.calls = []

    async def generate_groups(self, **kwargs):
        self.calls.append(("groups", kwargs))
        return self.groups_payload

    async def answer_quiz(self, **kwargs):
        self.calls.append(("answers", kwargs))
        return self.answers_payload


class PassageExamGeneratorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.source = ParsedSourceDocument(
            path="sample.docx",
            title="Sample",
            text="Doan van mau.\n\nCau hoi mau.",
        )
        self.groups_payload = {
            "groups": [
                {
                    "order": 1,
                    "passage": "Doan van moi",
                    "questions": [
                        {
                            "order": 1,
                            "question": "Tac gia muon nhan manh dieu gi?",
                            "choices": [
                                {"content": "Lua chon A"},
                                {"content": "Lua chon B"},
                                {"content": "Lua chon C"},
                                {"content": "Lua chon D"},
                            ],
                        }
                    ],
                }
            ],
        }
        self.answers_payload = {
            "answers": [
                {
                    "group_order": 1,
                    "question_order": 1,
                    "correct_choice_order": 2,
                }
            ]
        }

    async def test_generate_builds_state_then_fills_final_document(self):
        client = FakePassageClient(self.groups_payload, self.answers_payload)
        generator = PassageExamGenerator(client=client)

        document = await generator.generate(
            source=self.source,
            questions_per_group=1,
        )

        self.assertEqual("Sample", document.title)
        self.assertEqual("Generated from source file Sample", document.description)
        self.assertEqual(2, len(client.calls))
        self.assertEqual("groups", client.calls[0][0])
        self.assertEqual("answers", client.calls[1][0])
        self.assertEqual("<p>Doan van moi</p>", document.groups[0].passage)
        self.assertEqual("<p>Tac gia muon nhan manh dieu gi?</p>", document.groups[0].questions[0].question)
        self.assertEqual(
            [False, True, False, False],
            [choice.is_correct for choice in document.groups[0].questions[0].choices],
        )
        self.assertEqual("<p>Lua chon A</p>", document.groups[0].questions[0].choices[0].content)

    async def test_generate_reports_progress_stages(self):
        client = FakePassageClient(self.groups_payload, self.answers_payload)
        generator = PassageExamGenerator(client=client)
        progress_updates = []

        async def capture_progress(stage, payload):
            progress_updates.append((stage, payload))

        await generator.generate(
            source=self.source,
            questions_per_group=1,
            progress_callback=capture_progress,
        )

        self.assertEqual(
            [
                "starting",
                "requesting_groups",
                "groups_generated",
                "requesting_answers",
                "answers_generated",
                "completed",
            ],
            [stage for stage, _ in progress_updates],
        )
        self.assertEqual(1, progress_updates[2][1]["groups_count"])
        self.assertEqual(1, progress_updates[2][1]["questions_count"])

    def test_build_document_from_state_rejects_mismatched_answers(self):
        state = build_generation_state(
            title="De doc hieu moi",
            description="Sinh tu mau",
            groups_payload=validate_groups(self.groups_payload),
        )
        answer_key = validate_answers(
            {
                "answers": [
                    {
                        "group_order": 1,
                        "question_order": 2,
                        "correct_choice_order": 1,
                    }
                ]
            }
        )

        with self.assertRaisesRegex(ValueError, "answer key does not match generated quiz state"):
            build_document_from_state(
                state=state,
                answer_key=answer_key,
            )


class AzureOpenAIPassageClientTests(unittest.TestCase):
    @patch.dict(os.environ, {
        "AZURE_OPENAI_API_KEY": "fake-key",
        "AZURE_OPENAI_ENDPOINT": "https://fake.openai.azure.com/",
        "AZURE_OPENAI_API_VERSION": "2025-01-01-preview"
    })
    def test_client_initialization_with_env_vars(self):
        previous = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")
        os.environ.pop("AZURE_OPENAI_DEPLOYMENT_NAME", None)
        try:
            client = AzureOpenAIPassageClient()
            self.assertEqual("fake-key", client.api_key)
            self.assertEqual("https://fake.openai.azure.com/", client.azure_endpoint)
            self.assertEqual("2025-01-01-preview", client.api_version)
            self.assertEqual("gpt-4o", client.deployment_name)
        finally:
            if previous is not None:
                os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"] = previous

    def test_client_initialization_missing_env_vars(self):
        with patch.dict(os.environ):
            os.environ.pop("AZURE_OPENAI_API_KEY", None)
            os.environ.pop("AZURE_OPENAI_ENDPOINT", None)
            os.environ.pop("AZURE_OPENAI_API_VERSION", None)
            with self.assertRaisesRegex(ValueError, "Azure OpenAI credentials are required"):
                AzureOpenAIPassageClient()


if __name__ == "__main__":
    unittest.main()
