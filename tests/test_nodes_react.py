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
    "followup_count": 0,
    "current_persona": "",
    "needs_followup": False,
    "debug_log": [],
    "pending_debug": {},
    "verification_results": [],
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


def test_orchestrator_review_returns_sufficient_when_findings_complete():
    """3개 페르소나 findings가 모두 있으면 is_sufficient=True를 반환하는지 확인."""
    from backend.schemas import OrchestratorReview

    state = {
        **SAMPLE_STATE,
        "round": 0,
        "persona_findings": [
            {"persona": "investor", "findings": "수익화 시점 불명확.", "round": 0},
            {"persona": "cto", "findings": "6개월 MVP 비현실적.", "round": 0},
            {"persona": "mentor", "findings": "MVP 범위 과대.", "round": 0},
        ],
        "review_count": 0,
    }

    mock_review = OrchestratorReview(is_sufficient=True, follow_up_requests={})

    async def run():
        with patch("backend.nodes._bound_review") as mock_llm:
            mock_llm.ainvoke = AsyncMock(return_value=mock_review)
            from backend.nodes import orchestrator_review_node
            result = await orchestrator_review_node(state)

        assert result["review_count"] == 1
        assert result["orchestrator_request"] == {}

    import asyncio
    asyncio.run(run())


def test_orchestrator_review_returns_followup_when_insufficient():
    """findings가 부족하면 follow_up_requests를 반환하는지 확인."""
    from backend.schemas import OrchestratorReview

    state = {
        **SAMPLE_STATE,
        "round": 0,
        "persona_findings": [
            {"persona": "investor", "findings": "수익모델 분석 필요.", "round": 0},
        ],
        "review_count": 0,
    }

    mock_review = OrchestratorReview(
        is_sufficient=False,
        follow_up_requests={"investor": "Unit Economics 수치 포함해서 재분석해줘"},
    )

    async def run():
        with patch("backend.nodes._bound_review") as mock_llm:
            mock_llm.ainvoke = AsyncMock(return_value=mock_review)
            from backend.nodes import orchestrator_review_node
            result = await orchestrator_review_node(state)

        assert result["review_count"] == 1
        assert "investor" in result["orchestrator_request"]

    import asyncio
    asyncio.run(run())


def test_run_persona_uses_findings_in_prompt():
    """_run_persona가 persona_findings를 질문 생성에 활용하는지 확인."""
    state = {
        **SAMPLE_STATE,
        "round": 0,
        "orchestrator_plan": [
            {"persona": "investor", "section": "수익모델", "focus": "수익화 시점 불명확"},
        ],
        "persona_findings": [
            {"persona": "investor", "findings": "수익화 시점이 불명확하고 Unit Economics 근거 없음.", "round": 0},
        ],
    }

    async def run():
        captured = {}

        with patch("backend.nodes.llm") as mock_llm, \
             patch("backend.nodes._bound_llm") as mock_bound:

            async def fake_astream(messages, *args, **kwargs):
                captured["prompt"] = messages[-1].content
                mock_msg = MagicMock()
                mock_msg.content = "6개월 후 Unit Economics는 어떻게 됩니까?"
                yield mock_msg

            mock_llm.astream = fake_astream
            mock_bound.ainvoke = AsyncMock(return_value=MagicMock(tool_calls=[]))

            from backend.nodes import _run_persona
            result = await _run_persona("investor", state)

        assert "수익화 시점이 불명확" in captured["prompt"]
        assert result["persona_outputs"][0]["question"] != ""

    import asyncio
    asyncio.run(run())


def test_should_continue_react_returns_continue_when_insufficient_and_under_limit():
    from backend.graph import _should_continue_react
    state = {
        **SAMPLE_STATE,
        "review_count": 1,
        "orchestrator_request": {"investor": "더 분석해줘"},
    }
    result = _should_continue_react(state)
    assert result == "continue"


def test_should_continue_react_returns_done_when_max_iterations():
    from backend.graph import _should_continue_react
    state = {
        **SAMPLE_STATE,
        "review_count": 2,
        "orchestrator_request": {"investor": "더 분석해줘"},
    }
    result = _should_continue_react(state)
    assert result == "done"


def test_should_continue_react_returns_done_when_sufficient():
    from backend.graph import _should_continue_react
    state = {
        **SAMPLE_STATE,
        "review_count": 1,
        "orchestrator_request": {},
    }
    result = _should_continue_react(state)
    assert result == "done"


def test_human_node_does_not_increment_round():
    """human_node가 round를 증가시키지 않는지 확인."""
    from unittest.mock import patch
    with patch("backend.nodes.interrupt", return_value="테스트 답변"):
        from backend.nodes import human_node
        state = {**SAMPLE_STATE, "round": 2}
        result = human_node(state)
    assert "round" not in result
    assert result["messages"][0]["content"] == "테스트 답변"


def test_followup_judge_node_increments_followup_count_when_needed():
    """needs_followup=True 시 followup_count가 증가하는지 확인."""
    from backend.schemas import FollowupJudge

    state = {
        **SAMPLE_STATE,
        "messages": [
            {"role": "assistant", "name": "investor", "content": "수익 모델이 있나요?"},
            {"role": "user", "content": "나중에 생각해볼게요."},
        ],
        "followup_count": 0,
    }
    mock_judge = FollowupJudge(needs_followup=True, score=18, reason="답변이 너무 추상적임")

    async def run():
        with patch("backend.nodes._bound_followup") as mock_llm:
            mock_llm.ainvoke = AsyncMock(return_value=mock_judge)
            from backend.nodes import followup_judge_node
            result = await followup_judge_node(state)
        assert result["needs_followup"] is True
        assert result["followup_count"] == 1
        assert "round" not in result

    import asyncio
    asyncio.run(run())


