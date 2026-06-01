# 실시간 스트리밍 + 오케스트레이터 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `llm.ainvoke()` → `llm.astream()`으로 교체해 진짜 토큰 단위 스트리밍을 구현하고, 기획서 섹션을 분석해 6라운드 맞춤 심사 계획을 수립하는 오케스트레이터 노드를 추가한다.

**Architecture:** 오케스트레이터가 기획서 업로드 직후 `with_structured_output`으로 섹션별 허점을 분석해 `OrchestratorPlan`(6라운드 × {persona, section, focus})을 생성한다. 이후 각 페르소나 노드는 `orchestrator_plan[round]`의 `focus`를 프롬프트에 주입해 해당 섹션을 집중 공략하고, `llm.astream()`으로 토큰을 실시간 방출한다.

**Tech Stack:** LangGraph 1.2.2, LangChain 1.3.2, solar-pro2 (langchain-upstage 0.7.7), Pydantic v2, Python 3.13

---

## 변경 파일 구조

```
backend/
  schemas.py    OrchestratorRound, OrchestratorPlan 추가 + PlannerState에 orchestrator_plan 필드 추가
  prompts.py    ORCHESTRATOR_SYSTEM_PROMPT 추가
  nodes.py      _run_persona → astream 변경, orchestrator_node 추가, reporter_node → astream 변경
  graph.py      orchestrator 노드 추가, START→orchestrator, 조건부 라우팅 2개로 변경
  main.py       initial_state에 orchestrator_plan: [] 추가

tests/
  test_schemas.py   OrchestratorRound, OrchestratorPlan, PlannerState.orchestrator_plan 테스트 추가
```

## 변경 후 그래프 흐름

```
START → orchestrator (기획서 분석 → 6라운드 plan 생성)
      → [plan[0].persona] (첫 번째 타깃 페르소나)
      → human (interrupt)
      → [plan[round].persona] 또는 reporter (round >= 6)
      → END
```

---

## Task 1: schemas.py — OrchestratorPlan 모델 + PlannerState 업데이트

**Files:**
- Modify: `backend/schemas.py`
- Modify: `tests/test_schemas.py`

- [ ] **Step 1: `tests/test_schemas.py`에 새 테스트 추가**

파일 끝에 아래 테스트를 추가한다 (기존 5개 테스트는 그대로 유지):

```python
from backend.schemas import OrchestratorRound, OrchestratorPlan

def test_orchestrator_round_valid():
    r = OrchestratorRound(persona="investor", section="1. 문제 정의", focus="시장 차별성 근거 없음")
    assert r.persona == "investor"
    assert r.section == "1. 문제 정의"
    assert r.focus == "시장 차별성 근거 없음"

def test_orchestrator_round_invalid_persona():
    from pydantic import ValidationError
    import pytest
    with pytest.raises(ValidationError):
        OrchestratorRound(persona="invalid", section="섹션", focus="허점")

def test_orchestrator_plan_has_rounds():
    plan = OrchestratorPlan(rounds=[
        OrchestratorRound(persona="investor", section="1. 문제 정의", focus="차별성 부족"),
        OrchestratorRound(persona="cto", section="4. 기술 구현", focus="환각 처리 없음"),
    ])
    assert len(plan.rounds) == 2
    assert plan.rounds[0].persona == "investor"

def test_planner_state_has_orchestrator_plan_field():
    from typing import get_type_hints
    hints = PlannerState.__annotations__
    assert "orchestrator_plan" in hints
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
cd C:\Users\nunu\Desktop\test\AI_EDU\asm-team13-ai-study && pytest tests/test_schemas.py -v -k "orchestrator"
```

Expected: `ImportError: cannot import name 'OrchestratorRound'`

- [ ] **Step 3: `backend/schemas.py` 업데이트**

전체 파일을 아래 내용으로 교체한다:

