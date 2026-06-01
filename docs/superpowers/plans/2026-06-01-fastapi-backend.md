# 기획서 검증 에이전트 FastAPI Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** solar-pro2 기반 다중 페르소나(투자자/CTO/멘토) 압박 질문 생성 FastAPI 백엔드를 구현한다.

**Architecture:** LangGraph StateGraph로 오케스트레이터-페르소나 패턴을 구현한다. `interrupt()`로 사용자 입력 대기 → `Command(resume=...)` 재개 방식의 멀티턴 대화를 관리하고, InMemorySaver로 세션 체크포인팅한다. FastAPI SSE(Server-Sent Events)로 LLM 응답을 실시간 스트리밍한다.

**Tech Stack:** Python 3.13, FastAPI, LangGraph 1.2.2, LangChain 1.3.2, solar-pro2 (langchain-upstage 0.7.7), Pydantic v2, pytest, python-dotenv

---

## 파일 구조

```
backend/
  __init__.py         빈 파일 (패키지 선언)
  config.py           env 설정 (UPSTAGE_API_KEY 로드)
  schemas.py          Pydantic 모델 (PlannerState, API 요청/응답, PersonaOutput)
  prompts.py          페르소나별 시스템 프롬프트 상수
  parser.py           TXT 파일 → 섹션 dict 파싱 (순수 함수)
  nodes.py            LangGraph 노드 함수 (investor, cto, mentor, reporter, human)
  graph.py            StateGraph 정의 + InMemorySaver 컴파일
  main.py             FastAPI 앱 + 엔드포인트 (POST /upload, POST /chat, GET /health)

tests/
  __init__.py
  test_parser.py      parser.py 유닛 테스트
  test_schemas.py     Pydantic 스키마 검증 테스트

frontend/
  app.py              (기존) Streamlit UI → API 연동으로 업데이트

.env.example          API 키 템플릿
```

## 대화 흐름 (LangGraph 그래프)

```
POST /upload → [START] → investor_node → human_node (interrupt!) → 스트리밍 반환
POST /chat   → Command(resume=답변) → human_node 재개 → round 증가
               round%3==0 → investor_node
               round%3==1 → cto_node
               round%3==2 → mentor_node
               round>=6   → reporter_node → [END]
```

라운드 6회 (투자자→CTO→멘토→투자자→CTO→멘토) 후 최종 리포트.

---

## Task 1: 패키지 설치 및 프로젝트 셋업

**Files:**
- Create: `backend/__init__.py`
- Create: `.env.example`
- Create: `backend/config.py`

- [ ] **Step 1: 필요 패키지 설치**

```bash
pip install fastapi pytest pytest-asyncio
```

Expected output: `Successfully installed fastapi-...`

- [ ] **Step 2: 설치 확인**

```bash
python -c "import fastapi, pytest; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: `backend/__init__.py` 생성**

```python
```
(빈 파일)

- [ ] **Step 4: `.env.example` 생성**

```
UPSTAGE_API_KEY=your_upstage_api_key_here
```

- [ ] **Step 5: `.env` 파일 생성 (실제 키 입력, gitignore 대상)**

`.gitignore`에 `.env` 추가 확인 후:
```
UPSTAGE_API_KEY=실제_키_입력
```

- [ ] **Step 6: `backend/config.py` 작성**

```python
from dotenv import load_dotenv
import os

load_dotenv()

UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY", "")
MODEL_NAME = "solar-pro2"
MAX_ROUNDS = 6
PERSONA_ORDER = ["investor", "cto", "mentor"]
```

- [ ] **Step 7: 커밋**

```bash
git add backend/__init__.py backend/config.py .env.example .gitignore
git commit -m "feat: backend project setup and config"
```

---

## Task 2: TXT 섹션 파서 (TDD)

**Files:**
- Create: `backend/parser.py`
- Create: `tests/__init__.py`
- Create: `tests/test_parser.py`

- [ ] **Step 1: 테스트 먼저 작성 (`tests/test_parser.py`)**

```python
from backend.parser import parse_sections

