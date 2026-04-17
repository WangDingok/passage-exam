import argparse
import asyncio
import json
from pathlib import Path
from typing import Iterable, Optional, Sequence

from loguru import logger

from .contracts import PassageExamDocument
from .generator import PassageExamGenerator
from .generator.service import dump_document_json
from .parser import discover_source_files, parse_source_file
from .uploader import PassageExamUploader
from .utils import get_default_created_by

DEFAULT_CREATED_BY = get_default_created_by()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Passage exam generator and uploader")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser(
        "generate", help="Generate normalized exam JSON from source files")
    _add_source_arguments(generate_parser)
    generate_parser.add_argument(
        "--title", help="Override generated exam title for single-file input")
    generate_parser.add_argument("--description",
                                 default="",
                                 help="Optional exam description")
    generate_parser.add_argument("--questions-per-group",
                                 type=int,
                                 default=None)
    generate_parser.add_argument(
        "--output-dir", help="Directory to write normalized JSON files")

    upload_parser = subparsers.add_parser(
        "upload", help="Upload normalized exam JSON to Hasura")
    upload_parser.add_argument("--input-json",
                               required=True,
                               help="Path to normalized exam JSON")
    upload_parser.add_argument(
        "--created-by",
        default=DEFAULT_CREATED_BY,
        help=f"User id stored in created_by (default: {DEFAULT_CREATED_BY})",
    )
    upload_parser.add_argument("--idempotency",
                               choices=["off", "skip", "fail"],
                               default="skip")

    run_parser = subparsers.add_parser(
        "run", help="Generate and upload exam(s) from source files")
    _add_source_arguments(run_parser)
    run_parser.add_argument(
        "--title", help="Override generated exam title for single-file input")
    run_parser.add_argument("--description",
                            default="",
                            help="Optional exam description")
    run_parser.add_argument("--questions-per-group", type=int, default=None)
    run_parser.add_argument("--output-dir",
                            help="Directory to write normalized JSON files")
    run_parser.add_argument(
        "--created-by",
        default=DEFAULT_CREATED_BY,
        help=f"User id stored in created_by (default: {DEFAULT_CREATED_BY})",
    )
    run_parser.add_argument("--idempotency",
                            choices=["off", "skip", "fail"],
                            default="skip")

    serve_parser = subparsers.add_parser(
        "serve", help="Run the passage exam workflow API")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--reload", action="store_true")

    return parser


def _add_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input",
                        required=True,
                        help="Path to a txt/doc/docx file or directory")


async def handle_generate(args) -> None:
    generator = PassageExamGenerator()
    sources = discover_source_files(Path(args.input))
    output_dir = _prepare_output_dir(args.output_dir)

    for source_path in sources:
        source = parse_source_file(source_path)
        document = await generator.generate(
            source=source,
            title=args.title if len(sources) == 1 else source.title,
            description=args.description,
            questions_per_group=args.questions_per_group,
        )
        _write_or_print_document(document, output_dir)


async def handle_upload(args) -> None:
    payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    document = PassageExamDocument.model_validate(payload)
    uploader = PassageExamUploader()
    result = await uploader.upload(
        document,
        created_by=args.created_by,
        idempotency=args.idempotency,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


async def handle_run(args) -> None:
    generator = PassageExamGenerator()
    uploader = PassageExamUploader()
    sources = discover_source_files(Path(args.input))
    output_dir = _prepare_output_dir(args.output_dir)

    for source_path in sources:
        source = parse_source_file(source_path)
        document = await generator.generate(
            source=source,
            title=args.title if len(sources) == 1 else source.title,
            description=args.description,
            questions_per_group=args.questions_per_group,
        )
        _write_or_print_document(document, output_dir)
        result = await uploader.upload(
            document,
            created_by=args.created_by,
            idempotency=args.idempotency,
        )
        print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


def _prepare_output_dir(value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    path = Path(value)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_or_print_document(document: PassageExamDocument,
                             output_dir: Optional[Path]) -> None:
    content = dump_document_json(document)
    if not output_dir:
        print(content)
        return

    output_path = output_dir / f"{_safe_filename(document.title)}.json"
    output_path.write_text(content, encoding="utf-8")
    logger.info("Wrote normalized exam JSON to {}", output_path)


def _safe_filename(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in ("-", "_") else "_"
                      for char in value.strip())
    return cleaned or "passage_exam"


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "generate":
        asyncio.run(handle_generate(args))
    elif args.command == "upload":
        asyncio.run(handle_upload(args))
    elif args.command == "run":
        asyncio.run(handle_run(args))
    elif args.command == "serve":
        import uvicorn

        uvicorn.run("src.api.app:app",
                    host=args.host,
                    port=args.port,
                    reload=args.reload)
    else:
        parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
