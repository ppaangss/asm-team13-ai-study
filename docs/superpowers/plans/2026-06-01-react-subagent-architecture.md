# ReAct 서브에이전트 분할 + 프롬프트 개선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기획서를 페르소나별로 분할해 서브에이전트가 분석하고, 오케스트레이터가 ReAct 루프로 품질을 검증한 뒤 분석 결과 기반으로 간결한 질문을 생성한다.

**Architecture:** 오케스트레이터가 기획서 섹션을 investor/cto/mentor 전문 영역별로 나눠 각 분석 노드에 전달한다. 분석 결과를 받은 오케스트레이터가 품질을 검토하고 부족하면 보완 요청을 보내는 ReAct 루프(최대 2회)를 실행한다. 충분한 분석이 완료되면 해당 페르소나가 findings 기반으로 1~2문장의 압박 질문을 생성한다.

**Tech Stack:** LangGraph StateGraph, `with_structured_output`, 기존 solar-pro2, 기존 RAG/Tool Calling 유지

---

## 현재 구조 vs 새 구조

### 현재 (v2)
```
orchestrator (전체 기획서 → 6라운드 계획)
    ↓
investor_node (전체 기획서 + 계획 힌트 → 질문 직접 생성)
    ↓ human ↓ cto_node ↓ human ↓ mentor_node ...
```

### 새 구조 (v3)
```
orchestrator (전체 기획서 → 6라운드 계획 + 섹션 배분)
    ↓
[investor_analyze → cto_analyze → mentor_analyze]  ← 섹션 분할 수신
    ↓
orchestrator_review (분석 품질 검토)
    ├─ 부족 + iter < 2 → 보완 요청 → 분석 노드 재실행 → review 루프
    └─ 충분 → findings 저장
    ↓
investor_node / cto_node / mentor_node (findings 기반 간결 질문 생성)
    ↓ human ↓ (6라운드 반복)
    ↓
reporter_node
```

---

## File Structure

| 파일 | 변경 | 역할 |
|------|------|------|
| `backend/schemas.py` | **수정** | `PlannerState`에 findings/review 필드 추가, `PersonaFindings`, `OrchestratorReview` 스키마 추가 |
| `backend/prompts.py` | **수정** | orchestrator 섹션 배분 프롬프트, analyze 노드 프롬프트(신규), 질문 간결화 제약 추가 |
| `backend/nodes.py` | **수정** | `orchestrator_node` 섹션 배분 추가, `investor/cto/mentor_analyze_node` 신규, `orchestrator_review_node` 신규, `_run_persona` findings 기반으로 변경 |
| `backend/graph.py` | **수정** | ReAct 루프 조건부 엣지 추가 |
| `tests/test_nodes_react.py` | **신규** | analyze 노드, review 노드, ReAct 루프 조건 테스트 |

---

## 새 State 설계

```python
# backend/schemas.py에 추가될 전체 PlannerState

class PlannerState(TypedDict):
    # ── 기존 유지 ──────────────────────────────
    sections: dict[str, str]
    messages: Annotated[list[dict], operator.add]
    round: int
    persona_outputs: Annotated[list[dict], operator.add]
    final_report: str
    orchestrator_plan: list[dict]          # [{persona, section, focus}] × 6

    # ── 신규 ──────────────────────────────────
    sections_by_persona: dict[str, dict[str, str]]
    # {"investor": {"수익모델": "...", "시장분석": "..."},
    #  "cto":      {"기술구현": "...", "핵심기능": "..."},
    #  "mentor":   {"문제정의": "...", "서비스개요": "..."}}

    persona_findings: Annotated[list[dict], operator.add]
    # [{"persona": "investor", "findings": "...", "round": 0}, ...]

    review_count: int          # 현재 라운드 ReAct 반복 횟수 (0 시작, max 2)
    orchestrator_request: dict[str, str]
    # {"investor": "수익화 시점과 Unit Economics를 추가로 분석해줘"} 또는 {}
```

---

### Task 1: schemas.py — 신규 State 필드 및 스키마 추가

**Files:**
- Modify: `backend/schemas.py`
- Test: `tests/test_schemas.py`