SAMPLE_TXT = """[13조] 프로젝트 기획서
1. 문제 정의 및 프로젝트 개요

프로젝트 한 줄 정의
AI 심사위원 챗봇

2. 사용자 및 Agent 설계

타깃 사용자 페르소나
SW마에스트로 연수생

3. 핵심 기능 및 사용자 흐름

주요 사용자 시나리오
기획서 업로드 후 압박 질문 수신

4. 기술 구현 설계

기술 스택
Python, LangGraph

5. 성과 평가 및 실행 계획

성공 지표
유효 질문 5개 이상
"""

def test_parse_returns_dict():
    result = parse_sections(SAMPLE_TXT)
    assert isinstance(result, dict)

def test_parse_extracts_five_sections():
    result = parse_sections(SAMPLE_TXT)
    assert len(result) == 5

def test_parse_section_keys():
    result = parse_sections(SAMPLE_TXT)
    assert "1. 문제 정의 및 프로젝트 개요" in result
    assert "2. 사용자 및 Agent 설계" in result
    assert "3. 핵심 기능 및 사용자 흐름" in result
    assert "4. 기술 구현 설계" in result
    assert "5. 성과 평가 및 실행 계획" in result

def test_parse_section_content_not_empty():
    result = parse_sections(SAMPLE_TXT)
    for key, value in result.items():
        assert len(value.strip()) > 0, f"섹션 '{key}' 내용이 비어 있음"

def test_parse_empty_string():
    result = parse_sections("")
    assert result == {}

def test_parse_no_numbered_sections():
    result = parse_sections("섹션 구분 없는 텍스트입니다.")
    assert result == {"전체": "섹션 구분 없는 텍스트입니다."}
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
pytest tests/test_parser.py -v
```

Expected: `ModuleNotFoundError: No module named 'backend.parser'`

- [ ] **Step 3: `backend/parser.py` 구현**

```python
import re
from typing import Optional

def parse_sections(text: str) -> dict[str, str]:
    """TXT 기획서를 번호 섹션 단위로 파싱한다."""
    if not text.strip():
        return {}

    # "숫자. 제목" 패턴으로 섹션 분리
    pattern = re.compile(r"^(\d+\.\s+[^\n]+)", re.MULTILINE)
    matches = list(pattern.finditer(text))

    if not matches:
        return {"전체": text.strip()}

    sections = {}
    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        sections[title] = content

    return sections
```

- [ ] **Step 4: 테스트 실행 (통과 확인)**

```bash
pytest tests/test_parser.py -v
```

Expected: `6 passed`

- [ ] **Step 5: 커밋**

```bash
git add backend/parser.py tests/__init__.py tests/test_parser.py
git commit -m "feat: TXT section parser with tests"
```

---

## Task 3: Pydantic 스키마 정의

**Files:**
- Create: `backend/schemas.py`
- Create: `tests/test_schemas.py`

- [ ] **Step 1: 테스트 먼저 작성 (`tests/test_schemas.py`)**

```python
from backend.schemas import UploadResponse, ChatRequest, ChatEvent, FinalReport

def test_upload_response_has_thread_id_and_persona():
    resp = UploadResponse(thread_id="abc-123", first_persona="investor")
    assert resp.thread_id == "abc-123"
    assert resp.first_persona == "investor"

def test_chat_request_requires_thread_id_and_message():
    req = ChatRequest(thread_id="abc-123", message="시장 차별화 전략은 RAG 도입입니다.")
    assert req.thread_id == "abc-123"
    assert req.message == "시장 차별화 전략은 RAG 도입입니다."

def test_chat_event_token():
    event = ChatEvent(token="안녕", node="investor", done=False, is_final=False)
    assert event.token == "안녕"
    assert event.done is False

