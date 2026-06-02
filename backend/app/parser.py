import re

# 헤딩 텍스트 → 표준 섹션 키. 위에서부터 먼저 매칭되는 키를 사용한다.
SECTION_KEYWORDS = {
    "문제정의": ["문제", "정의", "배경", "개요"],
    "대상사용자": ["대상", "사용자", "타깃", "페르소나", "고객"],
    "핵심기능": ["기능", "핵심", "시나리오", "흐름"],
    "기술스택": ["기술", "스택", "아키텍처", "구현"],
    "MVP범위": ["mvp", "범위", "로드맵", "일정"],
    "차별성": ["차별", "경쟁", "시장", "사업", "수익"],
}

_HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.*\S)\s*$")


def _match_section(heading: str) -> str:
    h = heading.lower()
    for key, kws in SECTION_KEYWORDS.items():
        if any(kw in h for kw in kws):
            return key
    return "기타"


def parse_proposal(text: str) -> dict[str, str]:
    """마크다운 헤딩(#~######) 기준으로 본문을 표준 섹션으로 분할한다.

    헤딩이 없으면 빈 dict를 반환한다(호출 측에서 '분석 불가' 처리).
    """
    buckets: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            current = _match_section(m.group(1))
            buckets.setdefault(current, [])
            continue
        if current is not None and line.strip():
            buckets[current].append(line.rstrip())
    return {k: "\n".join(v).strip() for k, v in buckets.items() if "\n".join(v).strip()}
