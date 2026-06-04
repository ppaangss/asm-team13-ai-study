import re


def parse_sections(text: str) -> dict[str, str]:
    """TXT 기획서를 번호 섹션 단위로 파싱한다."""
    if not text.strip():
        return {}

    pattern = re.compile(r"^(\d+\.\s+[^\n]+)", re.MULTILINE)
    matches = list(pattern.finditer(text))

    if not matches:
        return {"전체": text.strip()}

    sections = {}
    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        sections[title] = content

    return sections


def parse_markdown_sections(text: str) -> dict[str, str]:
    """마크다운 문서를 ## 헤더 단위로 파싱한다. 없으면 # 헤더로 폴백."""
    if not text.strip():
        return {}

    pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))

    if not matches:
        pattern = re.compile(r"^#\s+(.+)$", re.MULTILINE)
        matches = list(pattern.finditer(text))
        if not matches:
            return {"전체": text.strip()}

    sections = {}
    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if content:
            sections[title] = content

    return sections