- [ ] **Step 1: 테스트 추가**

`tests/test_schemas.py` 파일 끝에 아래 테스트 추가:

```python
def test_planner_state_has_react_fields():
    """새 ReAct 필드가 PlannerState에 존재하는지 확인."""
    from typing import get_type_hints
    hints = get_type_hints(PlannerState)
    assert "sections_by_persona" in hints
    assert "persona_findings" in hints
    assert "review_count" in hints
    assert "orchestrator_request" in hints


def test_persona_findings_schema():
    from backend.schemas import PersonaFindings
    f = PersonaFindings(
        persona="investor",
        assigned_sections={"수익모델": "구독 기반"},
        findings="수익화 시점이 불명확하다.",
        round=0,
    )
    assert f.persona == "investor"
    assert "수익모델" in f.assigned_sections


def test_orchestrator_review_sufficient():
    from backend.schemas import OrchestratorReview
    r = OrchestratorReview(is_sufficient=True, follow_up_requests={})
    assert r.is_sufficient is True
    assert r.follow_up_requests == {}


def test_orchestrator_review_needs_more():
    from backend.schemas import OrchestratorReview
    r = OrchestratorReview(
        is_sufficient=False,
        follow_up_requests={"investor": "Unit Economics를 추가 분석해줘"},
    )
    assert r.is_sufficient is False
    assert "investor" in r.follow_up_requests
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_schemas.py -v -k "react or findings or review"
```

Expected: FAIL (ImportError — PersonaFindings, OrchestratorReview 없음)

- [ ] **Step 3: schemas.py 수정**

`backend/schemas.py`의 기존 내용 뒤에 추가 (OrchestratorPlan 클래스 아래):

```python
# ── ReAct 서브에이전트 스키마 ────────────────────────────────
class PersonaFindings(BaseModel):
    persona: Literal["investor", "cto", "mentor"]
    assigned_sections: dict[str, str]   # 이 페르소나에 배분된 섹션들
    findings: str                        # 허점 분석 결과 (자유 텍스트)
    round: int


class OrchestratorReview(BaseModel):
    is_sufficient: bool
    follow_up_requests: dict[str, str]  # {persona: 보완 요청 내용} — 충분하면 {}
```

`PlannerState` TypedDict에 아래 4개 필드 추가:

```python
class PlannerState(TypedDict):
    sections: dict[str, str]
    messages: Annotated[list[dict], operator.add]
    round: int
    persona_outputs: Annotated[list[dict], operator.add]
    final_report: str
    orchestrator_plan: list[dict]
    # ReAct 신규 필드
    sections_by_persona: dict[str, dict[str, str]]
    persona_findings: Annotated[list[dict], operator.add]
    review_count: int
    orchestrator_request: dict[str, str]
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_schemas.py -v
```

Expected: 전체 통과 (기존 9개 + 신규 4개 = 13개)

- [ ] **Step 5: Commit**

```bash
git add backend/schemas.py tests/test_schemas.py
git commit -m "feat(react): add ReAct fields to PlannerState and persona findings schemas"
```

---

### Task 2: prompts.py — orchestrator 섹션 배분 + analyze 프롬프트 + 질문 간결화

**Files:**
- Modify: `backend/prompts.py`

- [ ] **Step 1: ORCHESTRATOR_SYSTEM_PROMPT 업데이트**

기존 `ORCHESTRATOR_SYSTEM_PROMPT`를 아래로 교체:

```python
ORCHESTRATOR_SYSTEM_PROMPT = """당신은 기획서 심사 오케스트레이터입니다.

역할: 기획서를 분석하여 두 가지를 동시에 출력합니다.
1) investor/cto/mentor 3명이 6라운드에 걸쳐 약점을 검증하는 심사 계획
2) 각 페르소나가 집중 분석할 섹션 배분

섹션 배분 기준:
- investor  → 시장성·차별성·수익모델·지속가능성 관련 섹션
- cto       → 기술구현·핵심기능·아키텍처 관련 섹션
- mentor    → 서비스개요·문제정의·팀구성·MVP 범위 관련 섹션
- 섹션이 여러 페르소나에 해당하면 가장 관련 높은 페르소나 하나에만 배분

심사 계획 기준:
- 6라운드 안에 기획서 전 섹션을 고르게 커버
- 같은 섹션과 같은 허점을 반복 배정하지 않음

출력 규칙:
- 반드시 JSON으로만 출력 (설명 텍스트 없이)
- rounds: 6개 라운드 배열
- sections_by_persona: 페르소나별 배분 섹션명 배열"""
```