def test_followup_judge_node_increments_round_when_sufficient():
    """needs_followup=False 시 round가 증가하고 followup_count가 초기화되는지 확인."""
    from backend.schemas import FollowupJudge

    state = {
        **SAMPLE_STATE,
        "round": 1,
        "messages": [
            {"role": "assistant", "name": "cto", "content": "구현 가능한가요?"},
            {"role": "user", "content": "Whisper STT 기준 300ms 이내 처리 가능합니다."},
        ],
        "followup_count": 1,
    }
    mock_judge = FollowupJudge(needs_followup=False, score=72, reason="구체적 수치 제시됨")

    async def run():
        with patch("backend.nodes._bound_followup") as mock_llm:
            mock_llm.ainvoke = AsyncMock(return_value=mock_judge)
            from backend.nodes import followup_judge_node
            result = await followup_judge_node(state)
        assert result["needs_followup"] is False
        assert result["round"] == 2
        assert result["followup_count"] == 0

    import asyncio
    asyncio.run(run())


def test_followup_judge_node_evaluates_short_answer_with_llm():
    """짧은 답변("네")도 LLM으로 맥락 평가하는지 확인. 이전의 15자 가드 제거됨."""
    from backend.schemas import FollowupJudge

    state = {
        **SAMPLE_STATE,
        "round": 0,
        "messages": [
            {"role": "assistant", "name": "cto", "content": "구현 가능성을 확인하셨나요?"},
            {"role": "user", "content": "네"},  # 짧지만 맥락상 유효한 답변
        ],
        "followup_count": 1,
    }
    # "네"를 충분한 답변으로 판단 (score=80 → threshold=15 초과 → 다음 라운드)
    mock_judge = FollowupJudge(needs_followup=False, score=80, reason="질문에 대한 긍정 답변으로 충분")

    async def run():
        with patch("backend.nodes._bound_followup") as mock_llm:
            mock_llm.ainvoke = AsyncMock(return_value=mock_judge)
            from backend.nodes import followup_judge_node
            result = await followup_judge_node(state)
        mock_llm.ainvoke.assert_called_once()  # LLM 호출 확인
        assert result["needs_followup"] is False
        assert result["round"] == 1
        assert result["followup_count"] == 0

    import asyncio
    asyncio.run(run())


def test_followup_judge_node_no_followup_when_max_reached():
    """followup_count >= MAX_FOLLOWUPS 이면 needs_followup=True여도 종료되는지 확인."""
    from backend.schemas import FollowupJudge

    state = {
        **SAMPLE_STATE,
        "round": 0,
        "messages": [
            {"role": "assistant", "name": "mentor", "content": "MVP 범위가 너무 크지 않나요?"},
            {"role": "user", "content": "그냥 다 넣겠습니다."},
        ],
        "followup_count": 3,  # MAX_FOLLOWUPS 도달
    }
    mock_judge = FollowupJudge(needs_followup=True, score=10, reason="여전히 불충분")

    async def run():
        with patch("backend.nodes._bound_followup") as mock_llm:
            mock_llm.ainvoke = AsyncMock(return_value=mock_judge)
            from backend.nodes import followup_judge_node
            result = await followup_judge_node(state)
        # MAX 도달 → needs를 False 처리
        assert result["needs_followup"] is False
        assert result["round"] == 1
        assert result["followup_count"] == 0

    import asyncio
    asyncio.run(run())


def test_route_after_followup_returns_same_persona_when_needs_followup():
    """needs_followup=True 시 current_persona로 라우팅되는지 확인."""
    from backend.graph import _route_after_followup
    state = {
        **SAMPLE_STATE,
        "needs_followup": True,
        "current_persona": "cto",
        "round": 0,
        "orchestrator_plan": [{"persona": "cto", "section": "기술", "focus": "구현"}],
    }
    assert _route_after_followup(state) == "cto"


def test_route_after_followup_goes_to_reporter_when_rounds_exhausted():
    """모든 라운드 완료 시 reporter로 라우팅되는지 확인."""
    from backend.graph import _route_after_followup
    state = {
        **SAMPLE_STATE,
        "needs_followup": False,
        "round": 3,
        "orchestrator_plan": [
            {"persona": "investor", "section": "s1", "focus": "f1"},
            {"persona": "cto", "section": "s2", "focus": "f2"},
            {"persona": "mentor", "section": "s3", "focus": "f3"},
        ],
    }
    assert _route_after_followup(state) == "reporter"


def test_run_analyze_includes_persona_rag_in_prompt():
    """_run_analyze가 retrieve_persona 결과를 프롬프트에 포함하는지 확인."""
    state = {
        **SAMPLE_STATE,
        "sections_by_persona": {
            "investor": {"5. 수익 모델": "초기 무료, 추후 프리미엄"},
        },
        "orchestrator_request": {},
    }

    async def run():
        captured = {}

        with patch("backend.nodes.llm") as mock_llm, \
             patch("backend.nodes.retrieve_persona", return_value="=== 전문가 참고 자료 ===\n[unit_economics_guide — LTV]\nLTV는 고객 생애 가치다.") as mock_retrieve:

            async def fake_astream(messages, *args, **kwargs):
                captured["prompt"] = messages[-1].content
                mock_msg = MagicMock()
                mock_msg.content = "Unit Economics가 없습니다."
                yield mock_msg

            mock_llm.astream = fake_astream
            from backend.nodes import investor_analyze_node
            await investor_analyze_node(state)

        assert "전문가 참고 자료" in captured["prompt"]

    import asyncio
    asyncio.run(run())
