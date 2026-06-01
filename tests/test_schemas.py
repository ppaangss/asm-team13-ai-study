from backend.schemas import UploadResponse, ChatRequest, ChatEvent, FinalReport, PlannerState

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


from backend.schemas import OrchestratorRound, OrchestratorPlan

def test_orchestrator_round_valid():
    r = OrchestratorRound(persona="investor", section="1. 문제 정의", focus="시장 차별성 근거 없음")
    assert r.persona == "investor"
    assert r.section == "1. 문제 정의"
    assert r.focus == "시장 차별성 근거 없음"

def test_orchestrator_round_invalid_persona():
    from pydantic import ValidationError
    import pytest
    with pytest.raises(ValidationError):
        OrchestratorRound(persona="invalid", section="섹션", focus="허점")

def test_orchestrator_plan_has_rounds():
    plan = OrchestratorPlan(rounds=[
        OrchestratorRound(persona="investor", section="1. 문제 정의", focus="차별성 부족"),
        OrchestratorRound(persona="cto", section="4. 기술 구현", focus="환각 처리 없음"),
    ])
    assert len(plan.rounds) == 2
    assert plan.rounds[0].persona == "investor"

def test_planner_state_has_orchestrator_plan_field():
    hints = PlannerState.__annotations__
    assert "orchestrator_plan" in hints
