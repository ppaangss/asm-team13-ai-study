# Function Calling (외부 검색 Tool 연동) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** investor/cto/mentor 페르소나가 질문 생성 전 Tavily 웹 검색 도구를 LLM 판단 하에 호출해 실제 시장 데이터·경쟁사·기술 트렌드를 반영한 날카로운 질문을 생성한다.

**Architecture:** `backend/tools.py`에 `@tool` 데코레이터로 `web_search` 함수를 정의한다. `_run_persona`에서 `llm.bind_tools([web_search])`로 LLM이 스스로 검색 여부를 결정하게 한다. Tool call이 있으면 실행 후 결과를 messages에 주입, 없으면 직접 스트리밍한다. 최종 응답은 항상 `llm.astream()`으로 토큰 스트리밍한다.

**Tech Stack:** `tavily-python` (검색 API), `langchain-core` `@tool` 데코레이터, `langchain_core.messages.ToolMessage`, `solar-pro2` bind_tools

---

## File Structure

| 파일 | 변경 | 역할 |
|------|------|------|
| `backend/tools.py` | **신규 생성** | `web_search` tool 정의 (Tavily 래퍼) |
| `backend/config.py` | **수정** | `TAVILY_API_KEY` 추가 |
| `backend/prompts.py` | **수정** | investor/cto/mentor 프롬프트에 도구 사용 힌트 추가 |
| `backend/nodes.py` | **수정** | `_run_persona` → bind_tools + ToolMessage 루프 + astream |
| `tests/test_tools.py` | **신규 생성** | web_search tool 정의 및 실행 테스트 (Tavily mocked) |

---

### Task 1: 의존성 설치 및 TAVILY_API_KEY 설정

**Files:**
- Modify: `backend/config.py:1-18`

- [ ] **Step 1: tavily-python 설치**

```bash
pip install tavily-python
```

Expected: `Successfully installed tavily-python-X.X.X`

- [ ] **Step 2: .env에 TAVILY_API_KEY 추가**

`.env` 파일에 아래 줄 추가:
```
TAVILY_API_KEY=tvly-...실제키...
```

- [ ] **Step 3: config.py에 TAVILY_API_KEY 추가**

`backend/config.py` 전체를 아래로 교체:

```python
from dotenv import load_dotenv
import os

load_dotenv()

UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
MODEL_NAME = "solar-pro2"
MAX_ROUNDS = 6
PERSONA_ORDER = ["investor", "cto", "mentor"]

# RAG 설정
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "data/chroma_db")
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
EXAMPLES_DIR = os.getenv("EXAMPLES_DIR", "data/examples")

# LangSmith 트레이싱 (env var 로드 후 자동 활성화됨)
# LANGSMITH_TRACING, LANGSMITH_API_KEY, LANGSMITH_PROJECT 은 .env 에서 관리
```

- [ ] **Step 4: import 검증**

```bash
python -c "from backend.config import TAVILY_API_KEY; print('OK', bool(TAVILY_API_KEY))"
```

Expected: `OK True` (API 키가 있으면)

- [ ] **Step 5: Commit**

```bash
git add backend/config.py
git commit -m "feat(fc): add TAVILY_API_KEY to config"
```

---

### Task 2: backend/tools.py — web_search Tool 구현

**Files:**
- Create: `backend/tools.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: 실패할 테스트 작성**

`tests/test_tools.py`:

```python
import pytest
from unittest.mock import patch, MagicMock


def test_web_search_is_langchain_tool():
    from backend.tools import web_search
    # LangChain @tool은 .name, .description, .invoke 속성을 가진다
    assert hasattr(web_search, "name")
    assert hasattr(web_search, "description")
    assert hasattr(web_search, "invoke")
    assert web_search.name == "web_search"


def test_web_search_returns_string_on_success():
    fake_results = {
        "results": [
            {"title": "AI 시장 2024", "content": "AI 시장은 연 35% 성장 중입니다. 주요 플레이어는..."},
            {"title": "LLM 경쟁 현황", "content": "GPT-4, Claude 3, Gemini 등이 경쟁 중이며..."},
        ]
    }
    with patch("backend.tools.TavilyClient") as MockClient:
        instance = MockClient.return_value
        instance.search.return_value = fake_results
        from backend.tools import web_search
        result = web_search.invoke({"query": "AI 교육 시장 규모"})
    assert isinstance(result, str)
    assert "AI 시장 2024" in result
    assert "LLM 경쟁 현황" in result


def test_web_search_returns_fallback_when_no_results():
    with patch("backend.tools.TavilyClient") as MockClient:
        instance = MockClient.return_value
        instance.search.return_value = {"results": []}
        from backend.tools import web_search
        result = web_search.invoke({"query": "존재하지않는검색어xyz"})
    assert result == "검색 결과 없음"


