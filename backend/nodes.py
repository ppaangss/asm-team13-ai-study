from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langgraph.types import interrupt

from backend.config import MODEL_NAME
from backend.prompts import SYSTEM_PROMPTS
from backend.rag import retrieve
from backend.schemas import PlannerState, OrchestratorPlan
from backend.tools import web_search

llm = init_chat_model(model=MODEL_NAME, temperature=0.7)
_bound_llm = llm.bind_tools([web_search])


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
    """기획서를 분석해 6라운드 심사 계획을 수립한다. RAG로 유사 실패 패턴을 참조한다."""
    context = _format_context(state)

    rag_context = retrieve(context[:500])
    rag_block = f"\n\n{rag_context}" if rag_context else ""

    structured_llm = llm.with_structured_output(OrchestratorPlan)
    messages = [
        SystemMessage(content=SYSTEM_PROMPTS["orchestrator"]),
        HumanMessage(
            content=(
                f"{context}{rag_block}\n\n"
                "위 기획서를 분석하여 6라운드 심사 계획을 작성하세요."
            )
        ),
    ]
    try:
        plan: OrchestratorPlan = await structured_llm.ainvoke(messages)
        rounds = [r.model_dump() for r in plan.rounds]
    except Exception:
        rounds = []
    return {"orchestrator_plan": rounds}


async def _run_persona(persona: str, state: PlannerState) -> dict:
    """공통 페르소나 실행 로직.
    1단계: bind_tools LLM으로 tool call 여부 결정
    2단계: tool call 있으면 실행 후 결과 주입
    3단계: llm.astream()으로 최종 질문 스트리밍
    """
    context = _format_context(state)
    history = _format_history(state)

    plan = state.get("orchestrator_plan", [])
    focus_context = ""
    focus_section = ""
    if plan and state["round"] < len(plan):
        current = plan[state["round"]]
        focus_section = current["section"]
        focus_context = (
            f"\n\n[이번 라운드 집중 공략]"
            f"\n- 대상 섹션: {focus_section}"
            f"\n- 집중 허점: {current['focus']}"
        )

    rag_query = f"{persona} 관점 {focus_section} 약점" if focus_section else f"{persona} 관점 기획서 약점"
    rag_context = retrieve(rag_query)
    rag_block = f"\n\n{rag_context}" if rag_context else ""

    base_messages = [
        SystemMessage(content=SYSTEM_PROMPTS[persona]),
        HumanMessage(
            content=(
                f"{context}\n\n{history}{focus_context}{rag_block}\n\n"
                "위 기획서와 대화 이력을 바탕으로 날카로운 압박 질문 1개를 생성하세요."
            )
        ),
    ]

    # 1단계: LLM이 tool call 여부 결정 (실패 시 직접 스트리밍으로 폴백)
    messages = list(base_messages)
    try:
        tool_decision = await _bound_llm.ainvoke(base_messages)
        if tool_decision.tool_calls:
            # 2단계: tool call 비동기 실행 후 결과 주입
            messages.append(tool_decision)
            for tc in tool_decision.tool_calls:
                tool_result = await web_search.ainvoke(tc["args"])
                messages.append(ToolMessage(content=str(tool_result), tool_call_id=tc["id"]))
    except Exception:
        messages = list(base_messages)

    # 3단계: 최종 질문 스트리밍
    full_content = ""
    async for chunk in llm.astream(messages):
        if chunk.content:
            full_content += chunk.content

    # tool 주입 후 모델이 text 대신 tool_call만 반환한 경우 폴백
    if not full_content and len(messages) > len(base_messages):
        async for chunk in llm.astream(base_messages):
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
