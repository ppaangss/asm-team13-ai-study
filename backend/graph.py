from typing import Literal
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver

from backend.config import MAX_ROUNDS, PERSONA_ORDER
from backend.schemas import PlannerState
from backend.nodes import (
    orchestrator_node,
    investor_analyze_node, cto_analyze_node, mentor_analyze_node,
    orchestrator_review_node,
    investor_node, cto_node, mentor_node,
    human_node, reporter_node,
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


def _route_after_human(state: PlannerState) -> Literal["investor", "cto", "mentor", "reporter"]:
    """현재 라운드에 해당하는 페르소나로 라우팅. 계획이 없으면 round-robin 폴백."""
    if state["round"] >= MAX_ROUNDS:
        return "reporter"
    plan = state.get("orchestrator_plan", [])
    if plan and state["round"] < len(plan):
        persona = plan[state["round"]]["persona"]
        if persona in _ALL_PERSONAS:
            return persona
    return PERSONA_ORDER[state["round"] % len(PERSONA_ORDER)]


def build_graph():
    builder = StateGraph(PlannerState)

    # 노드 등록
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("investor_analyze", investor_analyze_node)
    builder.add_node("cto_analyze", cto_analyze_node)
    builder.add_node("mentor_analyze", mentor_analyze_node)
    builder.add_node("orchestrator_review", orchestrator_review_node)
    builder.add_node("investor", investor_node)
    builder.add_node("cto", cto_node)
    builder.add_node("mentor", mentor_node)
    builder.add_node("human", human_node)
    builder.add_node("reporter", reporter_node)

    # 시작: orchestrator → 3개 analyze 노드 순차 실행
    builder.add_edge(START, "orchestrator")
    builder.add_edge("orchestrator", "investor_analyze")
    builder.add_edge("investor_analyze", "cto_analyze")
    builder.add_edge("cto_analyze", "mentor_analyze")
    builder.add_edge("mentor_analyze", "orchestrator_review")

    # ReAct 루프: review → continue(재분석) or done(질문 생성 라우팅)
    builder.add_conditional_edges(
        "orchestrator_review",
        _should_continue_react,
        {
            "continue": "investor_analyze",
            "done": "investor",
        },
    )

    # 질문 생성 노드들 → human
    builder.add_edge("investor", "human")
    builder.add_edge("cto", "human")
    builder.add_edge("mentor", "human")

    # human 이후 다음 라운드 라우팅
    builder.add_conditional_edges(
        "human",
        _route_after_human,
        {"investor": "investor", "cto": "cto", "mentor": "mentor", "reporter": "reporter"},
    )

    builder.add_edge("reporter", END)

    return builder.compile(checkpointer=_checkpointer)


graph = build_graph()