- [ ] **Step 2: ANALYZE 프롬프트 3개 추가 (신규)**

`SYSTEM_PROMPTS` 딕셔너리 위에 아래 3개 상수 추가:

```python
INVESTOR_ANALYZE_PROMPT = """당신은 깐깐한 스타트업 투자자입니다.

역할: 배분된 기획서 섹션만을 분석해 투자 관점의 핵심 허점을 파악합니다.
분석 관점:
- 시장 규모 근거가 있는가? 수치 출처가 명확한가?
- 유사 경쟁 서비스 대비 실질적 차별점이 있는가?
- 수익화 시점과 Unit Economics가 현실적인가?
- 팀이 이 문제를 풀 역량이 있다는 근거가 있는가?

출력: 핵심 허점 2~3개를 간결하게 서술. 추후 질문 생성에 활용됩니다."""


CTO_ANALYZE_PROMPT = """당신은 냉철한 CTO입니다.

역할: 배분된 기획서 섹션만을 분석해 기술 관점의 핵심 허점을 파악합니다.
분석 관점:
- 제시된 기술 스택이 문제에 적합한가?
- LLM 사용이 이 기능에 필수적인가, 과용인가?
- 주어진 기간(MVP 일정) 내 구현 가능한가?
- 장애/환각/오류 케이스 처리 방안이 있는가?

출력: 기술적 핵심 허점 2~3개를 간결하게 서술. 추후 질문 생성에 활용됩니다."""


MENTOR_ANALYZE_PROMPT = """당신은 예리한 멘토입니다.

역할: 배분된 기획서 섹션만을 분석해 구조적 관점의 핵심 허점을 파악합니다.
분석 관점:
- 한 줄 서비스 정의와 핵심 기능이 논리적으로 연결되는가?
- 문제 정의와 해결책 간 인과 관계가 명확한가?
- MVP 범위가 검증 목표에 비해 적절한가?
- 타겟 사용자와 제공 가치가 구체적으로 연결되는가?

출력: 구조적 핵심 허점 2~3개를 간결하게 서술. 추후 질문 생성에 활용됩니다."""
```

- [ ] **Step 3: investor/cto/mentor 질문 생성 프롬프트 간결화**

기존 3개 프롬프트의 `출력:` 줄을 아래로 교체 (각각):

```python
# INVESTOR_SYSTEM_PROMPT 출력 줄 교체
출력: 질문 1개를 한국어로 작성한다.
규칙: 1~2문장 이내. 전문용어는 괄호로 한글 설명 추가. 수치나 구체적 예시를 요구할 것.
나쁜 예: "수익 모델에 대해 설명해주세요."
좋은 예: "구독형(월정액) 전환 없이 초기 무료 사용자만 모았을 때, 6개월 후 서버 비용을 감당할 현금 흐름 계획은 무엇입니까?"

# CTO_SYSTEM_PROMPT 출력 줄 교체
출력: 질문 1개를 한국어로 작성한다.
규칙: 1~2문장 이내. 기술 용어는 괄호로 설명. 구체적인 구현 방법이나 수치를 요구할 것.
나쁜 예: "기술 구현이 가능한가요?"
좋은 예: "Whisper STT(음성→텍스트 변환)의 실시간 지연시간(latency)이 평균 2초 이상인데, 실시간 교정 UX를 어떻게 구현할 계획입니까?"

# MENTOR_SYSTEM_PROMPT 출력 줄 교체
출력: 질문 1개를 한국어로 작성한다.
규칙: 1~2문장 이내. 논리 모순이나 빠진 전제를 직접 지적할 것.
나쁜 예: "MVP 범위가 적절한가요?"
좋은 예: "'AI 대화 파트너'와 '발음 교정'은 별개 기능인데, 6개월 MVP에 둘 다 넣으면 어느 쪽도 제대로 검증이 안 됩니다. 첫 번째 MVP에서 버려야 할 기능은 무엇입니까?"
```

