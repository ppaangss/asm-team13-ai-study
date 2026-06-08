"""
answer_fact_check_node 및 reporter 업데이트 단위 테스트
RED → GREEN → REFACTOR 사이클
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── 공통 픽스처 ──────────────────────────────────────────────────────────────

def _make_claim_result(claims: list[str]):
    mock = MagicMock()
    mock.claims = claims
    return mock


def _make_verify_result(items: list[dict]):
    mock = MagicMock()
    result_items = []
    for item in items:
        m = MagicMock()
        m.model_dump.return_value = item
        result_items.append(m)
    mock.items = result_items
    return mock


def _state(answer: str | None = None, fact_checks: list | None = None) -> dict:
    messages = [{"role": "assistant", "name": "investor", "content": "수익 모델이 있나요?"}]
    if answer is not None:
        messages.append({"role": "user", "content": answer})
    return {
        "sections": {"서비스 개요": "AI 기반 기획서 검증 서비스"},
        "messages": messages,
        "round": 1,
        "persona_outputs": [],
        "final_report": "",
        "orchestrator_plan": [],
        "sections_by_persona": {},
        "persona_findings": [],
        "review_count": 0,
        "orchestrator_request": {},
        "followup_count": 0,
        "current_persona": "investor",
        "needs_followup": False,
        "debug_log": [],
        "pending_debug": {},
        "verification_results": [],
        "answer_fact_checks": fact_checks or [],
    }


ANSWER_WITH_CLAIMS = "국내 AI 시장 규모는 5조원이고, 연평균 25% 성장 중입니다."
ANSWER_WITHOUT_CLAIMS = "저희는 좋은 서비스를 만들 자신이 있습니다."

SAMPLE_ITEM = {
    "claim": "국내 AI 시장 규모는 5조원",
    "status": "unconfirmed",
    "reason": "관련 데이터 불충분",
    "source": "검색 결과 없음",
}


# ── answer_fact_check_node ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_answer_fact_check_returns_items_for_verifiable_claims():
    """수치 주장이 있는 답변은 검증 결과를 answer_fact_checks에 담아 반환한다."""
    from backend.nodes import answer_fact_check_node
    with patch("backend.nodes._bound_claim_extractor") as mock_ext, \
         patch("backend.nodes.web_search") as mock_search, \
         patch("backend.nodes._bound_claim_verifier") as mock_verifier:
        mock_ext.ainvoke = AsyncMock(return_value=_make_claim_result(["AI 시장 5조원"]))
        mock_search.invoke = MagicMock(return_value="검색 결과")
        mock_verifier.ainvoke = AsyncMock(return_value=_make_verify_result([SAMPLE_ITEM]))

        result = await answer_fact_check_node(_state(ANSWER_WITH_CLAIMS))

    assert len(result["answer_fact_checks"]) == 1
    assert result["answer_fact_checks"][0]["claim"] == SAMPLE_ITEM["claim"]


@pytest.mark.asyncio
async def test_answer_fact_check_returns_empty_when_no_user_message():
    """사용자 메시지가 없으면 빈 리스트를 반환한다."""
    from backend.nodes import answer_fact_check_node
    result = await answer_fact_check_node(_state(answer=None))
    assert result["answer_fact_checks"] == []


@pytest.mark.asyncio
async def test_answer_fact_check_returns_empty_when_no_claims_extracted():
    """추출된 수치 주장이 없으면 웹 검색 없이 빈 리스트를 반환한다."""
    from backend.nodes import answer_fact_check_node
    with patch("backend.nodes._bound_claim_extractor") as mock_ext, \
         patch("backend.nodes.web_search") as mock_search:
        mock_ext.ainvoke = AsyncMock(return_value=_make_claim_result([]))

        result = await answer_fact_check_node(_state(ANSWER_WITHOUT_CLAIMS))

    assert result["answer_fact_checks"] == []
    mock_search.invoke.assert_not_called()


@pytest.mark.asyncio
async def test_answer_fact_check_limits_claims_to_3():
    """답변에서 주장이 5개 추출되어도 웹 검색은 최대 3번만 실행한다."""
    from backend.nodes import answer_fact_check_node
    five_claims = [f"주장 {i}" for i in range(5)]
    search_calls = []

    def counting_search(claim):
        search_calls.append(claim)
        return "검색 결과"

    with patch("backend.nodes._bound_claim_extractor") as mock_ext, \
         patch("backend.nodes.web_search") as mock_search, \
         patch("backend.nodes._bound_claim_verifier") as mock_verifier:
        mock_ext.ainvoke = AsyncMock(return_value=_make_claim_result(five_claims))
        mock_search.invoke = MagicMock(side_effect=counting_search)
        mock_verifier.ainvoke = AsyncMock(return_value=_make_verify_result([]))

        await answer_fact_check_node(_state(ANSWER_WITH_CLAIMS))

    assert len(search_calls) == 3


@pytest.mark.asyncio
async def test_answer_fact_check_handles_extractor_failure():
    """클레임 추출 LLM이 실패하면 예외를 전파하지 않고 빈 리스트를 반환한다."""
    from backend.nodes import answer_fact_check_node
    with patch("backend.nodes._bound_claim_extractor") as mock_ext:
        mock_ext.ainvoke = AsyncMock(side_effect=Exception("LLM 오류"))

        result = await answer_fact_check_node(_state(ANSWER_WITH_CLAIMS))

    assert result["answer_fact_checks"] == []


@pytest.mark.asyncio
async def test_answer_fact_check_handles_verifier_failure():
    """검증 LLM이 실패하면 예외를 전파하지 않고 빈 리스트를 반환한다."""
    from backend.nodes import answer_fact_check_node
    with patch("backend.nodes._bound_claim_extractor") as mock_ext, \
         patch("backend.nodes.web_search") as mock_search, \
         patch("backend.nodes._bound_claim_verifier") as mock_verifier:
        mock_ext.ainvoke = AsyncMock(return_value=_make_claim_result(["AI 시장 5조원"]))
        mock_search.invoke = MagicMock(return_value="검색 결과")
        mock_verifier.ainvoke = AsyncMock(side_effect=Exception("LLM 오류"))

        result = await answer_fact_check_node(_state(ANSWER_WITH_CLAIMS))

    assert result["answer_fact_checks"] == []


# ── reporter_node: answer_fact_checks 프롬프트 반영 ───────────────────────────

@pytest.mark.asyncio
async def test_reporter_prompt_includes_answer_fact_checks():
    """answer_fact_checks가 있으면 reporter_node 프롬프트에 claim이 포함된다."""
    from backend.nodes import reporter_node
    state = _state("답변", fact_checks=[SAMPLE_ITEM])

    captured: list = []
    mock_report = MagicMock()
    mock_report.summary = "요약"
    mock_report.overall_score = 70
    mock_report.weaknesses = []
    mock_report.closing = "마무리"

    async def capture_invoke(messages):
        captured.extend(messages)
        return mock_report

    with patch("backend.nodes._bound_reporter") as mock_reporter:
        mock_reporter.ainvoke = capture_invoke
        await reporter_node(state)

    full_prompt = " ".join(str(m.content) for m in captured)
    assert SAMPLE_ITEM["claim"] in full_prompt


@pytest.mark.asyncio
async def test_reporter_prompt_skips_fact_check_block_when_empty():
    """answer_fact_checks가 비어 있으면 reporter 프롬프트에 검증 섹션이 없다."""
    from backend.nodes import reporter_node
    state = _state("답변", fact_checks=[])

    captured: list = []
    mock_report = MagicMock()
    mock_report.summary = "요약"
    mock_report.overall_score = 70
    mock_report.weaknesses = []
    mock_report.closing = "마무리"

    async def capture_invoke(messages):
        captured.extend(messages)
        return mock_report

    with patch("backend.nodes._bound_reporter") as mock_reporter:
        mock_reporter.ainvoke = capture_invoke
        await reporter_node(state)

    full_prompt = " ".join(str(m.content) for m in captured)
    assert "답변 신뢰도 검증" not in full_prompt