def test_chat_event_done():
    event = ChatEvent(token="", node="", done=True, is_final=False)
    assert event.done is True

def test_final_report_risk_levels():
    report = FinalReport(
        summary="전반적으로 양호",
        weaknesses=[
            {"section": "기술스택", "issue": "LLM 필요성 불분명", "risk": "상", "suggestion": "Use case 재정의 필요"}
        ]
    )
    assert report.weaknesses[0]["risk"] == "상"
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
pytest tests/test_schemas.py -v
```

Expected: `ModuleNotFoundError: No module named 'backend.schemas'`

- [ ] **Step 3: `backend/schemas.py` 구현**

```python
from pydantic import BaseModel
from typing import Annotated, Any
import operator
from typing_extensions import TypedDict


# ── LangGraph State ──────────────────────────────────────────
class PlannerState(TypedDict):
    sections: dict[str, str]
    messages: Annotated[list[dict], operator.add]
    round: int
    persona_outputs: Annotated[list[dict], operator.add]
    final_report: str


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
pytest tests/test_schemas.py -v
```

Expected: `5 passed`

- [ ] **Step 5: 커밋**

```bash
git add backend/schemas.py tests/test_schemas.py
git commit -m "feat: Pydantic schemas for API and LangGraph state"
```

---

## Task 4: 페르소나 시스템 프롬프트

**Files:**
- Create: `backend/prompts.py`

- [ ] **Step 1: `backend/prompts.py` 작성**

```python
INVESTOR_SYSTEM_PROMPT = """당신은 깐깐한 스타트업 투자자입니다.

역할: 시장성·차별성·수익/지속가능성 관점에서 기획서의 허점을 날카롭게 지적합니다.
평가 기준:
- 이미 시장에 유사 서비스가 있는가?
- 사용자가 돈/시간을 쓸 만큼 충분히 아픈 문제인가?
- 왜 지금 이 팀이 이 문제를 풀어야 하는가?
- 수익 모델과 지속가능성이 명확한가?

말투: 직설적이고 회피를 허용하지 않는다. 단순 비난이 아니라 "왜 그게 약점인지 + 어떤 방향으로 보완할 수 있는지"를 함께 제시한다.
금지사항: 근거 없이 시장 수치를 단정짓지 않는다. 불확실한 외부 사실은 "확인이 필요한 가정"으로 표기한다.
출력: 질문 1개만 한국어로 출력한다. 부연 설명 없이 질문 본문만 작성한다."""

CTO_SYSTEM_PROMPT = """당신은 냉철한 CTO입니다.

역할: 기술 실현 가능성·아키텍처·LLM 적정성 관점에서 기획서의 기술적 허점을 지적합니다.
평가 기준:
- 이 기간 안에 구현 가능한가?
- LLM이 이 기능에 정말 필요한가? 과/오용은 아닌가?
- 실패/환각 케이스는 어떻게 처리하는가?
- 기술 스택 선택이 문제 특성에 적합한가?

말투: 직설적이고 기술적 근거를 요구한다. "왜 그게 약점인지 + 어떤 방향으로 보완할 수 있는지"를 함께 제시한다.
금지사항: 근거 없이 기술 불가능을 단정짓지 않는다.
출력: 질문 1개만 한국어로 출력한다. 부연 설명 없이 질문 본문만 작성한다."""

MENTOR_SYSTEM_PROMPT = """당신은 예리한 멘토입니다.

역할: 논리 일관성·MVP 범위·우선순위 관점에서 기획서의 구조적 허점을 지적합니다.
평가 기준:
- 한 줄 정의와 핵심 기능이 일관성 있게 연결되는가?
- MVP가 너무 크거나 작지 않은가? 무엇을 버려야 하는가?
- 대상 사용자와 제공 가치가 명확하게 연결되는가?
- 문제 정의와 해결책이 논리적으로 연결되는가?

말투: 직설적이되 건설적이다. "왜 그게 약점인지 + 어떤 방향으로 보완할 수 있는지"를 함께 제시한다.
금지사항: 단순 비판 없이 보완 방향을 반드시 제시한다.
출력: 질문 1개만 한국어로 출력한다. 부연 설명 없이 질문 본문만 작성한다."""

