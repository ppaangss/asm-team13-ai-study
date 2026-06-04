import pytest
from pydantic import ValidationError

from backend.schemas import (
    UploadResponse, ChatRequest, ChatEvent, FinalReport,
    PlannerState, OrchestratorRound, OrchestratorPlan,
    VerificationItem, VerificationResult,
)

def test_upload_response_has_thread_id_and_persona():
    resp = UploadResponse(thread_id="abc-123", first_persona="investor")
    assert resp.thread_id == "abc-123"
    assert resp.first_persona == "investor"

def test_chat_request_requires_thread_id_and_message():
    req = ChatRequest(thread_id="abc-123", message="시장 차별화 전략은 RAG 도입입니다.")
    assert req.thread_id == "abc-123"
    assert req.message == "시장 차별화 전략은 RAG 도입입니다."

def test_chat_event_token():
    event = ChatEvent(token="안녕", node="investor", done=False, is_final=False)
    assert event.token == "안녕"
    assert event.done is False

def test_chat_event_done():
    event = ChatEvent(token="", node="", done=True, is_final=False)
    assert event.done is True

def test_final_report_risk_levels():
    from backend.schemas import WeaknessItem
    weakness = WeaknessItem(
        section="기술스택", issue="LLM 필요성 불분명",
        risk="상", risk_score=75, suggestion="Use case 재정의 필요"
    )
    report = FinalReport(
        summary="전반적으로 양호",
        overall_score=62,
        weaknesses=[weakness],
        closing="BM 구체화에 집중하세요.",
    )
    assert report.weaknesses[0].risk == "상"
    assert report.weaknesses[0].risk_score == 75
    assert report.overall_score == 62
    assert report.closing != ""


def test_orchestrator_round_valid():
    r = OrchestratorRound(persona="investor", section="1. 문제 정의", focus="시장 차별성 근거 없음")
    assert r.persona == "investor"
    assert r.section == "1. 문제 정의"
    assert r.focus == "시장 차별성 근거 없음"

def test_orchestrator_round_invalid_persona():
    with pytest.raises(ValidationError):
        OrchestratorRound(persona="invalid", section="섹션", focus="허점")

def test_orchestrator_plan_has_rounds():
    plan = OrchestratorPlan(
        rounds=[
            OrchestratorRound(persona="investor", section="1. 문제 정의", focus="차별성 부족"),
            OrchestratorRound(persona="cto", section="4. 기술 구현", focus="환각 처리 없음"),
        ],
        sections_by_persona={
            "investor": ["1. 문제 정의"],
            "cto": ["4. 기술 구현"],
            "mentor": [],
        },
    )
    assert len(plan.rounds) == 2
    assert plan.rounds[0].persona == "investor"
    assert "investor" in plan.sections_by_persona

def test_planner_state_has_orchestrator_plan_field():
    hints = PlannerState.__annotations__
    assert "orchestrator_plan" in hints


def test_planner_state_has_react_fields():
    """새 ReAct 필드가 PlannerState에 존재하는지 확인."""
    from typing import get_type_hints
    hints = get_type_hints(PlannerState)
    assert "sections_by_persona" in hints
    assert "persona_findings" in hints
    assert "review_count" in hints
    assert "orchestrator_request" in hints


def test_planner_state_has_followup_fields():
    """꼬리 질문 필드가 PlannerState에 존재하는지 확인."""
    from typing import get_type_hints
    hints = get_type_hints(PlannerState)
    assert "followup_count" in hints
    assert "current_persona" in hints
    assert "needs_followup" in hints


def test_followup_judge_schema():
    """FollowupJudge 스키마가 올바르게 생성되는지 확인."""
    from backend.schemas import FollowupJudge
    j = FollowupJudge(needs_followup=True, score=18, reason="답변이 추상적임")
    assert j.needs_followup is True
    assert j.score == 18
    assert j.reason == "답변이 추상적임"

    j2 = FollowupJudge(needs_followup=False, score=75, reason="충분한 수치 제시")
    assert j2.needs_followup is False
    assert j2.score == 75


def test_persona_findings_schema():
    from backend.schemas import PersonaFindings
    f = PersonaFindings(
        persona="investor",
        assigned_sections={"수익모델": "구독 기반"},
        findings="수익화 시점이 불명확하다.",
        round=0,
    )
    assert f.persona == "investor"
    assert "수익모델" in f.assigned_sections


def test_orchestrator_review_sufficient():
    from backend.schemas import OrchestratorReview
    r = OrchestratorReview(is_sufficient=True, follow_up_requests={})
    assert r.is_sufficient is True
    assert r.follow_up_requests == {}


def test_orchestrator_review_needs_more():
    from backend.schemas import OrchestratorReview
    r = OrchestratorReview(
        is_sufficient=False,
        follow_up_requests={"investor": "Unit Economics를 추가 분석해줘"},
    )
    assert r.is_sufficient is False
    assert "investor" in r.follow_up_requests


def test_verification_item_schema():
    item = VerificationItem(label="출처 검증", status="pass", reason="Gartner 2025 보고서 인용됨")
    assert item.label == "출처 검증"
    assert item.status == "pass"
    assert "Gartner" in item.reason


def test_verification_item_invalid_status():
    with pytest.raises(Exception):
        VerificationItem(label="출처 검증", status="unknown", reason="테스트")


def test_verification_result_schema():
    result = VerificationResult(items=[
        VerificationItem(label="출처 검증",  status="pass", reason="출처 명시됨"),
        VerificationItem(label="BM 명확성",  status="warn", reason="단가 미기재"),
        VerificationItem(label="문제 구체성", status="fail", reason="수치 근거 없음"),
    ])
    assert len(result.items) == 3
    assert result.items[1].status == "warn"


def test_planner_state_has_verification_field():
    from typing import get_type_hints
    hints = get_type_hints(PlannerState)
    assert "verification_results" in hints


def test_verification_node_returns_items():
    """verification_node가 verification_results와 debug_log를 반환하는지 확인."""
    from unittest.mock import AsyncMock, patch
    import asyncio

    mock_result = VerificationResult(items=[
        VerificationItem(label=f"항목{i}", status="pass", reason="테스트") for i in range(7)
    ])

    async def run():
        with patch("backend.nodes._bound_verification") as mock_llm:
            mock_llm.ainvoke = AsyncMock(return_value=mock_result)
            from backend.nodes import verification_node
            state = {
                "sections": {"1. 서비스 개요": "AI 앱"},
                "messages": [], "round": 0, "persona_outputs": [],
                "final_report": "", "orchestrator_plan": [],
                "sections_by_persona": {}, "persona_findings": [],
                "review_count": 0, "orchestrator_request": {},
                "followup_count": 0, "current_persona": "",
                "needs_followup": False, "debug_log": [],
                "pending_debug": {}, "verification_results": [],
            }
            result = await verification_node(state)
        assert "verification_results" in result
        assert len(result["verification_results"]) == 7
        assert result["debug_log"][0]["type"] == "verification"

    asyncio.run(run())