- [ ] **Step 4: SYSTEM_PROMPTS 딕셔너리 업데이트**

기존 `SYSTEM_PROMPTS` 딕셔너리에 analyze 프롬프트 3개 추가:

```python
SYSTEM_PROMPTS = {
    "orchestrator":       ORCHESTRATOR_SYSTEM_PROMPT,
    "investor":           INVESTOR_SYSTEM_PROMPT,
    "cto":                CTO_SYSTEM_PROMPT,
    "mentor":             MENTOR_SYSTEM_PROMPT,
    "reporter":           REPORTER_SYSTEM_PROMPT,
    "investor_analyze":   INVESTOR_ANALYZE_PROMPT,
    "cto_analyze":        CTO_ANALYZE_PROMPT,
    "mentor_analyze":     MENTOR_ANALYZE_PROMPT,
}
```

- [ ] **Step 5: 기존 테스트 통과 확인**

```bash
pytest tests/ -v
```

Expected: 전체 통과 (prompts.py 변경은 기존 테스트에 영향 없음)

- [ ] **Step 6: Commit**

```bash
git add backend/prompts.py
git commit -m "feat(react): update prompts — section distribution, analyze prompts, concise question format"
```

---

### Task 3: orchestrator_node — 섹션 배분 출력 추가

**Files:**
- Modify: `backend/schemas.py:8-15` (OrchestratorPlan 확장)
- Modify: `backend/nodes.py:32-54` (orchestrator_node)
- Test: `tests/test_nodes_react.py` (신규)

- [ ] **Step 1: 테스트 파일 생성 (실패할 테스트)**

`tests/test_nodes_react.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


SAMPLE_STATE = {
    "sections": {
        "1. 서비스 개요": "AI 영어 스피킹 코치 앱",
        "2. 문제 정의": "스피킹 연습 기회 부족",
        "3. 핵심 기능": "실시간 발음 교정, AI 대화",
        "4. 기술 구현": "Whisper STT, GPT-4, 6개월 MVP",
        "5. 수익 모델": "초기 무료, 추후 프리미엄",
        "6. 시장 분석": "MZ세대 자기계발 수요",
    },
    "messages": [],
    "round": 0,
    "persona_outputs": [],
    "final_report": "",
    "orchestrator_plan": [],
    "sections_by_persona": {},
    "persona_findings": [],
    "review_count": 0,
    "orchestrator_request": {},
}


def test_orchestrator_node_returns_sections_by_persona():
    """orchestrator_node가 sections_by_persona를 반환하는지 확인."""
    mock_plan = MagicMock()
    mock_plan.rounds = []
    mock_plan.sections_by_persona = {
        "investor": ["5. 수익 모델", "6. 시장 분석"],
        "cto": ["3. 핵심 기능", "4. 기술 구현"],
        "mentor": ["1. 서비스 개요", "2. 문제 정의"],
    }

    async def run():
        with patch("backend.nodes._bound_orchestrator") as mock_llm:
            mock_llm.ainvoke = AsyncMock(return_value=mock_plan)
            from backend.nodes import orchestrator_node
            result = await orchestrator_node(SAMPLE_STATE)
        assert "sections_by_persona" in result
        assert "investor" in result["sections_by_persona"]
        # 섹션 내용(content)이 채워져 있는지 확인
        investor_sections = result["sections_by_persona"]["investor"]
        assert isinstance(investor_sections, dict)
        # 섹션 제목이 key, 내용이 value
        for title in investor_sections:
            assert title in SAMPLE_STATE["sections"]

    import asyncio
    asyncio.run(run())
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_nodes_react.py::test_orchestrator_node_returns_sections_by_persona -v
```

Expected: FAIL

- [ ] **Step 3: OrchestratorPlan 스키마 확장**

`backend/schemas.py`의 `OrchestratorPlan` 클래스를 아래로 교체:

