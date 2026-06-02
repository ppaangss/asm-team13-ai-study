from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from app.schemas import AgentState
from app.agents.analyzer import investor_analyze, cto_analyze, mentor_analyze
from app.agents.synthesizer import synthesize
from app.agents.questioner import ask
from app.agents.evaluator import evaluate
from app.agents.reporter import report


def should_continue(state: dict) -> str:
    """라운드 소진 여부로 다음 질문(ask) 또는 종료(report)를 결정한다."""
    if state.get("round", 0) >= state.get("max_rounds", 6):
        return "report"
    return "ask"


def build_graph():
    b = StateGraph(AgentState)
    b.add_node("investor_analyze", investor_analyze)
    b.add_node("cto_analyze", cto_analyze)
    b.add_node("mentor_analyze", mentor_analyze)
    b.add_node("synthesize", synthesize)
    b.add_node("ask", ask)
    b.add_node("evaluate", evaluate)
    b.add_node("report", report)

    b.add_edge(START, "investor_analyze")
    b.add_edge(START, "cto_analyze")
    b.add_edge(START, "mentor_analyze")
    b.add_edge("investor_analyze", "synthesize")
    b.add_edge("cto_analyze", "synthesize")
    b.add_edge("mentor_analyze", "synthesize")
    b.add_edge("synthesize", "ask")
    b.add_edge("ask", "evaluate")
    b.add_conditional_edges("evaluate", should_continue, {"ask": "ask", "report": "report"})
    b.add_edge("report", END)

    return b.compile(checkpointer=MemorySaver())