REPORTER_SYSTEM_PROMPT = """당신은 기획서 분석 전문가입니다.

역할: 지금까지의 대화(압박 질문과 사용자 답변)를 바탕으로 기획서의 종합 피드백 리포트를 작성합니다.

출력 형식 (반드시 아래 구조로 작성):
## 종합 피드백

**전반적 평가**: (2~3문장 요약)

## 허점 분석

| 섹션 | 핵심 허점 | 위험도 | 보완 제안 |
|------|-----------|--------|-----------|
| (섹션명) | (허점 설명) | 상/중/하 | (구체적 방향) |

## 마무리 한마디

(발표자에게 전하는 핵심 조언 1~2문장)"""


PERSONA_LABELS = {
    "investor": ("💼", "깐깐한 투자자"),
    "cto":      ("💻", "냉철한 CTO"),
    "mentor":   ("🦉", "예리한 멘토"),
    "reporter": ("🤖", "오케스트레이터"),
}

SYSTEM_PROMPTS = {
    "investor": INVESTOR_SYSTEM_PROMPT,
    "cto":      CTO_SYSTEM_PROMPT,
    "mentor":   MENTOR_SYSTEM_PROMPT,
    "reporter": REPORTER_SYSTEM_PROMPT,
}
```

- [ ] **Step 2: 프롬프트 임포트 확인**

```bash
python -c "from backend.prompts import SYSTEM_PROMPTS, PERSONA_LABELS; print(list(SYSTEM_PROMPTS.keys()))"
```

Expected: `['investor', 'cto', 'mentor', 'reporter']`

- [ ] **Step 3: 커밋**

```bash
git add backend/prompts.py
git commit -m "feat: persona system prompts (investor, CTO, mentor, reporter)"
```

---

## Task 5: LangGraph 노드 함수

**Files:**
- Create: `backend/nodes.py`

- [ ] **Step 1: `backend/nodes.py` 작성**

```python
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import interrupt

from backend.config import MODEL_NAME
from backend.prompts import SYSTEM_PROMPTS
from backend.schemas import PlannerState

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


