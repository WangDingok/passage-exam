import json
import uuid
import pytest

from src.contracts import PassageExamDocument, PassageGroup, PassageQuestion, QuestionChoice
from src.utils import (
    collapse_whitespace,
    strip_code_fences,
    ensure_html_paragraphs,
    canonical_document_hash,
    source_hash_marker,
    append_hash_marker,
    deterministic_material_id,
    load_json_document,
    get_default_created_by,
)

def test_collapse_whitespace():
    assert collapse_whitespace("  hello \n \t world  ") == "hello world"
    assert collapse_whitespace(None) == ""
    assert collapse_whitespace("") == ""

def test_strip_code_fences():
    assert strip_code_fences("```json\n{ \"a\": 1 }\n```") == '{ "a": 1 }'
    assert strip_code_fences("```\nplain text\n```") == "plain text"
    assert strip_code_fences("no fences here") == "no fences here"
    assert strip_code_fences(None) == ""

def test_ensure_html_paragraphs():
    # plain text
    assert ensure_html_paragraphs("line 1\n\nline 2") == "<p>line 1</p><p>line 2</p>"
    
    # already has HTML
    assert ensure_html_paragraphs("<p>line 1</p>") == "<p>line 1</p>"
    
    # single line
    assert ensure_html_paragraphs("single line") == "<p>single line</p>"
    
    # escaping
    assert ensure_html_paragraphs("x < y") == "<p>x &lt; y</p>"
    
    # empty or None
    assert ensure_html_paragraphs("") == ""
    assert ensure_html_paragraphs(None) == ""

def test_canonical_document_hash():
    doc1 = PassageExamDocument(
        title="Exam 1",
        description="desc",
        groups=[
            PassageGroup(
                order=1,
                passage="Passage text",
                questions=[
                    PassageQuestion(
                        order=1,
                        question="Q1",
                        choices=[
                            QuestionChoice(content="A", is_correct=True),
                            QuestionChoice(content="B", is_correct=False),
                            QuestionChoice(content="C", is_correct=False),
                            QuestionChoice(content="D", is_correct=False),
                        ]
                    )
                ]
            )
        ]
    )
    
    doc2 = PassageExamDocument(
        title="Exam 1",
        description="desc",
        groups=[
            PassageGroup(
                order=1,
                passage="Passage text",
                questions=[
                    PassageQuestion(
                        order=1,
                        question="Q1",
                        choices=[
                            QuestionChoice(content="A", is_correct=True),
                            QuestionChoice(content="B", is_correct=False),
                            QuestionChoice(content="C", is_correct=False),
                            QuestionChoice(content="D", is_correct=False),
                        ]
                    )
                ]
            )
        ]
    )
    
    # The hash should be identical for identical documents
    hash1 = canonical_document_hash(doc1)
    hash2 = canonical_document_hash(doc2)
    assert hash1 == hash2
    assert isinstance(hash1, str)
    assert len(hash1) == 64  # sha256 hex length

def test_source_hash_marker():
    assert source_hash_marker("abcdef") == "[source_hash:abcdef]"

def test_append_hash_marker():
    marker = "[source_hash:abcdef]"
    assert append_hash_marker("", "abcdef") == marker
    assert append_hash_marker("some description", "abcdef") == f"some description\n\n{marker}"
    assert append_hash_marker(f"desc with {marker}", "abcdef") == f"desc with {marker}"

def test_deterministic_material_id():
    mat_id = deterministic_material_id("abcdef")
    # Must be valid UUID
    parsed_uuid = uuid.UUID(mat_id)
    assert parsed_uuid.version == 5

def test_load_json_document():
    raw_json = "```json\n{\"key\": \"value\"}\n```"
    parsed = load_json_document(raw_json)
    assert parsed == {"key": "value"}

def test_get_default_created_by_from_env(monkeypatch):
    monkeypatch.setenv("PASSAGE_EXAM_CREATED_BY", "env-test-id")
    assert get_default_created_by() == "env-test-id"

def test_get_default_created_by_fallback(monkeypatch):
    monkeypatch.delenv("PASSAGE_EXAM_CREATED_BY", raising=False)
    assert get_default_created_by() == "system"