def test_web_search_truncates_long_content():
    long_content = "A" * 1000
    fake_results = {"results": [{"title": "긴 문서", "content": long_content}]}
    with patch("backend.tools.TavilyClient") as MockClient:
        instance = MockClient.return_value
        instance.search.return_value = fake_results
        from backend.tools import web_search
        result = web_search.invoke({"query": "테스트"})
    # 콘텐츠는 300자로 잘려야 한다
    assert len(result) <= 400  # "[긴 문서] " + 300자 + 여유
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_tools.py -v
```

Expected: `ImportError: cannot import name 'web_search' from 'backend.tools'` (파일 없음)

- [ ] **Step 3: backend/tools.py 구현**

```python
from __future__ import annotations

from langchain_core.tools import tool

from backend.config import TAVILY_API_KEY


@tool
def web_search(query: str) -> str:
    """인터넷에서 최신 정보를 검색합니다. 시장 규모, 경쟁사 현황, 기술 트렌드, 유사 서비스 사례 검색에 사용하세요."""
    from tavily import TavilyClient
    client = TavilyClient(api_key=TAVILY_API_KEY)
    results = client.search(query=query, max_results=3)
    if not results.get("results"):
        return "검색 결과 없음"
    lines = []
    for r in results["results"]:
        title = r.get("title", "")
        content = r.get("content", "")[:300]
        lines.append(f"[{title}] {content}")
    return "\n\n".join(lines)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_tools.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/tools.py tests/test_tools.py
git commit -m "feat(fc): add web_search tool (Tavily wrapper)"
```

---

### Task 3: prompts.py — 페르소나 프롬프트에 도구 사용 힌트 추가

**Files:**
- Modify: `backend/prompts.py:17-54`

- [ ] **Step 1: INVESTOR_SYSTEM_PROMPT 수정**

`backend/prompts.py`의 `INVESTOR_SYSTEM_PROMPT`에서 `금지사항:` 줄 앞에 아래 줄을 추가:

```
도구: 시장 규모·경쟁사·수익 모델 사례를 실제로 검증해야 한다면 web_search 도구를 호출하세요.
```

수정 후 `INVESTOR_SYSTEM_PROMPT` 전체:

```python
INVESTOR_SYSTEM_PROMPT = """당신은 깐깐한 스타트업 투자자입니다.

역할: 시장성·차별성·수익/지속가능성 관점에서 기획서의 허점을 날카롭게 지적합니다.
평가 기준:
- 이미 시장에 유사 서비스가 있는가?
- 사용자가 돈/시간을 쓸 만큼 충분히 아픈 문제인가?
- 왜 지금 이 팀이 이 문제를 풀어야 하는가?
- 수익 모델과 지속가능성이 명확한가?

말투: 직설적이고 회피를 허용하지 않는다. 단순 비난이 아니라 "왜 그게 약점인지 + 어떤 방향으로 보완할 수 있는지"를 함께 제시한다.
도구: 시장 규모·경쟁사·수익 모델 사례를 실제로 검증해야 한다면 web_search 도구를 호출하세요.
금지사항: 근거 없이 시장 수치를 단정짓지 않는다. 불확실한 외부 사실은 "확인이 필요한 가정"으로 표기한다.
출력: 질문 1개만 한국어로 출력한다. 부연 설명 없이 질문 본문만 작성한다."""
```

- [ ] **Step 2: CTO_SYSTEM_PROMPT 수정**

`CTO_SYSTEM_PROMPT`의 `금지사항:` 줄 앞에 추가:

```
도구: 기술 스택 성숙도·유사 구현 사례·벤치마크를 확인해야 한다면 web_search 도구를 호출하세요.
```

수정 후 `CTO_SYSTEM_PROMPT` 전체:

```python
CTO_SYSTEM_PROMPT = """당신은 냉철한 CTO입니다.

역할: 기술 실현 가능성·아키텍처·LLM 적정성 관점에서 기획서의 기술적 허점을 지적합니다.
평가 기준:
- 이 기간 안에 구현 가능한가?
- LLM이 이 기능에 정말 필요한가? 과/오용은 아닌가?
- 실패/환각 케이스는 어떻게 처리하는가?
- 기술 스택 선택이 문제 특성에 적합한가?

말투: 직설적이고 기술적 근거를 요구한다. "왜 그게 약점인지 + 어떤 방향으로 보완할 수 있는지"를 함께 제시한다.
도구: 기술 스택 성숙도·유사 구현 사례·벤치마크를 확인해야 한다면 web_search 도구를 호출하세요.
금지사항: 근거 없이 기술 불가능을 단정짓지 않는다.
출력: 질문 1개만 한국어로 출력한다. 부연 설명 없이 질문 본문만 작성한다."""
```

- [ ] **Step 3: MENTOR_SYSTEM_PROMPT 수정**

`MENTOR_SYSTEM_PROMPT`의 `금지사항:` 줄 앞에 추가:

```
도구: 유사 MVP 사례·선행 연구·시장 검증 사례를 확인해야 한다면 web_search 도구를 호출하세요.
```

수정 후 `MENTOR_SYSTEM_PROMPT` 전체:

```python
MENTOR_SYSTEM_PROMPT = """당신은 예리한 멘토입니다.

역할: 논리 일관성·MVP 범위·우선순위 관점에서 기획서의 구조적 허점을 지적합니다.
평가 기준:
- 한 줄 정의와 핵심 기능이 일관성 있게 연결되는가?
- MVP가 너무 크거나 작지 않은가? 무엇을 버려야 하는가?
- 대상 사용자와 제공 가치가 명확하게 연결되는가?
- 문제 정의와 해결책이 논리적으로 연결되는가?

말투: 직설적이되 건설적이다. "왜 그게 약점인지 + 어떤 방향으로 보완할 수 있는지"를 함께 제시한다.
도구: 유사 MVP 사례·선행 연구·시장 검증 사례를 확인해야 한다면 web_search 도구를 호출하세요.
금지사항: 단순 비판 없이 보완 방향을 반드시 제시한다.
출력: 질문 1개만 한국어로 출력한다. 부연 설명 없이 질문 본문만 작성한다."""
```

- [ ] **Step 4: 기존 테스트 통과 확인**

```bash
pytest tests/ -v
```

Expected: 전체 테스트 통과 (prompts.py 변경은 기존 테스트에 영향 없음)

- [ ] **Step 5: Commit**

```bash
git add backend/prompts.py
git commit -m "feat(fc): add web_search tool hint to persona system prompts"
```

---

### Task 4: nodes.py — _run_persona에 Tool Calling 루프 통합

**Files:**
- Modify: `backend/nodes.py:1-10` (imports)
- Modify: `backend/nodes.py:57-96` (`_run_persona` 함수 전체)

- [ ] **Step 1: nodes.py imports에 ToolMessage 추가**

`backend/nodes.py` 상단 imports 블록을 아래로 교체:

```python
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
```

- [ ] **Step 2: _run_persona 함수 전체 교체**

`backend/nodes.py`의 `_run_persona` 함수(57~96번째 줄)를 아래로 교체:

```python
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

    # 1단계: LLM이 tool call 여부 결정
    tool_decision = await _bound_llm.ainvoke(base_messages)

    messages = list(base_messages)
    if tool_decision.tool_calls:
        # 2단계: tool call 실행 후 결과 주입
        messages.append(tool_decision)
        for tc in tool_decision.tool_calls:
            tool_result = web_search.invoke(tc["args"])
            messages.append(ToolMessage(content=str(tool_result), tool_call_id=tc["id"]))

    # 3단계: 최종 질문 스트리밍
    full_content = ""
    async for chunk in llm.astream(messages):
        if chunk.content:
            full_content += chunk.content

    return {
        "messages": [{"role": "assistant", "name": persona, "content": full_content}],
        "persona_outputs": [{"persona": persona, "question": full_content, "round": state["round"]}],
    }