async def _run_persona(persona: str, state: PlannerState) -> dict:
    """공통 페르소나 실행 로직."""
    context = _format_context(state)
    history = _format_history(state)

    messages = [
        SystemMessage(content=SYSTEM_PROMPTS[persona]),
        HumanMessage(content=f"{context}\n\n{history}\n\n위 기획서와 대화 이력을 바탕으로 날카로운 압박 질문 1개를 생성하세요."),
    ]
    response = await llm.ainvoke(messages)
    return {
        "messages": [{"role": "assistant", "name": persona, "content": response.content}],
        "persona_outputs": [{"persona": persona, "question": response.content, "round": state["round"]}],
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
    """모든 Q&A를 바탕으로 종합 리포트 생성."""
    context = _format_context(state)
    history = _format_history(state)

    messages = [
        SystemMessage(content=SYSTEM_PROMPTS["reporter"]),
        HumanMessage(content=f"{context}\n\n{history}\n\n위 내용을 바탕으로 종합 피드백 리포트를 작성하세요."),
    ]
    response = await llm.ainvoke(messages)
    return {
        "messages": [{"role": "assistant", "name": "reporter", "content": response.content}],
        "final_report": response.content,
    }
```

- [ ] **Step 2: 노드 임포트 확인**

```bash
python -c "from backend.nodes import investor_node, cto_node, mentor_node, human_node, reporter_node; print('nodes OK')"
```

Expected: `nodes OK`

- [ ] **Step 3: 커밋**

```bash
git add backend/nodes.py
git commit -m "feat: LangGraph node functions (investor, cto, mentor, human, reporter)"
```

---

## Task 6: LangGraph 그래프 조립

**Files:**
- Create: `backend/graph.py`

- [ ] **Step 1: `backend/graph.py` 작성**

```python
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
```

- [ ] **Step 2: 그래프 구조 확인**

```bash
python -c "
from backend.graph import graph
print('nodes:', list(graph.nodes.keys()))
print('graph OK')
"
```

Expected: `nodes: ['__start__', 'investor', 'cto', 'mentor', 'human', 'reporter', '__end__']`

- [ ] **Step 3: 커밋**

```bash
git add backend/graph.py
git commit -m "feat: LangGraph StateGraph with interrupt-based human-in-the-loop"
```

---

## Task 7: FastAPI 앱 및 엔드포인트

**Files:**
- Create: `backend/main.py`

- [ ] **Step 1: `backend/main.py` 작성**

```python
import json
import uuid

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langgraph.types import Command

from backend.graph import graph
from backend.parser import parse_sections
from backend.schemas import UploadResponse, ChatRequest, ChatEvent
from backend.prompts import PERSONA_LABELS

app = FastAPI(title="기획서 검증 에이전트 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PERSONA_NODES = {"investor", "cto", "mentor", "reporter"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)):
    """TXT 기획서 업로드 → 파싱 → 첫 번째 투자자 질문 생성 준비."""
    if not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="TXT 파일만 지원합니다.")

    raw = (await file.read()).decode("utf-8")
    sections = parse_sections(raw)

    if not sections:
        raise HTTPException(status_code=400, detail="기획서 섹션을 파싱할 수 없습니다.")

    thread_id = str(uuid.uuid4())
    # 초기 상태를 그래프에 저장 (아직 실행하지 않음 - /chat/start에서 실행)
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "sections": sections,
        "messages": [],
        "round": 0,
        "persona_outputs": [],
        "final_report": "",
    }

    # 그래프를 첫 interrupt 지점까지 실행 (투자자 질문 생성 후 일시 정지)
    # 실제 스트리밍은 /chat/start에서 처리
    # 여기선 thread_id만 발급
    _ = initial_state  # 초기 상태는 /chat/start 첫 호출 시 전달

    return UploadResponse(thread_id=thread_id, first_persona="investor")


@app.post("/chat/start")
async def chat_start(thread_id: str, sections_json: str):
    """첫 번째 페르소나(투자자) 질문을 SSE 스트리밍으로 반환."""
    import json as _json
    sections = _json.loads(sections_json)
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "sections": sections,
        "messages": [],
        "round": 0,
        "persona_outputs": [],
        "final_report": "",
    }

    async def event_generator():
        async for chunk in graph.astream(
            initial_state, config, stream_mode="messages"
        ):
            msg, meta = chunk
            node = meta.get("langgraph_node", "")
            if node in PERSONA_NODES:
                content = getattr(msg, "content", "")
                if content:
                    event = ChatEvent(token=content, node=node, done=False)
                    yield f"data: {event.model_dump_json()}\n\n"

        # interrupt 지점에서 스트림 종료
        done_event = ChatEvent(token="", node="", done=True, is_final=False)
        yield f"data: {done_event.model_dump_json()}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/chat")
async def chat(req: ChatRequest):
    """사용자 답변 수신 → 다음 페르소나 질문 or 최종 리포트를 SSE 스트리밍으로 반환."""
    config = {"configurable": {"thread_id": req.thread_id}}
    state_snapshot = graph.get_state(config)

    if not state_snapshot.next:
        raise HTTPException(status_code=400, detail="이미 완료된 세션입니다.")

    async def event_generator():
        is_final = False
        async for chunk in graph.astream(
            Command(resume=req.message), config, stream_mode="messages"
        ):
            msg, meta = chunk
            node = meta.get("langgraph_node", "")
            if node in PERSONA_NODES:
                content = getattr(msg, "content", "")
                if content:
                    is_reporter = node == "reporter"
                    event = ChatEvent(token=content, node=node, done=False, is_final=is_reporter)
                    yield f"data: {event.model_dump_json()}\n\n"
                    if is_reporter:
                        is_final = True

        done_event = ChatEvent(token="", node="", done=True, is_final=is_final)
        yield f"data: {done_event.model_dump_json()}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

