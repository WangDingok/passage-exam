import hashlib
import html
import json
import os
import re
import uuid
from typing import Any

from .contracts import PassageExamDocument

WHITESPACE_RE = re.compile(r"\s+")
HTML_TAG_RE = re.compile(r"<[a-zA-Z][^>]*>")


def collapse_whitespace(value: str) -> str:
    return WHITESPACE_RE.sub(" ", value or "").strip()


def strip_code_fences(value: str) -> str:
    text = (value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    return text


def ensure_html_paragraphs(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if HTML_TAG_RE.search(text):
        return text

    paragraphs = [
        collapse_whitespace(part) for part in re.split(r"\n\s*\n", text)
        if collapse_whitespace(part)
    ]
    if not paragraphs:
        paragraphs = [collapse_whitespace(text)]
    return "".join(f"<p>{html.escape(paragraph)}</p>"
                   for paragraph in paragraphs if paragraph)


def canonical_document_hash(document: PassageExamDocument) -> str:
    sorted_document = document.sorted_copy()
    if hasattr(sorted_document, "model_dump"):
        dumped = sorted_document.model_dump()
    else:
        dumped = sorted_document.dict()
    payload = json.dumps(dumped,
                         ensure_ascii=False,
                         sort_keys=True,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def source_hash_marker(source_hash: str) -> str:
    return f"[source_hash:{source_hash}]"


def append_hash_marker(description: str, source_hash: str) -> str:
    marker = source_hash_marker(source_hash)
    base = (description or "").strip()
    if not base:
        return marker
    if marker in base:
        return base
    return f"{base}\n\n{marker}"


def deterministic_material_id(source_hash: str) -> str:
    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"passage-exam:material:{source_hash}"))


def load_json_document(value: str) -> Any:
    return json.loads(strip_code_fences(value))


def get_default_created_by() -> str:
    return os.getenv("PASSAGE_EXAM_CREATED_BY", "system")