```python
from pydantic import BaseModel
from typing import Annotated, Any, Literal
import operator
from typing_extensions import TypedDict


# ── Orchestrator 계획 모델 ────────────────────────────────────
class OrchestratorRound(BaseModel):
    persona: Literal["investor", "cto", "mentor"]
    section: str
    focus: str


class OrchestratorPlan(BaseModel):
    rounds: list[OrchestratorRound]


# ── LangGraph State ──────────────────────────────────────────
class PlannerState(TypedDict):
    sections: dict[str, str]
    messages: Annotated[list[dict], operator.add]
    round: int
    persona_outputs: Annotated[list[dict], operator.add]
    final_report: str
    orchestrator_plan: list[dict]   # [{persona, section, focus}] × 6


# ── API 요청/응답 ─────────────────────────────────────────────
class UploadResponse(BaseModel):
    thread_id: str
    first_persona: str = "investor"


class ChatRequest(BaseModel):
    thread_id: str
    message: str


class ChatEvent(BaseModel):
    token: str
    node: str
    done: bool
    is_final: bool = False


class FinalReport(BaseModel):
    summary: str
    weaknesses: list[dict[str, Any]]
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd C:\Users\nunu\Desktop\test\AI_EDU\asm-team13-ai-study && pytest tests/test_schemas.py -v
```

Expected: `9 passed` (기존 5 + 신규 4)

- [ ] **Step 5: 커밋**

```bash
git add backend/schemas.py tests/test_schemas.py
git commit -m "feat: add OrchestratorRound/OrchestratorPlan schemas and orchestrator_plan to PlannerState"
```

---

## Task 2: prompts.py — 오케스트레이터 시스템 프롬프트 추가

**Files:**
- Modify: `backend/prompts.py`

- [ ] **Step 1: `backend/prompts.py` 상단에 `ORCHESTRATOR_SYSTEM_PROMPT` 추가**

기존 `INVESTOR_SYSTEM_PROMPT` 앞에 삽입:

```python
ORCHESTRATOR_SYSTEM_PROMPT = """당신은 기획서 심사 오케스트레이터입니다.

역할: 기획서를 분석하여 투자자(investor)·CTO(cto)·멘토(mentor) 3명의 심사위원이 6라운드에 걸쳐 가장 효과적으로 약점을 검증하도록 심사 계획을 수립합니다.

배정 기준:
- investor  → 시장성·차별성·수익 모델 약점이 있는 섹션
- cto       → 기술 실현 가능성·LLM 적정성·아키텍처 약점이 있는 섹션
- mentor    → 논리 일관성·MVP 범위·우선순위 약점이 있는 섹션
- 6라운드 안에 기획서 전 섹션을 고르게 커버하세요
- 같은 섹션과 같은 허점을 반복 배정하지 마세요

출력 규칙:
- 반드시 6개의 라운드를 JSON으로만 출력하세요
- 설명 텍스트 없이 JSON 객체만 출력합니다
- 각 라운드: {"persona": "investor"|"cto"|"mentor", "section": "섹션명", "focus": "이 라운드에서 집중할 구체적 허점"}"""
```

- [ ] **Step 2: `SYSTEM_PROMPTS` dict에 "orchestrator" 키 추가**

기존 `SYSTEM_PROMPTS = {...}` 블록을:

```python
SYSTEM_PROMPTS = {
    "orchestrator": ORCHESTRATOR_SYSTEM_PROMPT,
    "investor":     INVESTOR_SYSTEM_PROMPT,
    "cto":          CTO_SYSTEM_PROMPT,
    "mentor":       MENTOR_SYSTEM_PROMPT,
    "reporter":     REPORTER_SYSTEM_PROMPT,
}
```

- [ ] **Step 3: `PERSONA_LABELS` dict에 "orchestrator" 키 추가**

```python
PERSONA_LABELS = {
    "orchestrator": ("🎯", "오케스트레이터"),
    "investor":     ("💼", "깐깐한 투자자"),
    "cto":          ("💻", "냉철한 CTO"),
    "mentor":       ("🦉", "예리한 멘토"),
    "reporter":     ("🤖", "종합 리포터"),
}
```

- [ ] **Step 4: 임포트 확인**

```bash
cd C:\Users\nunu\Desktop\test\AI_EDU\asm-team13-ai-study && python -c "
from backend.prompts import SYSTEM_PROMPTS, PERSONA_LABELS
assert 'orchestrator' in SYSTEM_PROMPTS
assert 'orchestrator' in PERSONA_LABELS
print('prompts OK')
"
```

Expected: `prompts OK`

- [ ] **Step 5: 커밋**

```bash
git add backend/prompts.py
git commit -m "feat: add orchestrator system prompt"
```

---

## Task 3: nodes.py — astream 전환 + orchestrator_node 추가

**Files:**
- Modify: `backend/nodes.py`

- [ ] **Step 1: `backend/nodes.py` 전체를 아래 내용으로 교체**

```python
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

    # 오케스트레이터 계획에서 이번 라운드의 집중 포인트 가져오기
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
```

- [ ] **Step 2: 임포트 확인**