- [ ] **Step 2: 서버 기동 확인**

```bash
uvicorn backend.main:app --reload --port 8000
```

Expected: `INFO: Uvicorn running on http://127.0.0.1:8000`

- [ ] **Step 3: Health check 확인**

새 터미널에서:
```bash
curl http://localhost:8000/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 4: 서버 종료 후 커밋**

```bash
git add backend/main.py
git commit -m "feat: FastAPI endpoints with SSE streaming (upload, chat/start, chat)"
```

---

## Task 8: Streamlit 프론트엔드 API 연동

**Files:**
- Modify: `frontend/app.py`

- [ ] **Step 1: `frontend/app.py` 수정 — import 추가 및 상수 정의**

파일 상단의 import 블록을 다음으로 교체:

```python
import streamlit as st
import httpx
import json

API_BASE = "http://localhost:8000"

PERSONA_AVATAR = {
    "investor": "💼",
    "cto":      "💻",
    "mentor":   "🦉",
    "reporter": "🤖",
}
PERSONA_NAME = {
    "investor": "깐깐한 투자자",
    "cto":      "냉철한 CTO",
    "mentor":   "예리한 멘토",
    "reporter": "오케스트레이터",
}
```

- [ ] **Step 2: session_state 초기화 블록 교체**

기존 `if "page" not in st.session_state:` 블록을 다음으로 교체:

```python
if "page" not in st.session_state:
    st.session_state.page = "upload"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "sections_json" not in st.session_state:
    st.session_state.sections_json = None
if "is_done" not in st.session_state:
    st.session_state.is_done = False
```

- [ ] **Step 3: `render_upload_page()` 버튼 클릭 핸들러 교체**

기존 `if st.button("🚀 모의 심사 시작하기", ...)` 블록을:

```python
if st.button("🚀 모의 심사 시작하기", use_container_width=True):
    with st.spinner("기획서 분석 중..."):
        files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "text/plain")}
        resp = httpx.post(f"{API_BASE}/upload", files=files)
        if resp.status_code != 200:
            st.error(f"업로드 실패: {resp.text}")
        else:
            data = resp.json()
            st.session_state.thread_id = data["thread_id"]
            # 섹션 데이터는 /chat/start에 필요하므로 다시 파싱
            from backend.parser import parse_sections
            raw = uploaded_file.getvalue().decode("utf-8")
            import json as _json
            st.session_state.sections_json = _json.dumps(
                parse_sections(raw), ensure_ascii=False
            )
            st.session_state.page = "chat"
            st.session_state.messages = [
                {"role": "assistant", "name": "reporter",
                 "content": "기획서 파싱 완료. 지금부터 압박 질문을 시작합니다.",
                 "avatar": "🤖"}
            ]
            st.session_state.is_done = False
            st.rerun()
