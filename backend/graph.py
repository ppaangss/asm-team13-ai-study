from typing import Literal
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver

from backend.config import MAX_ROUNDS, PERSONA_ORDER
from backend.schemas import PlannerState
from backend.nodes import investor_node, cto_node, mentor_node, human_node, reporter_node

_checkpointer = InMemorySaver()


def _route_after_human(state: PlannerState) -> Literal["investor", "cto", "mentor", "reporter"]:
    """라운드 수에 따라 다음 페르소나 또는 리포터로 라우팅."""
    if state["round"] >= MAX_ROUNDS:
        return "reporter"
    return PERSONA_ORDER[state["round"] % len(PERSONA_ORDER)]


def build_graph():
    builder = StateGraph(PlannerState)

    builder.add_node("investor", investor_node)
    builder.add_node("cto", cto_node)
    builder.add_node("mentor", mentor_node)
    builder.add_node("human", human_node)
    builder.add_node("reporter", reporter_node)

    # 최초 진입: 항상 투자자부터 시작
    builder.add_edge(START, "investor")

    # 각 페르소나 → 사용자 입력 대기
    builder.add_edge("investor", "human")
    builder.add_edge("cto", "human")
    builder.add_edge("mentor", "human")

    # 사용자 답변 후 → 다음 페르소나 or 리포터
    builder.add_conditional_edges(
        "human",
        _route_after_human,
        {"investor": "investor", "cto": "cto", "mentor": "mentor", "reporter": "reporter"},
    )

    builder.add_edge("reporter", END)

    return builder.compile(checkpointer=_checkpointer)


graph = build_graph()
