from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import interrupt

from backend.config import MODEL_NAME
from backend.prompts import SYSTEM_PROMPTS
from backend.rag import retrieve, retrieve_persona
from backend.schemas import PlannerState, OrchestratorPlan, OrchestratorReview, FollowupJudge, VerificationResult, FinalReport
from backend.tools import web_search

llm = init_chat_model(model=MODEL_NAME, temperature=0.7)
_bound_llm = llm.bind_tools([web_search])
_bound_orchestrator = llm.with_structured_output(OrchestratorPlan)
_bound_review = llm.with_structured_output(OrchestratorReview)
_bound_followup = llm.with_structured_output(FollowupJudge)
_bound_verification = llm.with_structured_output(VerificationResult)
_bound_reporter = llm.with_structured_output(FinalReport)


def _trim_to_question(text: str) -> str:
    """첫 번째 ? 이후 내용 제거, 앞뒤 따옴표 제거."""
    text = text.strip().strip('"').strip("'").strip()
    idx = text.find('?')
    return text[:idx + 1] if idx != -1 else text


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


async def verification_node(state: PlannerState) -> dict:
    """기획서 7개 항목 정적 검증. Q&A 시작 전 1회 실행."""
    context = _format_context(state)
    messages = [
        SystemMessage(content=SYSTEM_PROMPTS["verification"]),
        HumanMessage(content=context),
    ]
    try:
        result: VerificationResult = await _bound_verification.ainvoke(messages)
        items = [item.model_dump() for item in result.items]
    except Exception:
        items = []

    return {
        "verification_results": items,
        "debug_log": [{"type": "verification", "items": items}],
    }


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

    # 이전에 질문된 내용 목록 (중복 방지용)
    asked_questions = [
        m["content"] for m in state.get("messages", [])
        if m.get("role") == "assistant"
    ]
    asked_block = (
        "\n\n=== 이미 질문된 내용 — 아래와 동일하거나 유사한 질문 절대 금지 ===\n"
        + "\n".join(f"- {q}" for q in asked_questions)
    ) if asked_questions else ""

    is_followup = state.get("followup_count", 0) > 0
    if is_followup:
        instruction = (
            "이전 답변을 바탕으로 꼬리 질문 1개를 작성하세요.\n"
            "규칙: [이미 질문된 내용]과 같거나 비슷한 표현으로 묻지 말 것. "
            "다른 각도로 파고드세요. 구어체로, 따옴표 없이, 물음표 한 번만."
        )
    else:
        instruction = (
            "위 기획서, 대화 이력, 사전 분석 결과를 바탕으로 날카로운 압박 질문 1개를 작성하세요.\n"
            "규칙: [이미 질문된 내용]과 주제가 겹치는 질문은 하지 말 것. "
            "아직 다뤄지지 않은 새로운 허점을 골라 실제 심사 현장에서 구두로 말하는 것처럼 짧고 자연스럽게 작성하세요."
        )

    base_messages = [
        SystemMessage(content=SYSTEM_PROMPTS[persona]),
        HumanMessage(
            content=(
                f"{context}\n\n{history}{focus_context}{rag_block}{findings_block}"
                f"{asked_block}\n\n{instruction}"
            )
        ),
    ]

    # 질문 스트리밍 (ainvoke를 사용하지 않아 이중 스트리밍 방지)
    full_content = ""
    async for chunk in llm.astream(base_messages):
        if chunk.content:
            full_content += chunk.content

    full_content = _trim_to_question(full_content)
    result: dict = {
        "messages": [{"role": "assistant", "name": persona, "content": full_content}],
        "persona_outputs": [{"persona": persona, "question": full_content, "round": state["round"]}],
    }

    # 꼬리질문 생성 직후: pending_debug(판단 대상 Q&A)와 지금 생성한 꼬리질문을 합쳐 debug_log emit
    pending = state.get("pending_debug", {})
    if is_followup and pending:
        result["debug_log"] = [{**pending, "followup_question": full_content}]
        result["pending_debug"] = {}

    return result


async def question_router(state: PlannerState) -> dict:
    """질문 생성 페르소나 라우팅을 위한 패스스루 노드."""
    return {}


async def investor_node(state: PlannerState) -> dict:
    result = await _run_persona("investor", state)
    return {**result, "current_persona": "investor"}


