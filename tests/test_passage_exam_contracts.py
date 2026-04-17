import unittest

from pydantic import ValidationError

from src.contracts import PassageExamDocument


def validate_document(payload):
    validate_method = getattr(PassageExamDocument, "model_validate", PassageExamDocument.parse_obj)
    return validate_method(payload)


class PassageExamContractsTests(unittest.TestCase):
    def test_rejects_empty_group_passage(self):
        with self.assertRaises(ValidationError):
            validate_document(
                {
                    "title": "Exam",
                    "groups": [
                        {
                            "order": 1,
                            "passage": " ",
                            "questions": [
                                {
                                    "order": 1,
                                    "type": "multiple_choice",
                                    "question": "<p>Q1</p>",
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
            )

    def test_rejects_multiple_correct_answers(self):
        with self.assertRaises(ValidationError):
            validate_document(
                {
                    "title": "Exam",
                    "groups": [
                        {
                            "order": 1,
                            "passage": "<p>Passage</p>",
                            "questions": [
                                {
                                    "order": 1,
                                    "type": "multiple_choice",
                                    "question": "<p>Q1</p>",
                                    "choices": [
                                        {"content": "<p>A</p>", "is_correct": True},
                                        {"content": "<p>B</p>", "is_correct": True},
                                        {"content": "<p>C</p>", "is_correct": False},
                                        {"content": "<p>D</p>", "is_correct": False},
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )

    def test_rejects_choice_count_other_than_four(self):
        with self.assertRaises(ValidationError):
            validate_document(
                {
                    "title": "Exam",
                    "groups": [
                        {
                            "order": 1,
                            "passage": "<p>Passage</p>",
                            "questions": [
                                {
                                    "order": 1,
                                    "type": "multiple_choice",
                                    "question": "<p>Q1</p>",
                                    "choices": [
                                        {"content": "<p>A</p>", "is_correct": True},
                                        {"content": "<p>B</p>", "is_correct": False},
                                        {"content": "<p>C</p>", "is_correct": False},
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )

    def test_rejects_duplicate_question_order_within_group(self):
        with self.assertRaises(ValidationError):
            validate_document(
                {
                    "title": "Exam",
                    "groups": [
                        {
                            "order": 1,
                            "passage": "<p>Passage</p>",
                            "questions": [
                                {
                                    "order": 1,
                                    "type": "multiple_choice",
                                    "question": "<p>Q1</p>",
                                    "choices": [
                                        {"content": "<p>A</p>", "is_correct": True},
                                        {"content": "<p>B</p>", "is_correct": False},
                                        {"content": "<p>C</p>", "is_correct": False},
                                        {"content": "<p>D</p>", "is_correct": False},
                                    ],
                                },
                                {
                                    "order": 1,
                                    "type": "multiple_choice",
                                    "question": "<p>Q2</p>",
                                    "choices": [
                                        {"content": "<p>A</p>", "is_correct": False},
                                        {"content": "<p>B</p>", "is_correct": True},
                                        {"content": "<p>C</p>", "is_correct": False},
                                        {"content": "<p>D</p>", "is_correct": False},
                                    ],
                                },
                            ],
                        }
                    ],
                }
            )


if __name__ == "__main__":
    unittest.main()