```bash
cd C:\Users\nunu\Desktop\test\AI_EDU\asm-team13-ai-study && python -c "
from backend.nodes import orchestrator_node, investor_node, cto_node, mentor_node, human_node, reporter_node
print('nodes OK')
"
```

Expected: `nodes OK`

- [ ] **Step 3: 커밋**

```bash
git add backend/nodes.py
git commit -m "feat: astream token streaming + orchestrator_node"
```

---

## Task 4: graph.py — 오케스트레이터 노드 + 계획 기반 라우팅

**Files:**
- Modify: `backend/graph.py`

- [ ] **Step 1: `backend/graph.py` 전체를 아래 내용으로 교체**

```python
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

    # 시작: 오케스트레이터가 기획서 분석 후 첫 페르소나 결정
    builder.add_edge(START, "orchestrator")
    builder.add_conditional_edges(
        "orchestrator",
        _route_after_orchestrator,
        {"investor": "investor", "cto": "cto", "mentor": "mentor"},
    )

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
```

- [ ] **Step 2: 그래프 노드 확인**

```bash
cd C:\Users\nunu\Desktop\test\AI_EDU\asm-team13-ai-study && python -c "
from backend.graph import graph
nodes = list(graph.nodes.keys())
print('nodes:', nodes)
assert 'orchestrator' in nodes
assert 'investor' in nodes
assert 'cto' in nodes
assert 'mentor' in nodes
assert 'human' in nodes
assert 'reporter' in nodes
print('graph OK')
"
```

Expected:
```
nodes: ['__start__', 'orchestrator', 'investor', 'cto', 'mentor', 'human', 'reporter', '__end__']
graph OK
```

- [ ] **Step 3: 커밋**

```bash
git add backend/graph.py
git commit -m "feat: orchestrator-based graph routing with plan-driven persona selection"
```

---

## Task 5: main.py — initial_state에 orchestrator_plan 추가

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: `chat_start` 함수의 `initial_state`에 `orchestrator_plan` 필드 추가**

`backend/main.py`에서 `initial_state` 딕셔너리를:

```python
    initial_state = {
        "sections": sections,
        "messages": [],
        "round": 0,
        "persona_outputs": [],
        "final_report": "",
        "orchestrator_plan": [],
    }
```

- [ ] **Step 2: 전체 테스트 통과 확인**

```bash
cd C:\Users\nunu\Desktop\test\AI_EDU\asm-team13-ai-study && pytest tests/ -v
```

Expected: `9 passed`

- [ ] **Step 3: 서버 기동 및 health 확인**

```bash
cd C:\Users\nunu\Desktop\test\AI_EDU\asm-team13-ai-study
uvicorn backend.main:app --port 8000 --reload
```

새 터미널에서:
```bash
curl http://localhost:8000/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 4: 서버 종료 후 커밋**

```bash
git add backend/main.py
git commit -m "fix: add orchestrator_plan to initial_state"
```

---

## Self-Review

### Spec 커버리지

| 요구사항 | Task | 구현 |
|----------|------|------|
| `llm.ainvoke()` → `llm.astream()` 전환 | Task 3 | ✅ `_run_persona`, `reporter_node` 모두 변경 |
| 오케스트레이터 노드 (섹션 분석 + 계획 수립) | Task 3 | ✅ `orchestrator_node` + `with_structured_output` |
| 계획 기반 라우팅 (round-robin 제거) | Task 4 | ✅ `_route_after_orchestrator`, `_route_after_human` |
| 페르소나에 focus 컨텍스트 주입 | Task 3 | ✅ `_run_persona`의 `focus_context` |
| round-robin 폴백 유지 | Task 4 | ✅ plan 없을 때 `PERSONA_ORDER` 폴백 |
| OrchestratorPlan Pydantic 모델 | Task 1 | ✅ |
| 기존 테스트 11개 모두 통과 | Task 5 | ✅ |

### 주의사항

- `with_structured_output`은 solar-pro2의 JSON 모드를 사용한다. UPSTAGE_API_KEY가 `.env`에 설정되어 있어야 한다.
- 오케스트레이터는 `ainvoke()` (스트리밍 없음)를 사용한다. 기획서 분석 시 2~5초 대기가 발생하며, 이 시간 동안 프론트엔드에 로딩 표시가 없다. 이후 개선 과제.
- `orchestrator_plan`이 빈 배열인 경우 기존 round-robin 방식으로 폴백하므로 하위 호환성이 유지된다.