```python
class OrchestratorPlan(BaseModel):
    rounds: list[OrchestratorRound]
    sections_by_persona: dict[str, list[str]]
    # {"investor": ["5. 수익 모델", "6. 시장 분석"], "cto": [...], "mentor": [...]}
```

- [ ] **Step 4: orchestrator_node 수정**

`backend/nodes.py`의 `orchestrator_node` 함수를 아래로 교체:

```python
# 모듈 상단에 추가 (llm 선언 아래)
_bound_orchestrator = llm.with_structured_output(OrchestratorPlan)


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
        # sections_by_persona: 섹션 제목 목록 → {제목: 내용} 딕셔너리로 변환
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
```

- [ ] **Step 5: 기존 참조 수정**

`backend/nodes.py` 상단의 `structured_llm = llm.with_structured_output(OrchestratorPlan)` 라인이 있으면 삭제 (위에서 `_bound_orchestrator`로 대체).

- [ ] **Step 6: 테스트 통과 확인**

```bash
pytest tests/test_nodes_react.py::test_orchestrator_node_returns_sections_by_persona tests/test_schemas.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/schemas.py backend/nodes.py tests/test_nodes_react.py
git commit -m "feat(react): orchestrator returns sections_by_persona for sub-agent dispatch"
```

---

### Task 4: analyze 노드 3개 구현 (investor/cto/mentor_analyze)

**Files:**
- Modify: `backend/nodes.py` (3개 analyze 노드 추가)
- Test: `tests/test_nodes_react.py`

- [ ] **Step 1: 테스트 추가**

`tests/test_nodes_react.py`에 아래 추가:

```python
def test_investor_analyze_node_uses_assigned_sections():
    """investor_analyze_node가 배분된 섹션만 사용하고 findings를 반환하는지 확인."""
    state = {
        **SAMPLE_STATE,
        "sections_by_persona": {
            "investor": {"5. 수익 모델": "초기 무료, 추후 프리미엄"},
        },
        "orchestrator_request": {},
    }

    async def run():
        with patch("backend.nodes.llm") as mock_llm:
            mock_msg = MagicMock()
            mock_msg.content = "수익화 시점이 불명확하고 전환율 근거가 없다."
            mock_chunks = [mock_msg]

            async def fake_astream(*args, **kwargs):
                for c in mock_chunks:
                    yield c

            mock_llm.astream = fake_astream
            from backend.nodes import investor_analyze_node
            result = await investor_analyze_node(state)

        assert "persona_findings" in result
        assert len(result["persona_findings"]) == 1
        finding = result["persona_findings"][0]
        assert finding["persona"] == "investor"
        assert len(finding["findings"]) > 0
        assert finding["round"] == 0

    import asyncio
    asyncio.run(run())


def test_analyze_node_includes_followup_request_when_present():
    """orchestrator_request가 있으면 프롬프트에 포함되는지 확인 (findings에 반영)."""
    state = {
        **SAMPLE_STATE,
        "sections_by_persona": {
            "investor": {"5. 수익 모델": "초기 무료"},
        },
        "orchestrator_request": {"investor": "Unit Economics를 구체적으로 분석해줘"},
    }

    async def run():
        with patch("backend.nodes.llm") as mock_llm:
            captured = {}

            async def fake_astream(messages, *args, **kwargs):
                # HumanMessage 내용에 follow-up 요청이 포함됐는지 캡처
                captured["prompt"] = messages[-1].content
                mock_msg = MagicMock()
                mock_msg.content = "Unit Economics 근거 없음."
                yield mock_msg

            mock_llm.astream = fake_astream
            from backend.nodes import investor_analyze_node
            await investor_analyze_node(state)

        assert "Unit Economics" in captured["prompt"]

    import asyncio
    asyncio.run(run())
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_nodes_react.py -k "analyze" -v
```

Expected: FAIL (investor_analyze_node 없음)

- [ ] **Step 3: analyze 노드 구현**

`backend/nodes.py`에서 `_run_persona` 함수 위에 아래 추가:

