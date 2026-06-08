"""
세션 설정(최대 라운드, 꼬리질문 임계값) 단위 테스트
RED → GREEN → REFACTOR 사이클
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── 공통 상태 ────────────────────────────────────────────────────────────────

def _judge_state(followup_count: int = 0, thresholds: dict | None = None) -> dict:
    return {
        "sections": {},
        "messages": [
            {"role": "assistant", "name": "investor", "content": "질문"},
            {"role": "user", "content": "답변"},
        ],
        "round": 0,
        "persona_outputs": [],
        "final_report": "",
        "orchestrator_plan": [],
        "sections_by_persona": {},
        "persona_findings": [],
        "review_count": 0,
        "orchestrator_request": {},
        "followup_count": followup_count,
        "current_persona": "investor",
        "needs_followup": False,
        "debug_log": [],
        "pending_debug": {},
        "verification_results": [],
        "answer_fact_checks": [],
        **({"followup_thresholds": thresholds} if thresholds is not None else {}),
    }


def _mock_judge(score: int):
    mock = MagicMock()
    mock.score = score
    mock.reason = "테스트"
    mock.needs_followup = score < 30
    return mock


# ── followup_judge_node: 임계값 state 적용 ───────────────────────────────────

@pytest.mark.asyncio
async def test_followup_judge_uses_threshold_from_state():
    """state.followup_thresholds가 있으면 기본값 대신 해당 임계값을 사용한다."""
    from backend.nodes import followup_judge_node

    # score=50 → 기본 임계값 30 기준이면 통과(needs_followup=False)
    # 커스텀 임계값 80 기준이면 꼬리질문 필요(needs_followup=True)
    state = _judge_state(followup_count=0, thresholds={0: 80, 1: 40, 2: 10})

    with patch("backend.nodes._bound_followup") as mock_followup:
        mock_followup.ainvoke = AsyncMock(return_value=_mock_judge(score=50))
        result = await followup_judge_node(state)

    assert result["needs_followup"] is True


@pytest.mark.asyncio
async def test_followup_judge_falls_back_to_default_threshold():
    """state에 followup_thresholds가 없으면 기본값 {0:30, 1:15, 2:5}를 사용한다."""
    from backend.nodes import followup_judge_node

    state = _judge_state(followup_count=0)  # thresholds 미설정

    with patch("backend.nodes._bound_followup") as mock_followup:
        mock_followup.ainvoke = AsyncMock(return_value=_mock_judge(score=50))
        result = await followup_judge_node(state)

    # score=50 >= 기본 임계값 30 → 꼬리질문 없음
    assert result["needs_followup"] is False


@pytest.mark.asyncio
async def test_followup_judge_threshold_zero_means_no_followup():
    """임계값 0이면 어떤 점수에서도 꼬리질문이 발생하지 않는다."""
    from backend.nodes import followup_judge_node

    state = _judge_state(followup_count=0, thresholds={0: 0, 1: 0, 2: 0})

    with patch("backend.nodes._bound_followup") as mock_followup:
        mock_followup.ainvoke = AsyncMock(return_value=_mock_judge(score=0))
        result = await followup_judge_node(state)

    assert result["needs_followup"] is False


# ── _route_after_followup: max_rounds state 적용 ─────────────────────────────

def test_route_uses_max_rounds_from_state():
    """state.max_rounds가 있으면 전역 MAX_ROUNDS 대신 해당 값으로 라운드 종료를 판단한다."""
    from backend.graph import _route_after_followup

    # 플랜은 6라운드지만 max_rounds=3으로 설정 → 3라운드에서 reporter로
    state = {
        "round": 3,
        "max_rounds": 3,
        "needs_followup": False,
        "current_persona": "investor",
        "orchestrator_plan": [{}] * 6,
    }
    assert _route_after_followup(state) == "reporter"


def test_route_continues_when_round_below_max_rounds():
    """round가 max_rounds 미만이면 question_router로 계속 진행한다."""
    from backend.graph import _route_after_followup

    state = {
        "round": 2,
        "max_rounds": 3,
        "needs_followup": False,
        "current_persona": "investor",
        "orchestrator_plan": [{}] * 6,
    }
    assert _route_after_followup(state) == "question_router"


def test_route_falls_back_to_global_max_rounds():
    """state에 max_rounds가 없으면 전역 MAX_ROUNDS를 사용한다."""
    from backend.graph import _route_after_followup
    from backend.config import MAX_ROUNDS

    state = {
        "round": MAX_ROUNDS,
        "needs_followup": False,
        "current_persona": "investor",
        "orchestrator_plan": [{}] * (MAX_ROUNDS + 2),
    }
    assert _route_after_followup(state) == "reporter"


# ── _derive_thresholds: 단일 임계값 → 3회차 딕셔너리 ─────────────────────────

def test_derive_thresholds_scales_down():
    """단일 임계값 60에서 1회차는 절반, 2회차는 최소 5 이상으로 산출된다."""
    from backend.nodes import _derive_thresholds

    result = _derive_thresholds(60)
    assert result[0] == 60
    assert result[1] == 30
    assert result[2] >= 5


def test_derive_thresholds_zero_disables_followup():
    """임계값 0이면 모든 회차 임계값이 0이다."""
    from backend.nodes import _derive_thresholds

    result = _derive_thresholds(0)
    assert result == {0: 0, 1: 0, 2: 0}
