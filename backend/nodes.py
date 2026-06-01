from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import interrupt

from backend.config import MODEL_NAME
from backend.prompts import SYSTEM_PROMPTS
from backend.schemas import PlannerState, OrchestratorPlan

llm = init_chat_model(model=MODEL_NAME, temperature=0.7)


def _format_context(state: PlannerState) -> str:
    """기획서 섹션을 LLM 컨텍스트 문자열로 변환."""
    lines = ["=== 기획서 내용 ==="]
    for title, content in state["sections"].items():
        lines.append(f"\n[{title}]\n{content}")
    return "\n".join(lines)


def _format_history(state: PlannerState) -> str:
    """대화 이력을 문자열로 변환."""
    if not state["messages"]:
        return "(대화 이력 없음)"
    lines = ["=== 이전 대화 ==="]
    for msg in state["messages"]:
        role = msg.get("name", msg.get("role", "unknown"))
        lines.append(f"[{role}]: {msg['content']}")
    return "\n".join(lines)


async def orchestrator_node(state: PlannerState) -> dict:
    """기획서를 분석해 6라운드 심사 계획을 수립한다."""
    context = _format_context(state)

    structured_llm = llm.with_structured_output(OrchestratorPlan)
    messages = [
        SystemMessage(content=SYSTEM_PROMPTS["orchestrator"]),
        HumanMessage(content=f"{context}\n\n위 기획서를 분석하여 6라운드 심사 계획을 작성하세요."),
    ]
    plan: OrchestratorPlan = await structured_llm.ainvoke(messages)
    return {
        "orchestrator_plan": [r.model_dump() for r in plan.rounds],
    }


async def _run_persona(persona: str, state: PlannerState) -> dict:
    """공통 페르소나 실행 로직. llm.astream()으로 토큰 단위 스트리밍."""
    context = _format_context(state)
    history = _format_history(state)

    plan = state.get("orchestrator_plan", [])
    focus_context = ""
    if plan and state["round"] < len(plan):
        current = plan[state["round"]]
        focus_context = (
            f"\n\n[이번 라운드 집중 공략]"
            f"\n- 대상 섹션: {current['section']}"
            f"\n- 집중 허점: {current['focus']}"
        )

    messages = [
        SystemMessage(content=SYSTEM_PROMPTS[persona]),
        HumanMessage(
            content=(
                f"{context}\n\n{history}{focus_context}\n\n"
                "위 기획서와 대화 이력을 바탕으로 날카로운 압박 질문 1개를 생성하세요."
            )
        ),
    ]

    full_content = ""
    async for chunk in llm.astream(messages):
        if chunk.content:
            full_content += chunk.content

    return {
        "messages": [{"role": "assistant", "name": persona, "content": full_content}],
        "persona_outputs": [{"persona": persona, "question": full_content, "round": state["round"]}],
    }


async def investor_node(state: PlannerState) -> dict:
    return await _run_persona("investor", state)


async def cto_node(state: PlannerState) -> dict:
    return await _run_persona("cto", state)


async def mentor_node(state: PlannerState) -> dict:
    return await _run_persona("mentor", state)


def human_node(state: PlannerState) -> dict:
    """사용자 입력 대기. interrupt()로 그래프를 일시 정지한다."""
    user_answer = interrupt("user_input")
    return {
        "messages": [{"role": "user", "content": user_answer}],
        "round": state["round"] + 1,
    }


async def reporter_node(state: PlannerState) -> dict:
    """모든 Q&A를 바탕으로 종합 리포트 생성. llm.astream()으로 스트리밍."""
    context = _format_context(state)
    history = _format_history(state)

    messages = [
        SystemMessage(content=SYSTEM_PROMPTS["reporter"]),
        HumanMessage(content=f"{context}\n\n{history}\n\n위 내용을 바탕으로 종합 피드백 리포트를 작성하세요."),
    ]

    full_content = ""
    async for chunk in llm.astream(messages):
        if chunk.content:
            full_content += chunk.content

    return {
        "messages": [{"role": "assistant", "name": "reporter", "content": full_content}],
        "final_report": full_content,
    }