```python
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

    messages = [
        SystemMessage(content=SYSTEM_PROMPTS[f"{persona}_analyze"]),
        HumanMessage(
            content=(
                f"=== 분석 대상 섹션 ===\n{sections_text}"
                f"{follow_up_block}\n\n"
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
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_nodes_react.py -k "analyze" -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/nodes.py tests/test_nodes_react.py
git commit -m "feat(react): add investor/cto/mentor analyze nodes for sub-agent section analysis"
```

---

### Task 5: orchestrator_review_node — ReAct 검토 루프

**Files:**
- Modify: `backend/nodes.py` (orchestrator_review_node 추가)
- Test: `tests/test_nodes_react.py`

- [ ] **Step 1: 테스트 추가**

`tests/test_nodes_react.py`에 아래 추가:

```python
def test_orchestrator_review_returns_sufficient_when_findings_complete():
    """3개 페르소나 findings가 모두 있으면 is_sufficient=True를 반환하는지 확인."""
    from backend.schemas import OrchestratorReview

    state = {
        **SAMPLE_STATE,
        "round": 0,
        "persona_findings": [
            {"persona": "investor", "findings": "수익화 시점 불명확.", "round": 0},
            {"persona": "cto", "findings": "6개월 MVP 비현실적.", "round": 0},
            {"persona": "mentor", "findings": "MVP 범위 과대.", "round": 0},
        ],
        "review_count": 0,
    }

    mock_review = OrchestratorReview(is_sufficient=True, follow_up_requests={})

    async def run():
        with patch("backend.nodes._bound_review") as mock_llm:
            mock_llm.ainvoke = AsyncMock(return_value=mock_review)
            from backend.nodes import orchestrator_review_node
            result = await orchestrator_review_node(state)

        assert result["review_count"] == 1
        # is_sufficient=True이면 orchestrator_request가 비어야 함
        assert result["orchestrator_request"] == {}

    import asyncio
    asyncio.run(run())


def test_orchestrator_review_returns_followup_when_insufficient():
    """findings가 부족하면 follow_up_requests를 반환하는지 확인."""
    from backend.schemas import OrchestratorReview

    state = {
        **SAMPLE_STATE,
        "round": 0,
        "persona_findings": [
            {"persona": "investor", "findings": "수익모델 분석 필요.", "round": 0},
        ],
        "review_count": 0,
    }

    mock_review = OrchestratorReview(
        is_sufficient=False,
        follow_up_requests={"investor": "Unit Economics 수치 포함해서 재분석해줘"},
    )

    async def run():
        with patch("backend.nodes._bound_review") as mock_llm:
            mock_llm.ainvoke = AsyncMock(return_value=mock_review)
            from backend.nodes import orchestrator_review_node
            result = await orchestrator_review_node(state)

        assert result["review_count"] == 1
        assert "investor" in result["orchestrator_request"]

    import asyncio
    asyncio.run(run())
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_nodes_react.py -k "review" -v
```

Expected: FAIL

- [ ] **Step 3: orchestrator_review_node 구현**

`backend/nodes.py`에 추가:

```python
# 모듈 상단 (llm 선언 아래)
_bound_review = llm.with_structured_output(OrchestratorReview)


async def orchestrator_review_node(state: PlannerState) -> dict:
    """현재 라운드 persona_findings를 검토. 충분하면 통과, 부족하면 follow_up_requests 반환."""
    current_round = state["round"]
    findings_this_round = [
        f for f in state.get("persona_findings", [])
        if f["round"] == current_round
    ]

    findings_text = "\n\n".join(
        f"[{f['persona']}]\n{f['findings']}" for f in findings_this_round
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
```

- [ ] **Step 4: OrchestratorReview import 추가**

`backend/nodes.py` 상단 imports에 추가:

```python
from backend.schemas import PlannerState, OrchestratorPlan, OrchestratorReview
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/test_nodes_react.py -v
```

Expected: 전체 통과

- [ ] **Step 6: Commit**

```bash
git add backend/nodes.py tests/test_nodes_react.py
git commit -m "feat(react): add orchestrator_review_node with ReAct loop quality check"
```

---