async def cto_node(state: PlannerState) -> dict:
    result = await _run_persona("cto", state)
    return {**result, "current_persona": "cto"}


async def mentor_node(state: PlannerState) -> dict:
    result = await _run_persona("mentor", state)
    return {**result, "current_persona": "mentor"}


def human_node(state: PlannerState) -> dict:
    """사용자 입력 대기. interrupt()로 그래프를 일시 정지한다."""
    user_answer = interrupt("user_input")
    return {"messages": [{"role": "user", "content": user_answer}]}


# followup_count별 최소 score 임계값: 이 값 미만이면 꼬리 질문 필요
_FOLLOWUP_THRESHOLDS = {0: 30, 1: 15, 2: 5}


async def followup_judge_node(state: PlannerState) -> dict:
    """마지막 Q&A를 검토해 꼬리 질문 필요 여부 판단. 불필요하면 round 증가."""
    from backend.config import MAX_FOLLOWUPS

    msgs = state.get("messages", [])
    last_q = next((m for m in reversed(msgs) if m.get("role") == "assistant"), None)
    last_a = next((m for m in reversed(msgs) if m.get("role") == "user"), None)

    qa_text = ""
    if last_q:
        qa_text += f"[질문 — {last_q.get('name', 'persona')}]\n{last_q['content']}\n\n"
    if last_a:
        qa_text += f"[답변]\n{last_a['content']}"

    followup_count = state.get("followup_count", 0)
    threshold = _FOLLOWUP_THRESHOLDS.get(followup_count, 5)

    messages = [
        SystemMessage(content=SYSTEM_PROMPTS["followup_judge"]),
        HumanMessage(
            content=(
                f"=== 최근 Q&A ===\n{qa_text}\n\n"
                f"현재 꼬리 질문 횟수: {followup_count}/{MAX_FOLLOWUPS}\n"
                f"이번 회차 임계값: score < {threshold} 이면 needs_followup=true\n"
                "이 답변이 충분한지 판단하세요."
            )
        ),
    ]

    try:
        result: FollowupJudge = await _bound_followup.ainvoke(messages)
        score = max(0, min(100, result.score))
        reason = result.reason
        # LLM의 needs_followup을 신뢰하지 않고 score < threshold로 직접 판단
        needs = (score < threshold) and (followup_count < MAX_FOLLOWUPS)
    except Exception:
        needs = False
        score = None
        reason = "예외 처리 발생 — LLM 호출 오류"

    base_entry = {
        "type": "followup_judge",
        "followup_count": followup_count,
        "score": score,
        "threshold": threshold,
        "needs_followup": needs,
        "reason": reason,
        "question": last_q["content"] if last_q else "",
        "answer": last_a["content"] if last_a else "",
    }

    if needs:
        # 꼬리질문이 아직 생성되지 않았으므로 pending에 보관.
        # 페르소나 노드가 꼬리질문 생성 후 followup_question 필드를 추가해 debug_log에 emit.
        return {
            "needs_followup": True,
            "followup_count": followup_count + 1,
            "pending_debug": base_entry,
        }
    return {
        "needs_followup": False,
        "round": state["round"] + 1,
        "followup_count": 0,
        "debug_log": [base_entry],
        "pending_debug": {},
    }


async def reporter_node(state: PlannerState) -> dict:
    """모든 Q&A를 바탕으로 구조화된 종합 리포트 생성. debug_log로 프론트에 전달."""
    context = _format_context(state)
    history = _format_history(state)

    messages = [
        SystemMessage(content=SYSTEM_PROMPTS["reporter"]),
        HumanMessage(content=f"{context}\n\n{history}\n\n위 내용을 바탕으로 종합 피드백 리포트를 작성하세요."),
    ]

    try:
        result: FinalReport = await _bound_reporter.ainvoke(messages)
        report_dict = {
            "type": "report",
            "summary": result.summary,
            "overall_score": result.overall_score,
            "weaknesses": [w.model_dump() for w in result.weaknesses],
            "closing": result.closing,
        }
    except Exception:
        report_dict = {
            "type": "report",
            "summary": "리포트 생성 중 오류가 발생했습니다.",
            "overall_score": 0,
            "weaknesses": [],
            "closing": "",
        }

    return {
        "messages": [{"role": "assistant", "name": "reporter", "content": report_dict["summary"]}],
        "final_report": report_dict["summary"],
        "debug_log": [report_dict],
    }
