import pytest
from unittest.mock import AsyncMock, patch, MagicMock


SAMPLE_STATE = {
    "sections": {
        "1. 서비스 개요": "AI 영어 스피킹 코치 앱",
        "2. 문제 정의": "스피킹 연습 기회 부족",
        "3. 핵심 기능": "실시간 발음 교정, AI 대화",
        "4. 기술 구현": "Whisper STT, GPT-4, 6개월 MVP",
        "5. 수익 모델": "초기 무료, 추후 프리미엄",
        "6. 시장 분석": "MZ세대 자기계발 수요",
    },
    "messages": [],
    "round": 0,
    "persona_outputs": [],
    "final_report": "",
    "orchestrator_plan": [],
    "sections_by_persona": {},
    "persona_findings": [],
    "review_count": 0,
    "orchestrator_request": {},
}


def test_orchestrator_node_returns_sections_by_persona():
    """orchestrator_node가 sections_by_persona를 반환하는지 확인."""
    mock_plan = MagicMock()
    mock_plan.rounds = []
    mock_plan.sections_by_persona = {
        "investor": ["5. 수익 모델", "6. 시장 분석"],
        "cto": ["3. 핵심 기능", "4. 기술 구현"],
        "mentor": ["1. 서비스 개요", "2. 문제 정의"],
    }

    async def run():
        with patch("backend.nodes._bound_orchestrator") as mock_llm:
            mock_llm.ainvoke = AsyncMock(return_value=mock_plan)
            from backend.nodes import orchestrator_node
            result = await orchestrator_node(SAMPLE_STATE)
        assert "sections_by_persona" in result
        assert "investor" in result["sections_by_persona"]
        investor_sections = result["sections_by_persona"]["investor"]
        assert isinstance(investor_sections, dict)
        for title in investor_sections:
            assert title in SAMPLE_STATE["sections"]

    import asyncio
    asyncio.run(run())
