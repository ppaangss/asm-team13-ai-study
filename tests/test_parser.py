from backend.parser import parse_sections

SAMPLE_TXT = """[13조] 프로젝트 기획서
1. 문제 정의 및 프로젝트 개요

프로젝트 한 줄 정의
AI 심사위원 챗봇

2. 사용자 및 Agent 설계

타깃 사용자 페르소나
SW마에스트로 연수생

3. 핵심 기능 및 사용자 흐름

주요 사용자 시나리오
기획서 업로드 후 압박 질문 수신

4. 기술 구현 설계

기술 스택
Python, LangGraph

5. 성과 평가 및 실행 계획

성공 지표
유효 질문 5개 이상
"""

def test_parse_returns_dict():
    result = parse_sections(SAMPLE_TXT)
    assert isinstance(result, dict)

def test_parse_extracts_five_sections():
    result = parse_sections(SAMPLE_TXT)
    assert len(result) == 5

def test_parse_section_keys():
    result = parse_sections(SAMPLE_TXT)
    assert "1. 문제 정의 및 프로젝트 개요" in result
    assert "2. 사용자 및 Agent 설계" in result
    assert "3. 핵심 기능 및 사용자 흐름" in result
    assert "4. 기술 구현 설계" in result
    assert "5. 성과 평가 및 실행 계획" in result

def test_parse_section_content_not_empty():
    result = parse_sections(SAMPLE_TXT)
    for key, value in result.items():
        assert len(value.strip()) > 0, f"섹션 '{key}' 내용이 비어 있음"

def test_parse_empty_string():
    result = parse_sections("")
    assert result == {}

def test_parse_no_numbered_sections():
    result = parse_sections("섹션 구분 없는 텍스트입니다.")
    assert result == {"전체": "섹션 구분 없는 텍스트입니다."}
