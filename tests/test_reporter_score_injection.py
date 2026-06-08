"""
reporter_node 답변 품질 점수 주입 단위 테스트
RED → GREEN → REFACTOR 사이클
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── 공통 헬퍼 ──────────────────────────────────────────────────────────────────

def _followup_entry(persona: str, score: int, reason: str) -> dict:
    return {
        "type": "followup_judge",
        "followup_count": 0,
        "score": score,
        "threshold": 30,
        "needs_followup": False,
        "reason": reason,
        "persona": persona,
        "question": "질문 내용",
        "answer": "답변 내용",
    }


def _state(debug_log: list | None = None) -> dict:
    return {
        "sections": {"서비스 개요": "AI 기획서 검증 서비스"},
        "messages": [
            {"role": "assistant", "name": "investor", "content": "수익 모델이 있나요?"},
            {"role": "user", "content": "구독 모델입니다."},
        ],
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
        "debug_log": debug_log or [],
        "pending_debug": {},
        "verification_results": [],
        "answer_fact_checks": [],
    }


def _mock_report():
    mock = MagicMock()
    mock.summary = "종합 평가"
    mock.overall_score = 55
    mock.weaknesses = []
    mock.closing = "마무리"
    return mock


# ── followup_judge_node: persona 필드 포함 여부 ────────────────────────────────

@pytest.mark.asyncio
async def test_followup_judge_entry_includes_persona():
    """followup_judge debug entry에 persona 필드가 포함된다."""
    from backend.nodes import followup_judge_node

    state = _state()

    mock_judge = MagicMock()
    mock_judge.score = 50
    mock_judge.reason = "테스트"
    mock_judge.needs_followup = False

    with patch("backend.nodes._bound_followup") as mock_followup:
        mock_followup.ainvoke = AsyncMock(return_value=mock_judge)
        result = await followup_judge_node(state)

    log_entries = result.get("debug_log", [])
    assert len(log_entries) == 1
    assert "persona" in log_entries[0]
    assert log_entries[0]["persona"] == "investor"


# ── _format_followup_scores: debug_log → 점수 블록 포맷팅 ──────────────────────

def test_format_followup_scores_returns_block_when_entries_exist():
    """followup_judge 항목이 있으면 점수 블록 문자열을 반환한다."""
    from backend.nodes import _format_followup_scores

    state = _state(debug_log=[
        _followup_entry("investor", 15, "수치 근거 없음"),
        _followup_entry("cto", 65, "방향은 있으나 구체성 부족"),
    ])
    result = _format_followup_scores(state)

    assert "investor" in result
    assert "15" in result
    assert "cto" in result
    assert "65" in result


def test_format_followup_scores_returns_empty_when_no_entries():
    """followup_judge 항목이 없으면 빈 문자열을 반환한다."""
    from backend.nodes import _format_followup_scores

    result = _format_followup_scores(_state())
    assert result == ""


def test_format_followup_scores_ignores_non_followup_entries():
    """type이 followup_judge가 아닌 항목은 무시한다."""
    from backend.nodes import _format_followup_scores

    state = _state(debug_log=[
        {"type": "verification", "items": []},
        _followup_entry("mentor", 8, "핵심 회피"),
    ])
    result = _format_followup_scores(state)

    assert "mentor" in result
    assert "8" in result


# ── reporter_node: 점수 블록 주입 확인 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_reporter_includes_followup_scores_in_llm_call():
    """followup 점수가 있으면 reporter가 LLM에 점수 블록을 포함해 호출한다."""
    from backend.nodes import reporter_node

    state = _state(debug_log=[
        _followup_entry("investor", 12, "수치 없음"),
    ])

    captured_messages = []

    async def mock_ainvoke(messages):
        captured_messages.extend(messages)
        return _mock_report()

    with patch("backend.nodes._bound_reporter") as mock_reporter:
        mock_reporter.ainvoke = mock_ainvoke
        await reporter_node(state)

    human_content = next(
        m.content for m in captured_messages if hasattr(m, "content") and "investor" in m.content
    )
    assert "12" in human_content
    assert "investor" in human_content


@pytest.mark.asyncio
async def test_reporter_skips_score_block_when_no_followup_entries():
    """followup 점수가 없으면 reporter LLM 호출에 점수 블록이 없다."""
    from backend.nodes import reporter_node

    state = _state()

    captured_messages = []

    async def mock_ainvoke(messages):
        captured_messages.extend(messages)
        return _mock_report()

    with patch("backend.nodes._bound_reporter") as mock_reporter:
        mock_reporter.ainvoke = mock_ainvoke
        await reporter_node(state)

    human_msg = next(
        (m for m in captured_messages if hasattr(m, "type") and m.type == "human"),
        None
    )
    assert human_msg is not None
    assert "답변 품질" not in human_msg.content
