import io
import pytest
from backend.file_reader import extract_text, read_file_text, SUPPORTED_EXTENSIONS
from pathlib import Path
import tempfile


def test_supported_extensions():
    assert ".txt" in SUPPORTED_EXTENSIONS
    assert ".md" in SUPPORTED_EXTENSIONS
    assert ".pdf" in SUPPORTED_EXTENSIONS
    assert ".docx" in SUPPORTED_EXTENSIONS


def test_extract_txt():
    result = extract_text("안녕하세요\n1. 섹션".encode("utf-8"), "plan.txt")
    assert "안녕하세요" in result
    assert "1. 섹션" in result


def test_extract_md_strips_headers():
    md = "## 1. 서비스 개요\n내용입니다\n## 2. 문제 정의\n문제"
    result = extract_text(md.encode("utf-8"), "plan.md")
    assert "##" not in result
    assert "1. 서비스 개요" in result
    assert "2. 문제 정의" in result


def test_extract_md_strips_bold():
    md = "**중요한 내용**이 있습니다"
    result = extract_text(md.encode("utf-8"), "plan.md")
    assert "**" not in result
    assert "중요한 내용" in result


def test_extract_pdf(monkeypatch):
    class _FakePage:
        def extract_text(self):
            return "PDF 페이지 내용"

    class _FakeReader:
        def __init__(self, stream):
            self.pages = [_FakePage(), _FakePage()]

    monkeypatch.setattr("backend.file_reader.PdfReader", _FakeReader, raising=False)
    import backend.file_reader as fr
    monkeypatch.setattr(fr, "_extract_pdf",
                        lambda content: "\n".join("PDF 페이지 내용" for _ in range(2)))

    result = extract_text(b"%PDF-fake", "plan.pdf")
    assert "PDF 페이지 내용" in result


def test_extract_docx(monkeypatch):
    import backend.file_reader as fr

    class _FakePara:
        def __init__(self, text, style_name="Normal"):
            self.text = text
            self.style = type("S", (), {"name": style_name})()

    class _FakeDoc:
        def __init__(self, stream):
            self.paragraphs = [
                _FakePara("1. 서비스 개요", "Heading 1"),
                _FakePara("이것은 서비스 설명입니다."),
                _FakePara(""),  # 빈 단락 — 무시되어야 함
                _FakePara("2. 문제 정의", "Heading 2"),
                _FakePara("해결하려는 문제입니다."),
            ]

    monkeypatch.setattr(fr, "_extract_docx",
                        lambda content: "\n".join(
                            p.text for p in _FakeDoc(None).paragraphs if p.text.strip()
                        ))
    result = extract_text(b"PK\x03\x04fake", "plan.docx")
    assert "1. 서비스 개요" in result
    assert "이것은 서비스 설명입니다." in result
    assert "2. 문제 정의" in result


def test_unsupported_extension_raises():
    with pytest.raises(ValueError, match="지원하지 않는 파일 형식"):
        extract_text(b"data", "plan.hwp")


def test_read_file_text_txt(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("1. 섹션\n내용", encoding="utf-8")
    result = read_file_text(f)
    assert "1. 섹션" in result


def test_read_file_text_md(tmp_path):
    f = tmp_path / "test.md"
    f.write_text("## 1. 섹션\n내용", encoding="utf-8")
    result = read_file_text(f)
    assert "##" not in result
    assert "1. 섹션" in result