### Task 6: _run_persona 수정 — findings 기반 질문 생성

**Files:**
- Modify: `backend/nodes.py:57-120` (`_run_persona` 함수)

- [ ] **Step 1: 테스트 추가**

`tests/test_nodes_react.py`에 아래 추가:

```python
def test_run_persona_uses_findings_in_prompt():
    """_run_persona가 persona_findings를 질문 생성에 활용하는지 확인."""
    state = {
        **SAMPLE_STATE,
        "round": 0,
        "orchestrator_plan": [
            {"persona": "investor", "section": "수익모델", "focus": "수익화 시점 불명확"},
        ],
        "persona_findings": [
            {"persona": "investor", "findings": "수익화 시점이 불명확하고 Unit Economics 근거 없음.", "round": 0},
        ],
    }

    async def run():
        captured = {}

        with patch("backend.nodes.llm") as mock_llm, \
             patch("backend.nodes._bound_llm") as mock_bound:

            async def fake_astream(messages, *args, **kwargs):
                captured["prompt"] = messages[-1].content
                mock_msg = MagicMock()
                mock_msg.content = "6개월 후 Unit Economics는 어떻게 됩니까?"
                yield mock_msg

            mock_llm.astream = fake_astream
            mock_bound.ainvoke = AsyncMock(return_value=MagicMock(tool_calls=[]))

            from backend.nodes import _run_persona
            result = await _run_persona("investor", state)

        # findings가 프롬프트에 포함됐는지 확인
        assert "수익화 시점이 불명확" in captured["prompt"]
        assert result["persona_outputs"][0]["question"] != ""

    import asyncio
    asyncio.run(run())
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_nodes_react.py::test_run_persona_uses_findings_in_prompt -v
```

Expected: FAIL (findings가 프롬프트에 없음)

- [ ] **Step 3: _run_persona 수정**

`backend/nodes.py`의 `_run_persona` 함수에서 `base_messages` 구성 부분을 아래로 교체:

```python
    # 현재 라운드의 이 페르소나 findings 조회
    current_findings = next(
        (f["findings"] for f in state.get("persona_findings", [])
         if f["persona"] == persona and f["round"] == state["round"]),
        ""
    )
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
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_nodes_react.py -v && pytest tests/ -v
```

Expected: 전체 통과

- [ ] **Step 5: Commit**

```bash
git add backend/nodes.py tests/test_nodes_react.py
git commit -m "feat(react): _run_persona uses persona_findings for grounded question generation"
```

---

### Task 7: graph.py — ReAct 루프 조건부 엣지 구성

**Files:**
- Modify: `backend/graph.py`
- Test: `tests/test_nodes_react.py`

- [ ] **Step 1: ReAct 라우팅 조건 테스트 추가**

`tests/test_nodes_react.py`에 아래 추가:

```python
def test_should_continue_react_returns_continue_when_insufficient_and_under_limit():
    from backend.graph import _should_continue_react
    state = {
        **SAMPLE_STATE,
        "review_count": 1,
        "orchestrator_request": {"investor": "더 분석해줘"},
    }
    result = _should_continue_react(state)
    assert result == "continue"


def test_should_continue_react_returns_done_when_max_iterations():
    from backend.graph import _should_continue_react
    state = {
        **SAMPLE_STATE,
        "review_count": 2,
        "orchestrator_request": {"investor": "더 분석해줘"},
    }
    result = _should_continue_react(state)
    assert result == "done"


def test_should_continue_react_returns_done_when_sufficient():
    from backend.graph import _should_continue_react
    state = {
        **SAMPLE_STATE,
        "review_count": 1,
        "orchestrator_request": {},
    }
    result = _should_continue_react(state)
    assert result == "done"
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_nodes_react.py -k "should_continue" -v
```

Expected: FAIL

- [ ] **Step 3: graph.py 전체 교체**