```

- [ ] **Step 3: 기존 테스트 전체 통과 확인**

```bash
pytest tests/ -v
```

Expected: 28개 기존 테스트 모두 통과 (nodes.py import 변경이 다른 테스트에 영향 없어야 함)

- [ ] **Step 4: Commit**

```bash
git add backend/nodes.py
git commit -m "feat(fc): integrate tool calling in _run_persona (bind_tools + ToolMessage loop)"
```

---

### Task 5: 전체 테스트 실행 및 최종 검증

**Files:**
- (신규 파일 없음 - 검증 태스크)

- [ ] **Step 1: 전체 테스트 실행**

```bash
pytest tests/ -v
```

Expected: 32개 이상 통과 (기존 28 + test_tools 4)

- [ ] **Step 2: tools.py 임포트 연쇄 확인**

```bash
python -c "from backend.nodes import investor_node, cto_node, mentor_node; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: FastAPI 서버 기동 확인**

```bash
uvicorn backend.main:app --reload --port 8000
```

Expected: 에러 없이 기동 (Tavily API 키 없어도 서버는 뜸 — tool은 호출 시에만 사용)

- [ ] **Step 4: Final Commit**

```bash
git add .
git commit -m "feat(fc): function calling integration complete — personas can search web via Tavily"
```

---

## 주의사항

- **Tavily API 키**: `.env`에 `TAVILY_API_KEY=tvly-...` 설정 필요. 없으면 tool call 실행 시 `AuthenticationError` 발생 (서버 기동은 정상)
- **solar-pro2 tool calling**: `bind_tools()`는 LLM이 tool call 여부를 스스로 결정. 검색이 불필요하다고 판단하면 tool_calls가 비어 기존 RAG 방식으로만 동작
- **스트리밍 보장**: tool call 유무와 관계없이 최종 답변은 항상 `llm.astream(messages)`로 스트리밍됨
- **테스트 격리**: test_tools.py는 `TavilyClient`를 항상 mock — 실제 API 호출 없음
