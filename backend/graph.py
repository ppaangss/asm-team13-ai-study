from typing import Literal
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver

from backend.config import MAX_ROUNDS, PERSONA_ORDER
from backend.schemas import PlannerState
from backend.nodes import (
    orchestrator_node,
    investor_node, cto_node, mentor_node,
    human_node, reporter_node,
)

_checkpointer = InMemorySaver()


def _route_after_orchestrator(state: PlannerState) -> Literal["investor", "cto", "mentor"]:
    """오케스트레이터 계획의 첫 번째 라운드 페르소나로 라우팅."""
    plan = state.get("orchestrator_plan", [])
    if plan:
        return plan[0]["persona"]
    return "investor"


def _route_after_human(state: PlannerState) -> Literal["investor", "cto", "mentor", "reporter"]:
    """현재 라운드에 해당하는 페르소나로 라우팅. 계획이 없으면 round-robin 폴백."""
    if state["round"] >= MAX_ROUNDS:
        return "reporter"
    plan = state.get("orchestrator_plan", [])
    if plan and state["round"] < len(plan):
        return plan[state["round"]]["persona"]
    return PERSONA_ORDER[state["round"] % len(PERSONA_ORDER)]


def build_graph():
    builder = StateGraph(PlannerState)

    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("investor", investor_node)
    builder.add_node("cto", cto_node)
    builder.add_node("mentor", mentor_node)
    builder.add_node("human", human_node)
    builder.add_node("reporter", reporter_node)

    builder.add_edge(START, "orchestrator")
    builder.add_conditional_edges(
        "orchestrator",
        _route_after_orchestrator,
        {"investor": "investor", "cto": "cto", "mentor": "mentor"},
    )

    builder.add_edge("investor", "human")
    builder.add_edge("cto", "human")
    builder.add_edge("mentor", "human")

    builder.add_conditional_edges(
        "human",
        _route_after_human,
        {"investor": "investor", "cto": "cto", "mentor": "mentor", "reporter": "reporter"},
    )

    builder.add_edge("reporter", END)

    return builder.compile(checkpointer=_checkpointer)


graph = build_graph()