```python
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

_FIRST_PERSONAS = {"investor", "cto", "mentor"}
_ALL_PERSONAS = {"investor", "cto", "mentor"}


def _should_continue_react(state: PlannerState) -> Literal["continue", "done"]:
    """ReAct 루프 계속 여부 판단. 최대 2회 또는 sufficient이면 종료."""
    if state.get("review_count", 0) >= MAX_REACT_ITERATIONS:
        return "done"
    if not state.get("orchestrator_request"):
        return "done"
    return "continue"


def _route_after_orchestrator(state: PlannerState) -> Literal["investor", "cto", "mentor"]:
    plan = state.get("orchestrator_plan", [])
    if plan:
        persona = plan[0]["persona"]
        if persona in _FIRST_PERSONAS:
            return persona
    return "investor"


def _route_after_review(state: PlannerState) -> Literal["investor_analyze", "cto_analyze", "mentor_analyze", "question"]:
    """ReAct: 보완 요청된 페르소나가 있으면 해당 분석 노드로, 없으면 질문 생성으로."""
    request = state.get("orchestrator_request", {})
    if request:
        # 보완 요청 중 첫 번째 페르소나 분석 노드로 라우팅
        first_persona = next(iter(request))
        return f"{first_persona}_analyze"
    return "question"


def _route_to_question_persona(state: PlannerState) -> Literal["investor", "cto", "mentor"]:
    """현재 라운드의 질문 생성 페르소나 결정."""
    plan = state.get("orchestrator_plan", [])
    if plan and state["round"] < len(plan):
        persona = plan[state["round"]]["persona"]
        if persona in _ALL_PERSONAS:
            return persona
    return PERSONA_ORDER[state["round"] % len(PERSONA_ORDER)]


def _route_after_human(state: PlannerState) -> Literal["investor", "cto", "mentor", "reporter"]:
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

    # ReAct 루프: review → (continue → 해당 analyze 노드) or (done → question 라우팅)
    builder.add_conditional_edges(
        "orchestrator_review",
        _should_continue_react,
        {
            "continue": "investor_analyze",  # 보완 필요 시 첫 번째 페르소나 재분석
            "done": "investor",              # 충분 시 질문 생성 (라운드별 라우팅은 아래에서)
        },
    )
    # NOTE: "done" 분기는 실제로 _route_to_question_persona로 라우팅이 필요.
    # LangGraph conditional edge는 단일 함수만 받으므로,
    # "done" 케이스를 아래 별도 라우팅 노드로 처리:
    # orchestrator_review → [done] → question_router → investor/cto/mentor

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
```

> **구현 노트:** `orchestrator_review`의 "done" 분기 이후 라운드별 페르소나 라우팅은 단순화를 위해 `investor` 노드로 직접 연결했다. 실제로는 `_route_to_question_persona`로 동적 라우팅이 필요하다. Task 7 완료 후 이 부분을 별도 `question_router` 노드로 분리하는 것을 권장한다.

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_nodes_react.py -v
pytest tests/ -v
```

Expected: 전체 통과

- [ ] **Step 5: Commit**

```bash
git add backend/graph.py tests/test_nodes_react.py
git commit -m "feat(react): ReAct loop graph with conditional edges for sub-agent re-analysis"
```

---

## 주의사항 및 알려진 한계

### ReAct 루프 최대 횟수
`MAX_REACT_ITERATIONS = 2`로 고정. 무한 루프 방지. 필요 시 `backend/config.py`에 `REACT_MAX_ITER = int(os.getenv("REACT_MAX_ITER", "2"))`로 환경변수화 가능.

### 보완 요청 라우팅 단순화
현재 구현에서 `orchestrator_request`에 여러 페르소나가 있어도 첫 번째 페르소나만 순차 재실행한다. 완전한 구현은 모든 요청된 페르소나를 재실행해야 하며, LangGraph `Send` API를 사용한 병렬 팬아웃으로 구현 가능하다.

### question_router 미구현
Task 7에서 `orchestrator_review → done → investor/cto/mentor` 라우팅이 단순화됐다. `round`에 따른 정확한 페르소나 라우팅은 별도 `question_router` 노드 추가 필요.

### 기존 RAG + Tool Calling 유지
`_run_persona`의 RAG 블록과 Tool Calling 로직은 그대로 유지된다. findings 블록이 추가되는 것일 뿐 기존 기능을 대체하지 않는다.
