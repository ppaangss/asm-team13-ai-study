from typing import Literal
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver

from backend.config import MAX_ROUNDS, MAX_FOLLOWUPS, PERSONA_ORDER
from backend.schemas import PlannerState
from backend.nodes import (
    orchestrator_node,
    verification_node, data_verification_node,
    investor_analyze_node, cto_analyze_node, mentor_analyze_node,
    orchestrator_review_node,
    question_router,
    investor_node, cto_node, mentor_node,
    human_node, answer_fact_check_node, followup_judge_node, reporter_node,
)

_checkpointer = InMemorySaver()

MAX_REACT_ITERATIONS = 2

_ALL_PERSONAS = {"investor", "cto", "mentor"}


def _should_continue_react(state: PlannerState) -> Literal["continue", "done"]:
    """ReAct 루프 계속 여부 판단. 최대 2회 또는 sufficient이면 종료."""
    if state.get("review_count", 0) >= MAX_REACT_ITERATIONS:
        return "done"
    if not state.get("orchestrator_request"):
        return "done"
    return "continue"


def _route_to_question_persona(state: PlannerState) -> Literal["investor", "cto", "mentor"]:
    """현재 라운드의 질문 생성 페르소나 결정."""
    plan = state.get("orchestrator_plan", [])
    if plan and state["round"] < len(plan):
        persona = plan[state["round"]]["persona"]
        if persona in _ALL_PERSONAS:
            return persona
    return PERSONA_ORDER[state["round"] % len(PERSONA_ORDER)]


def _route_after_followup(state: PlannerState) -> Literal["investor", "cto", "mentor", "question_router", "reporter"]:
    """꼬리 질문 여부에 따라 라우팅. needs_followup이면 같은 페르소나, 아니면 다음 라운드."""
    if state.get("needs_followup", False):
        persona = state.get("current_persona", "investor")
        return persona if persona in _ALL_PERSONAS else "investor"

    plan = state.get("orchestrator_plan", [])
    max_r = state.get("max_rounds", MAX_ROUNDS)
    if state["round"] >= len(plan) or state["round"] >= max_r:
        return "reporter"
    return "question_router"


def build_graph():
    builder = StateGraph(PlannerState)

    # 노드 등록
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("verification", verification_node)
    builder.add_node("data_verification", data_verification_node)
    builder.add_node("investor_analyze", investor_analyze_node)
    builder.add_node("cto_analyze", cto_analyze_node)
    builder.add_node("mentor_analyze", mentor_analyze_node)
    builder.add_node("orchestrator_review", orchestrator_review_node)
    builder.add_node("question_router", question_router)
    builder.add_node("investor", investor_node)
    builder.add_node("cto", cto_node)
    builder.add_node("mentor", mentor_node)
    builder.add_node("human", human_node)
    builder.add_node("answer_fact_check", answer_fact_check_node)
    builder.add_node("followup_judge", followup_judge_node)
    builder.add_node("reporter", reporter_node)

    # 시작: orchestrator → verification → data_verification → 3개 analyze 노드 순차 실행
    builder.add_edge(START, "orchestrator")
    builder.add_edge("orchestrator", "verification")
    builder.add_edge("verification", "data_verification")
    builder.add_edge("data_verification", "investor_analyze")
    builder.add_edge("investor_analyze", "cto_analyze")
    builder.add_edge("cto_analyze", "mentor_analyze")
    builder.add_edge("mentor_analyze", "orchestrator_review")

    # ReAct 루프: review → continue(재분석) or done(질문 생성 라우팅)
    builder.add_conditional_edges(
        "orchestrator_review",
        _should_continue_react,
        {"continue": "investor_analyze", "done": "question_router"},
    )

    # question_router → 라운드별 페르소나로 라우팅
    builder.add_conditional_edges(
        "question_router",
        _route_to_question_persona,
        {"investor": "investor", "cto": "cto", "mentor": "mentor"},
    )

    # 질문 생성 노드들 → human
    builder.add_edge("investor", "human")
    builder.add_edge("cto", "human")
    builder.add_edge("mentor", "human")

    # human → answer_fact_check → followup_judge → 꼬리질문 or 다음 라운드
    builder.add_edge("human", "answer_fact_check")
    builder.add_edge("answer_fact_check", "followup_judge")
    builder.add_conditional_edges(
        "followup_judge",
        _route_after_followup,
        {
            "investor": "investor",
            "cto": "cto",
            "mentor": "mentor",
            "question_router": "question_router",
            "reporter": "reporter",
        },
    )

    builder.add_edge("reporter", END)

    return builder.compile(checkpointer=_checkpointer)


graph = build_graph()
