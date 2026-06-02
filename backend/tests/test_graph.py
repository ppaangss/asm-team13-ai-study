from langgraph.types import Command
from app.graph import build_graph, should_continue


def test_should_continue_until_max_rounds():
    assert should_continue({"round": 0, "max_rounds": 2}) == "ask"
    assert should_continue({"round": 1, "max_rounds": 2}) == "ask"


def test_should_report_at_max_rounds():
    assert should_continue({"round": 2, "max_rounds": 2}) == "report"


def _initial_state():
    return {
        "sections": {"문제정의": "발표 전 약점을 모른다", "차별성": "유사 서비스 미검토"},
        "persona_analyses": [], "weaknesses": [], "question_pool": [],
        "asked": [], "transcript": [], "current_question": {}, "current_answer": "",
        "round": 0, "max_rounds": 1, "final_report": {},
    }


def test_graph_runs_analysis_dialogue_and_report(fake_llm):
    graph = build_graph()
    cfg = {"configurable": {"thread_id": "t1"}}

    first = graph.invoke(_initial_state(), cfg)
    assert "__interrupt__" in first
    assert first["__interrupt__"][0].value["persona"] == "투자자"

    final = graph.invoke(Command(resume="제 답변입니다."), cfg)
    assert "final_report" in final
    assert final["final_report"]["weaknesses"]
    assert final["final_report"]["summary"]
