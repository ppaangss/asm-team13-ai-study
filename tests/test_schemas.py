import pytest
from pydantic import ValidationError

from backend.schemas import (
    UploadResponse, ChatRequest, ChatEvent, FinalReport,
    PlannerState, OrchestratorRound, OrchestratorPlan,
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
    report = FinalReport(
        summary="전반적으로 양호",
        weaknesses=[
            {"section": "기술스택", "issue": "LLM 필요성 불분명", "risk": "상", "suggestion": "Use case 재정의 필요"}
        ]
    )
    assert report.weaknesses[0]["risk"] == "상"


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
