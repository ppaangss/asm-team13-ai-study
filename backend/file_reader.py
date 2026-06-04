from __future__ import annotations

import io
import re
from pathlib import Path

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


def extract_text(content: bytes, filename: str) -> str:
    """업로드된 파일 바이트에서 텍스트 추출. rag.py / main.py 공용."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".txt":
        return content.decode("utf-8")
    if suffix == ".md":
        return _process_md(content.decode("utf-8"))
    if suffix == ".pdf":
        return _extract_pdf(content)
    if suffix == ".docx":
        return _extract_docx(content)
    raise ValueError(f"지원하지 않는 파일 형식: {suffix}. 허용: txt, md, pdf, docx")


def read_file_text(path: Path) -> str:
    """디스크 파일에서 텍스트 추출 (rag.py build_index용)."""
    return extract_text(path.read_bytes(), path.name)


def _process_md(text: str) -> str:
    # ## 1. 섹션명 → 1. 섹션명 (숫자 섹션 헤더 보존)
    text = re.sub(r"^#{1,6}\s+(\d+\.)", r"\1", text, flags=re.MULTILINE)
    # ## 섹션명 → 섹션명 (숫자 없는 헤더 제거)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # **bold** / *italic* 마크다운 제거
    text = re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", text)
    return text


def _extract_pdf(content: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)


def _extract_docx(content: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(content))
    lines = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        # Heading 스타일이면 앞줄 구분을 위해 빈 줄 추가 (섹션 파서 인식률 향상)
        if para.style.name.startswith("Heading"):
            lines.append("")
        lines.append(text)
    return "\n".join(lines)
