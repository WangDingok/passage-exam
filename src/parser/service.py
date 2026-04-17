import re
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Iterable, List
from xml.etree import ElementTree

from loguru import logger
from pydantic import BaseModel

from ..utils import collapse_whitespace

SUPPORTED_EXTENSIONS = {".txt", ".doc", ".docx"}
TEXT_FRAGMENT_RE = re.compile(r"[\w\d][^\r\n\t]{3,}")


class ParsedSourceDocument(BaseModel):
    path: str
    title: str
    text: str


def discover_source_files(path: Path) -> List[Path]:
    if path.is_file():
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"unsupported file extension: {path.suffix}")
        return [path]

    if not path.is_dir():
        raise ValueError(f"input path does not exist: {path}")

    files = sorted(candidate for candidate in path.rglob("*")
                   if candidate.is_file()
                   and candidate.suffix.lower() in SUPPORTED_EXTENSIONS)
    if not files:
        raise ValueError(f"no supported source files found in: {path}")

    logger.info("Discovered {} supported source file(s) in {}", len(files),
                path)
    return files


def parse_source_file(path: Path) -> ParsedSourceDocument:
    logger.info("Parsing source file: {}", path)
    return parse_source_bytes(path.name, path.read_bytes(), path=str(path))


def parse_source_bytes(filename: str,
                       data: bytes,
                       *,
                       path: str = "<upload>") -> ParsedSourceDocument:
    extension = Path(filename).suffix.lower()
    text = _extract_text_by_extension(extension, data, path)
    normalized_text = _normalize_extracted_text(text)
    if not normalized_text:
        raise ValueError(f"no readable text extracted from: {path}")

    logger.info("Successfully extracted {} characters from {}",
                len(normalized_text), filename)

    return ParsedSourceDocument(
        path=path,
        title=Path(filename).stem.replace("_", " ").strip()
        or Path(filename).stem,
        text=normalized_text,
    )


def _extract_text_by_extension(extension: str, data: bytes,
                               origin: str) -> str:
    if extension == ".txt":
        return _extract_txt(data)
    if extension == ".docx":
        return _extract_docx(data, origin)
    if extension == ".doc":
        return _extract_doc(data, origin)
    raise ValueError(f"unsupported file extension: {extension}")


def _extract_txt(data: bytes) -> str:
    return data.decode("utf-8", errors="ignore")


def _extract_docx(data: bytes, origin: str) -> str:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            document_xml = archive.read("word/document.xml")
    except KeyError as exc:
        raise ValueError(f"missing word/document.xml in {origin}") from exc

    root = ElementTree.fromstring(document_xml)
    paragraphs = []
    for paragraph in root.iter():
        if not paragraph.tag.endswith("}p"):
            continue
        text_parts = []
        for node in paragraph.iter():
            if node.tag.endswith("}t") and node.text:
                text_parts.append(node.text)
        paragraph_text = collapse_whitespace("".join(text_parts))
        if paragraph_text:
            paragraphs.append(paragraph_text)
    return "\n\n".join(paragraphs)


def _extract_doc(data: bytes, origin: str) -> str:
    fragments = []

    for decoded in (
            data.decode("utf-16le", errors="ignore"),
            data.decode("utf-8", errors="ignore"),
            data.decode("latin-1", errors="ignore"),
    ):
        fragments.extend(_extract_text_fragments(decoded))

    deduped = _dedupe_in_order(fragment for fragment in fragments if fragment)
    text = "\n".join(deduped)
    if not text:
        logger.warning(
            "Best-effort .doc parser could not extract rich text from {}",
            origin)
    return text


def _extract_text_fragments(value: str) -> List[str]:
    cleaned = value.replace("\x00", "\n")
    lines = []
    for raw_line in re.split(r"[\r\n]+", cleaned):
        line = collapse_whitespace(raw_line)
        if not line:
            continue
        if sum(char.isalnum() for char in line) < 4:
            continue
        if not TEXT_FRAGMENT_RE.search(line):
            continue
        lines.append(line)
    return lines


def _normalize_extracted_text(value: str) -> str:
    parts = [
        collapse_whitespace(part) for part in re.split(r"\n{2,}", value or "")
    ]
    filtered = [part for part in parts if part]
    return "\n\n".join(filtered)


def _dedupe_in_order(values: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
