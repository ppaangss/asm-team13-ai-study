from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langgraph.types import interrupt

from backend.config import MODEL_NAME
from backend.prompts import SYSTEM_PROMPTS
from backend.rag import retrieve, retrieve_persona
from backend.schemas import PlannerState, OrchestratorPlan, OrchestratorReview
from backend.tools import web_search

llm = init_chat_model(model=MODEL_NAME, temperature=0.7)
_bound_llm = llm.bind_tools([web_search])
_bound_orchestrator = llm.with_structured_output(OrchestratorPlan)
_bound_review = llm.with_structured_output(OrchestratorReview)


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
    """기획서 분석 → 6라운드 계획 + 페르소나별 섹션 배분."""
    context = _format_context(state)
    rag_context = retrieve(context[:500])
    rag_block = f"\n\n{rag_context}" if rag_context else ""

    messages = [
        SystemMessage(content=SYSTEM_PROMPTS["orchestrator"]),
        HumanMessage(
            content=(
                f"{context}{rag_block}\n\n"
                "위 기획서를 분석하여 6라운드 심사 계획과 페르소나별 섹션 배분을 작성하세요."
            )
        ),
    ]
    try:
        plan: OrchestratorPlan = await _bound_orchestrator.ainvoke(messages)
        rounds = [r.model_dump() for r in plan.rounds]
        sections_by_persona: dict[str, dict[str, str]] = {}
        for persona, titles in plan.sections_by_persona.items():
            sections_by_persona[persona] = {
                t: state["sections"][t]
                for t in titles
                if t in state["sections"]
            }
    except Exception:
        rounds = []
        sections_by_persona = {
            p: dict(state["sections"])
            for p in ["investor", "cto", "mentor"]
        }
    return {"orchestrator_plan": rounds, "sections_by_persona": sections_by_persona}


async def _run_analyze(persona: str, state: PlannerState) -> dict:
    """배분된 섹션만 받아 허점 분석 후 findings 반환. ReAct 루프에서 재실행 가능."""
    assigned = state.get("sections_by_persona", {}).get(persona, {})
    if not assigned:
        assigned = state["sections"]  # 폴백: 전체 섹션

    sections_text = "\n".join(
        f"[{title}]\n{content}" for title, content in assigned.items()
    )

    follow_up = state.get("orchestrator_request", {}).get(persona, "")
    follow_up_block = f"\n\n[추가 분석 요청]\n{follow_up}" if follow_up else ""

    persona_rag = retrieve_persona(persona, sections_text[:400])
    persona_rag_block = f"\n\n{persona_rag}" if persona_rag else ""

    messages = [
        SystemMessage(content=SYSTEM_PROMPTS[f"{persona}_analyze"]),
        HumanMessage(
            content=(
                f"=== 분석 대상 섹션 ===\n{sections_text}"
                f"{follow_up_block}"
                f"{persona_rag_block}\n\n"
                "위 섹션의 핵심 허점을 분석하세요."
            )
        ),
    ]

    full_content = ""
    async for chunk in llm.astream(messages):
        if chunk.content:
            full_content += chunk.content

    return {
        "persona_findings": [{
            "persona": persona,
            "findings": full_content,
            "round": state["round"],
        }],
        "orchestrator_request": {},  # 처리 완료 후 초기화
    }


async def investor_analyze_node(state: PlannerState) -> dict:
    return await _run_analyze("investor", state)


async def cto_analyze_node(state: PlannerState) -> dict:
    return await _run_analyze("cto", state)


async def mentor_analyze_node(state: PlannerState) -> dict:
    return await _run_analyze("mentor", state)


async def orchestrator_review_node(state: PlannerState) -> dict:
    """현재 라운드 persona_findings를 검토. 충분하면 통과, 부족하면 follow_up_requests 반환."""
    current_round = state["round"]
    latest_by_persona: dict[str, str] = {}
    for f in state.get("persona_findings", []):
        if f["round"] == current_round:
            latest_by_persona[f["persona"]] = f["findings"]

    findings_text = "\n\n".join(
        f"[{persona}]\n{findings}" for persona, findings in latest_by_persona.items()
    )

    messages = [
        SystemMessage(content="""당신은 기획서 심사 품질 검토자입니다.
각 페르소나(investor/cto/mentor)의 분석 결과를 검토하여:
- 허점이 구체적이고 근거가 있으면 is_sufficient=true
- 분석이 너무 추상적이거나 중요 허점을 놓쳤으면 is_sufficient=false와 보완 요청 작성
follow_up_requests는 부족한 페르소나에만 작성합니다."""),
        HumanMessage(
            content=(
                f"=== 현재 라운드({current_round}) 분석 결과 ===\n"
                f"{findings_text}\n\n"
                "분석 품질을 검토하고 충분 여부를 판단하세요."
            )
        ),
    ]

    try:
        review: OrchestratorReview = await _bound_review.ainvoke(messages)
        follow_up = dict(review.follow_up_requests) if not review.is_sufficient else {}
    except Exception:
        follow_up = {}

    return {
        "review_count": state.get("review_count", 0) + 1,
        "orchestrator_request": follow_up,
    }


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

    # 현재 라운드의 이 페르소나 findings 조회 (재분석 시 최신 결과 사용)
    findings_this_persona = [
        f["findings"] for f in state.get("persona_findings", [])
        if f["persona"] == persona and f["round"] == state["round"]
    ]
    current_findings = findings_this_persona[-1] if findings_this_persona else ""
    findings_block = (
        f"\n\n[사전 분석 결과]\n{current_findings}"
        if current_findings else ""
    )

    base_messages = [
        SystemMessage(content=SYSTEM_PROMPTS[persona]),
        HumanMessage(
            content=(
                f"{context}\n\n{history}{focus_context}{rag_block}{findings_block}\n\n"
                "위 기획서, 대화 이력, 사전 분석 결과를 바탕으로 날카로운 압박 질문 1개를 생성하세요."
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


async def question_router(state: PlannerState) -> dict:
    """질문 생성 페르소나 라우팅을 위한 패스스루 노드."""
    return {}


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