```

- [ ] **Step 4: `render_chat_page()` 채팅 입력 처리 교체**

기존 `if prompt := st.chat_input(...)` 블록을:

```python
if not st.session_state.is_done:
    if prompt := st.chat_input("답변을 입력해주세요..."):
        # 사용자 메시지 표시
        st.session_state.messages.append(
            {"role": "user", "content": prompt, "avatar": "👤"}
        )
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)

        # 첫 번째 질문이면 /chat/start, 이후는 /chat
        is_first = all(m["role"] != "assistant" or m.get("name") == "reporter"
                       for m in st.session_state.messages[1:])

        if is_first:
            url = f"{API_BASE}/chat/start"
            params = {"thread_id": st.session_state.thread_id,
                      "sections_json": st.session_state.sections_json}
            request = httpx.Request("POST", url, params=params)
        else:
            url = f"{API_BASE}/chat"
            request = httpx.Request(
                "POST", url,
                content=json.dumps({"thread_id": st.session_state.thread_id,
                                    "message": prompt}),
                headers={"content-type": "application/json"}
            )

        # SSE 스트리밍 수신
        current_node = None
        full_response = ""
        placeholder = None

        with httpx.Client(timeout=60) as client:
            with client.stream("POST", request.url,
                               params=request.url.params,
                               content=request.content,
                               headers=request.headers) as stream:
                for line in stream.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])

                    if event["done"]:
                        if placeholder:
                            placeholder.markdown(full_response)
                        if event.get("is_final"):
                            st.session_state.is_done = True
                        break

                    node = event["node"]
                    token = event["token"]

                    if node != current_node:
                        current_node = node
                        avatar = PERSONA_AVATAR.get(node, "🤖")
                        name = PERSONA_NAME.get(node, node)
                        full_response = ""
                        with st.chat_message("assistant", avatar=avatar):
                            st.caption(f"**{name}**")
                            placeholder = st.empty()

                    full_response += token
                    if placeholder:
                        placeholder.markdown(full_response + "▌")

        if full_response:
            st.session_state.messages.append({
                "role": "assistant",
                "name": current_node,
                "content": full_response,
                "avatar": PERSONA_AVATAR.get(current_node, "🤖"),
            })
        st.rerun()
else:
    st.info("심사가 완료되었습니다. 위의 종합 리포트를 확인하세요.")
```

- [ ] **Step 5: 통합 테스트 (수동)**

터미널 1:
```bash
uvicorn backend.main:app --reload --port 8000
```

터미널 2:
```bash
streamlit run frontend/app.py --server.port 8501
```

브라우저 `http://localhost:8501` 접속 → `[13조] 프로젝트 기획서.txt` 업로드 → 심사 시작

확인 항목:
- [ ] 업로드 성공 → 채팅 페이지 전환
- [ ] 투자자 질문이 스트리밍으로 출력됨
- [ ] 답변 입력 → CTO 질문 스트리밍 출력
- [ ] 6라운드 후 최종 리포트 출력
- [ ] "심사가 완료되었습니다" 메시지 표시

- [ ] **Step 6: 커밋**

```bash
git add frontend/app.py
git commit -m "feat: Streamlit frontend API integration with SSE streaming"
```

---

## Self-Review

### Spec 커버리지 체크

| 기획서 요구사항 | Task | 구현 여부 |
|----------------|------|-----------|
| TXT 업로드 및 파싱 | Task 2, 7 | ✅ |
| 3개 페르소나 압박 질문 생성 | Task 4, 5, 6 | ✅ |
| 순차형 멀티턴 대화 | Task 6 (interrupt) | ✅ |
| SSE 스트리밍 출력 | Task 7 | ✅ |
| 최종 리포트 (위험도+보완 제안) | Task 5 (reporter_node) | ✅ |
| 채팅 마지막 메시지로 리포트 | Task 7, 8 | ✅ |
| solar-pro2 단일 LLM | Task 5 (init_chat_model) | ✅ |
| 세션 내 메모리 유지 | Task 6 (InMemorySaver) | ✅ |
| 파싱 실패 예외 처리 | Task 7 (/upload 400 반환) | ✅ |

### 주의사항

- `UPSTAGE_API_KEY` 없으면 `init_chat_model` 호출 시 에러. `.env` 파일 반드시 생성.
- `InMemorySaver`는 서버 재시작 시 모든 세션 소멸. MVP 로컬 데모 용도로만 사용.
- `frontend/app.py`의 `/chat/start` 판별 로직(`is_first`)이 단순화되어 있음. 실제 운영 시에는 서버에 `round` 상태를 쿼리하는 방식으로 개선 권장.
