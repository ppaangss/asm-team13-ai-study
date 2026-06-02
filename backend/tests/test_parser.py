from app.parser import parse_proposal


def test_parses_headings_into_canonical_sections():
    text = """# 문제 정의
사용자가 발표 전 약점을 모른다.
## 대상 사용자
SW마에스트로 연수생
## 핵심 기능
페르소나 압박 질문 생성
"""
    sections = parse_proposal(text)
    assert sections["문제정의"].startswith("사용자가 발표")
    assert sections["대상사용자"] == "SW마에스트로 연수생"
    assert "압박 질문" in sections["핵심기능"]


def test_missing_section_is_absent():
    sections = parse_proposal("# 문제 정의\n내용")
    assert "기술스택" not in sections


def test_no_headings_returns_empty():
    assert parse_proposal("헤딩 없는 자유 텍스트") == {}
