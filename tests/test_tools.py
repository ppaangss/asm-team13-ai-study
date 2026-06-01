import pytest
from unittest.mock import patch, MagicMock


def test_web_search_is_langchain_tool():
    from backend.tools import web_search
    # LangChain @tool은 .name, .description, .invoke 속성을 가진다
    assert hasattr(web_search, "name")
    assert hasattr(web_search, "description")
    assert hasattr(web_search, "invoke")
    assert web_search.name == "web_search"


def test_web_search_returns_string_on_success():
    fake_results = {
        "results": [
            {"title": "AI 시장 2024", "content": "AI 시장은 연 35% 성장 중입니다. 주요 플레이어는..."},
            {"title": "LLM 경쟁 현황", "content": "GPT-4, Claude 3, Gemini 등이 경쟁 중이며..."},
        ]
    }
    with patch("tavily.TavilyClient") as MockClient:
        instance = MockClient.return_value
        instance.search.return_value = fake_results
        from backend.tools import web_search
        result = web_search.invoke({"query": "AI 교육 시장 규모"})
    assert isinstance(result, str)
    assert "AI 시장 2024" in result
    assert "LLM 경쟁 현황" in result


def test_web_search_returns_fallback_when_no_results():
    with patch("tavily.TavilyClient") as MockClient:
        instance = MockClient.return_value
        instance.search.return_value = {"results": []}
        from backend.tools import web_search
        result = web_search.invoke({"query": "존재하지않는검색어xyz"})
    assert result == "검색 결과 없음"


def test_web_search_truncates_long_content():
    long_content = "A" * 1000
    fake_results = {"results": [{"title": "긴 문서", "content": long_content}]}
    with patch("tavily.TavilyClient") as MockClient:
        instance = MockClient.return_value
        instance.search.return_value = fake_results
        from backend.tools import web_search
        result = web_search.invoke({"query": "테스트"})
    # 콘텐츠는 300자로 잘려야 한다
    assert len(result) <= 400  # "[긴 문서] " + 300자 + 여유


def test_web_search_handles_api_error():
    with patch("tavily.TavilyClient") as MockClient:
        instance = MockClient.return_value
        instance.search.side_effect = Exception("API Error")
        from backend.tools import web_search
        result = web_search.invoke({"query": "test"})
    assert result == "웹 검색 실패"
