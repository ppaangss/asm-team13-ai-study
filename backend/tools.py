from __future__ import annotations

from langchain_core.tools import tool

from backend.config import TAVILY_API_KEY


@tool
def web_search(query: str) -> str:
    """인터넷에서 최신 정보를 검색합니다. 시장 규모, 경쟁사 현황, 기술 트렌드, 유사 서비스 사례 검색에 사용하세요."""
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=TAVILY_API_KEY)
        results = client.search(query=query, max_results=3)
        if not results.get("results"):
            return "검색 결과 없음"
        lines = []
        for r in results["results"]:
            title = r.get("title", "")
            content = r.get("content", "")[:300]
            lines.append(f"[{title}] {content}")
        return "\n\n".join(lines)
    except Exception:
        return "웹 검색 실패"
