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


def test_investor_analyze_node_uses_assigned_sections():
    """investor_analyze_node가 배분된 섹션만 사용하고 findings를 반환하는지 확인."""
    state = {
        **SAMPLE_STATE,
        "sections_by_persona": {
            "investor": {"5. 수익 모델": "초기 무료, 추후 프리미엄"},
        },
        "orchestrator_request": {},
    }

    async def run():
        with patch("backend.nodes.llm") as mock_llm:
            mock_msg = MagicMock()
            mock_msg.content = "수익화 시점이 불명확하고 전환율 근거가 없다."
            mock_chunks = [mock_msg]

            async def fake_astream(*args, **kwargs):
                for c in mock_chunks:
                    yield c

            mock_llm.astream = fake_astream
            from backend.nodes import investor_analyze_node
            result = await investor_analyze_node(state)

        assert "persona_findings" in result
        assert len(result["persona_findings"]) == 1
        finding = result["persona_findings"][0]
        assert finding["persona"] == "investor"
        assert len(finding["findings"]) > 0
        assert finding["round"] == 0

    import asyncio
    asyncio.run(run())


def test_analyze_node_includes_followup_request_when_present():
    """orchestrator_request가 있으면 프롬프트에 포함되는지 확인 (findings에 반영)."""
    state = {
        **SAMPLE_STATE,
        "sections_by_persona": {
            "investor": {"5. 수익 모델": "초기 무료"},
        },
        "orchestrator_request": {"investor": "Unit Economics를 구체적으로 분석해줘"},
    }

    async def run():
        with patch("backend.nodes.llm") as mock_llm:
            captured = {}

            async def fake_astream(messages, *args, **kwargs):
                captured["prompt"] = messages[-1].content
                mock_msg = MagicMock()
                mock_msg.content = "Unit Economics 근거 없음."
                yield mock_msg

            mock_llm.astream = fake_astream
            from backend.nodes import investor_analyze_node
            await investor_analyze_node(state)

        assert "Unit Economics" in captured["prompt"]

    import asyncio
    asyncio.run(run())
