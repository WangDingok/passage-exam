import unittest
import uuid
import zipfile
import shutil
from pathlib import Path

from src.parser import discover_source_files, parse_source_bytes, parse_source_file


class PassageExamParserTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path("tests/.tmp") / str(uuid.uuid4())
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_discover_source_files_from_directory(self):
        root = self.tmp_dir
        (root / "sample.txt").write_text("Hello", encoding="utf-8")
        (root / "ignored.pdf").write_text("Nope", encoding="utf-8")

        discovered = discover_source_files(root)

        self.assertEqual([root / "sample.txt"], discovered)

    def test_parse_txt_file(self):
        path = self.tmp_dir / "reading_sample.txt"
        path.write_text("Passage one.\n\nQuestion style.", encoding="utf-8")

        parsed = parse_source_file(path)

        self.assertEqual("reading sample", parsed.title)
        self.assertIn("Passage one.", parsed.text)
        self.assertIn("Question style.", parsed.text)

    def test_parse_docx_file(self):
        path = self.tmp_dir / "reading.docx"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "word/document.xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
                <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                  <w:body>
                    <w:p><w:r><w:t>Passage paragraph.</w:t></w:r></w:p>
                    <w:p><w:r><w:t>Question example.</w:t></w:r></w:p>
                  </w:body>
                </w:document>""",
            )

        parsed = parse_source_file(path)

        self.assertIn("Passage paragraph.", parsed.text)
        self.assertIn("Question example.", parsed.text)

    def test_parse_doc_file_best_effort(self):
        path = self.tmp_dir / "reading.doc"
        content = "Doan van mau cho de doc hieu".encode("utf-16le")
        path.write_bytes(content)

        parsed = parse_source_file(path)

        self.assertIn("Doan van mau", parsed.text)

    def test_parse_upload_bytes(self):
        parsed = parse_source_bytes(
            "upload_sample.txt",
            b"Shared passage.\n\nQuestion stem.",
        )

        self.assertEqual("upload sample", parsed.title)
        self.assertEqual("<upload>", parsed.path)
        self.assertIn("Shared passage.", parsed.text)


if __name__ == "__main__":
    unittest.main()
