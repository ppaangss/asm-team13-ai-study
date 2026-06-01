# RAG Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 예시 기획서 코퍼스를 ChromaDB에 임베딩 저장하고, 오케스트레이터와 페르소나 노드가 유사 패턴을 검색해 더 근거 있는 질문을 생성하도록 RAG를 연결한다.

**Architecture:** `data/examples/`에 3개의 한국어 예시 기획서(의도적 약점 포함)를 두고, `backend/rag.py`가 Upstage solar-embedding으로 청크를 임베딩해 ChromaDB에 저장한다. `orchestrator_node`는 기획서 업로드 시 유사 실패 패턴을 검색해 6라운드 계획을 구체화하고, `_run_persona`는 각 라운드에서 해당 섹션·페르소나 관점의 사례를 검색해 질문에 근거를 부여한다.

**Tech Stack:** chromadb 0.4+, langchain-upstage 0.7.7 (UpstageEmbeddings: solar-embedding-1-passage / solar-embedding-1-query), Python 3.13, FastAPI lifespan event

---

## 변경 파일 구조

```
data/
  examples/
    ai_speaking_coach.txt      신규: 영어 스피킹 앱 예시 (수익모델·시장분석 약점)
    ai_interview_coach.txt     신규: 면접 코칭 앱 예시 (기술 과대평가·전환율 허수)
    soho_marketing.txt         신규: 소상공인 마케팅 앱 예시 (MVP 과다·타겟 불명확)
  chroma_db/                   자동 생성 (ChromaDB 영속 저장소, .gitignore 추가)

backend/
  config.py       수정: CHROMA_DB_PATH, RAG_TOP_K, EXAMPLES_DIR 상수 추가
  rag.py          신규: get_collection(), build_index(), retrieve() 구현
  nodes.py        수정: orchestrator_node + _run_persona에 retrieve() 호출 추가
  main.py         수정: lifespan 이벤트로 build_index() 자동 실행

tests/
  test_rag.py     신규: RAG 함수 4개 테스트 (API 호출 없이 FakeEmbedder 사용)
```

---

## Task 1: chromadb 설치 + config.py 상수 추가

**Files:**
- Modify: `backend/config.py`

- [ ] **Step 1: chromadb 설치**

```bash
cd C:\Users\nunu\Desktop\test\AI_EDU\asm-team13-ai-study && pip install chromadb
```

Expected: `Successfully installed chromadb-...`

- [ ] **Step 2: 설치 확인**

```bash
python -c "import chromadb; print(chromadb.__version__)"
```

Expected: 버전 출력 (예: `0.6.x`)

- [ ] **Step 3: `backend/config.py` 전체 교체**

```python
from dotenv import load_dotenv
import os

load_dotenv()

UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY", "")
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

- [ ] **Step 4: 임포트 확인**

```bash
cd C:\Users\nunu\Desktop\test\AI_EDU\asm-team13-ai-study && python -c "
from backend.config import CHROMA_DB_PATH, RAG_TOP_K, EXAMPLES_DIR
print(CHROMA_DB_PATH, RAG_TOP_K, EXAMPLES_DIR)
"
```

Expected: `data/chroma_db 3 data/examples`

- [ ] **Step 5: 커밋**

```bash
cd C:\Users\nunu\Desktop\test\AI_EDU\asm-team13-ai-study && git add backend/config.py && git commit -m "feat: add RAG config constants and install chromadb"
```

---

## Task 2: data/examples/ — 예시 기획서 3개 생성

**Files:**
- Create: `data/examples/ai_speaking_coach.txt`
- Create: `data/examples/ai_interview_coach.txt`
- Create: `data/examples/soho_marketing.txt`
- Create: `.gitignore` 업데이트 (data/chroma_db/ 제외)

- [ ] **Step 1: `data/examples/` 디렉토리 생성**

```bash
cd C:\Users\nunu\Desktop\test\AI_EDU\asm-team13-ai-study && mkdir -p data/examples
```

- [ ] **Step 2: `data/examples/ai_speaking_coach.txt` 작성**

약점: 수익모델 불명확, 경쟁사 분석 없음, 기술 비용 미검토

```
1. 서비스 개요
AI 기반 영어 스피킹 코치 앱으로 사용자의 발음과 문법을 실시간으로 교정하고 맞춤형 학습 경로를 제공합니다.

2. 문제 정의
국내 영어 학습자들은 스피킹 연습 기회가 절대적으로 부족합니다. 학원비는 비싸고 원어민과의 대화 기회는 제한적입니다.

3. 핵심 기능
- 실시간 발음 교정 (STT 기반)
- AI 대화 파트너 (주제별 시뮬레이션)
- 학습 진도 및 약점 추적 대시보드

4. 기술 구현
OpenAI Whisper로 음성 인식, GPT-4로 대화 생성, TTS API로 음성 출력합니다. 6개월 내 MVP 출시 예정입니다.

5. 수익 모델
초기에는 무료로 출시해 사용자를 최대한 모은 뒤 수익화 방법을 검토할 예정입니다. 프리미엄 기능 잠금 해제 방식을 고려 중입니다.

6. 시장 분석
영어 학습 시장은 전 세계적으로 매우 크고 지속적으로 성장하고 있습니다. 특히 MZ세대의 자기계발 수요가 높아 충분한 시장이 있다고 판단합니다.

7. 팀 구성
개발자 2명, 영어 교육 전문가 1명으로 구성되어 있습니다.
```

- [ ] **Step 3: `data/examples/ai_interview_coach.txt` 작성**

약점: 기술 일정 비현실적, 전환율 근거 없음, 규제 미고려

```
1. 서비스 개요
AI 면접관 페르소나 시스템으로 취업 준비생에게 실전과 동일한 압박 면접 환경을 제공합니다. 투자자, CTO, HR 담당자 페르소나가 순차적으로 질문합니다.

2. 문제 정의
취업 준비생의 88%가 실전 모의 면접 기회 부족을 호소합니다. 기존 면접 스터디는 동료 피드백의 한계가 있습니다.

3. 핵심 기능
- AI 다중 페르소나 면접관 (투자자/CTO/HR/멘토)
- 답변 실시간 품질 평가 (논리성, 구체성, 간결성)
- 취약 항목 자동 추출 및 반복 훈련
- 업종별 면접 예상 질문 데이터베이스

4. 기술 구현
LLM 기반 다중 에이전트 시스템으로 각 페르소나가 독립적으로 평가합니다. RAG로 면접 질문 DB를 구성합니다. 3개월 내 베타 버전 출시 예정입니다.

5. 수익 모델
월 9,900원 구독제로 운영합니다. 국내 취업 준비생 50만 명 중 전환율 20% 가정 시 1년 내 월 10억 원 매출이 가능합니다.

6. 시장 분析
에듀테크 시장은 코로나 이후 급성장했으며 AI 기반 서비스로의 전환이 가속화되고 있습니다. 경쟁사 대비 다중 페르소나 방식이 차별점입니다.

7. 팀 구성
풀스택 개발자 3명, PM 1명, AI 엔지니어 1명으로 구성되어 있습니다.
```

- [ ] **Step 4: `data/examples/soho_marketing.txt` 작성**

약점: MVP 범위 과다, 타겟 세분화 없음, 기술 복잡도 과소평가

```
1. 서비스 개요
소상공인을 위한 올인원 AI 마케팅 플랫폼으로 SNS 콘텐츠 자동 생성부터 광고 성과 최적화, 고객 관리까지 통합 제공합니다.

2. 문제 정의
국내 소상공인 300만 명은 마케팅 전문 지식과 실행 시간이 부족합니다. 외주 대행사는 비용이 크고 결과를 통제하기 어렵습니다.

3. 핵심 기능
- SNS 콘텐츠 자동 생성 (인스타그램, 블로그, 유튜브 쇼츠)
- 실시간 광고 성과 분석 및 자동 최적화
- 경쟁사 SNS 모니터링
- 고객 리뷰 자동 응답 생성
- 월별 매출 예측 대시보드

4. 기술 구현
멀티모달 LLM으로 텍스트와 이미지를 동시 생성하고 카카오, 네이버, 메타 광고 API와 전면 연동합니다. 6개월 내 전체 기능 출시를 목표로 합니다.

5. 수익 모델
기본 무료 제공, 프리미엄 플랜 월 29,900원, 광고 집행 대행 수수료 15% 수취 구조입니다.

6. 시장 분析
국내 소상공인 약 300만 명이 잠재 타겟입니다. 디지털 전환 정부 지원 사업과 연계해 초기 고객을 확보할 계획입니다.

7. 팀 구성
개발자 4명, 디자이너 1명, 사업개발 1명으로 구성되어 있습니다.
```

- [ ] **Step 5: `.gitignore`에 chroma_db 추가**

`.gitignore` 파일 끝에 아래를 추가한다 (파일이 없으면 새로 생성):

```
# ChromaDB 영속 저장소 (자동 생성)
data/chroma_db/
```

- [ ] **Step 6: 파일 존재 확인**

```bash
cd C:\Users\nunu\Desktop\test\AI_EDU\asm-team13-ai-study && python -c "
from pathlib import Path
files = list(Path('data/examples').glob('*.txt'))
print([f.name for f in files])
assert len(files) == 3
print('examples OK')
"
```

Expected: `['ai_speaking_coach.txt', 'ai_interview_coach.txt', 'soho_marketing.txt']`

- [ ] **Step 7: 커밋**

```bash
cd C:\Users\nunu\Desktop\test\AI_EDU\asm-team13-ai-study && git add data/examples/ .gitignore && git commit -m "feat: add example planning docs for RAG corpus"
```

---

## Task 3: backend/rag.py + tests/test_rag.py

**Files:**
- Create: `backend/rag.py`
- Create: `tests/test_rag.py`

- [ ] **Step 1: `tests/test_rag.py` 작성 (실패 상태)**

```python
import pytest
import chromadb
from pathlib import Path


class _FakeEmbedder:
    """API 호출 없이 테스트용 임의 벡터 반환."""
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(i % 10) / 10] * 8 for i in range(len(texts))]

    def embed_query(self, text: str) -> list[float]:
        return [0.5] * 8


@pytest.fixture
def fake_col():
    """인메모리 ChromaDB 컬렉션 (테스트 격리)."""
    client = chromadb.EphemeralClient()
    return client.create_collection("test_planning_examples")


def test_example_files_exist():
    files = list(Path("data/examples").glob("*.txt"))
    assert len(files) >= 3


def test_build_index_adds_docs(fake_col, monkeypatch):
    monkeypatch.setattr("backend.rag._get_embedder_passage", lambda: _FakeEmbedder())
    from backend.rag import build_index
    build_index(collection=fake_col)
    assert fake_col.count() > 0


def test_build_index_idempotent(fake_col, monkeypatch):
    monkeypatch.setattr("backend.rag._get_embedder_passage", lambda: _FakeEmbedder())
    from backend.rag import build_index
    build_index(collection=fake_col)
    count1 = fake_col.count()
    build_index(collection=fake_col)
    count2 = fake_col.count()
    assert count1 == count2


def test_retrieve_returns_nonempty_string(fake_col, monkeypatch):
    monkeypatch.setattr("backend.rag._get_embedder_passage", lambda: _FakeEmbedder())
    monkeypatch.setattr("backend.rag._get_embedder_query", lambda: _FakeEmbedder())
    from backend.rag import build_index, retrieve
    build_index(collection=fake_col)
    result = retrieve("시장 분析 차별성", collection=fake_col)
    assert isinstance(result, str)
    assert len(result) > 0


def test_retrieve_empty_collection_returns_empty(fake_col, monkeypatch):
    monkeypatch.setattr("backend.rag._get_embedder_query", lambda: _FakeEmbedder())
    from backend.rag import retrieve
    result = retrieve("시장 분析", collection=fake_col)
    assert result == ""
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
cd C:\Users\nunu\Desktop\test\AI_EDU\asm-team13-ai-study && python -m pytest tests/test_rag.py -v
```

Expected: `ImportError: No module named 'backend.rag'`

- [ ] **Step 3: `backend/rag.py` 작성**

```python
from pathlib import Path

import chromadb

from backend.config import UPSTAGE_API_KEY, CHROMA_DB_PATH, RAG_TOP_K, EXAMPLES_DIR
from backend.parser import parse_sections


def _get_embedder_passage():
    from langchain_upstage import UpstageEmbeddings
    return UpstageEmbeddings(model="solar-embedding-1-passage", api_key=UPSTAGE_API_KEY)


def _get_embedder_query():
    from langchain_upstage import UpstageEmbeddings
    return UpstageEmbeddings(model="solar-embedding-1-query", api_key=UPSTAGE_API_KEY)


def get_collection(db_path: str | None = None) -> chromadb.Collection:
    """ChromaDB 컬렉션 반환. db_path 미지정 시 config의 CHROMA_DB_PATH 사용."""
    path = db_path or CHROMA_DB_PATH
    client = chromadb.PersistentClient(path=path)
    return client.get_or_create_collection(
        name="planning_examples",
        metadata={"hnsw:space": "cosine"},
    )


def build_index(collection: chromadb.Collection | None = None) -> None:
    """data/examples/ TXT 파일을 섹션 단위로 청킹해 ChromaDB에 저장. 중복 없이 멱등 실행."""
    if collection is None:
        collection = get_collection()

    examples_path = Path(EXAMPLES_DIR)
    if not examples_path.exists():
        return

    texts, ids, metadatas = [], [], []
    for txt_file in sorted(examples_path.glob("*.txt")):
        raw = txt_file.read_text(encoding="utf-8")
        sections = parse_sections(raw)
        for section_title, section_content in sections.items():
            doc_id = f"{txt_file.stem}::{section_title}"
            # 이미 인덱싱된 문서는 건너뜀 (멱등성 보장)
            if collection.get(ids=[doc_id])["ids"]:
                continue
            chunk = f"[{section_title}]\n{section_content}"
            texts.append(chunk)
            ids.append(doc_id)
            metadatas.append({"source": txt_file.stem, "section": section_title})

    if not texts:
        return

    embedder = _get_embedder_passage()
    vectors = embedder.embed_documents(texts)
    collection.add(documents=texts, embeddings=vectors, ids=ids, metadatas=metadatas)


def retrieve(
    query: str,
    top_k: int | None = None,
    collection: chromadb.Collection | None = None,
) -> str:
    """쿼리와 유사한 예시 섹션 top_k개를 레이블 포함 문자열로 반환. 컬렉션이 비어 있으면 ''."""
    if collection is None:
        collection = get_collection()
    if collection.count() == 0:
        return ""

    k = top_k if top_k is not None else RAG_TOP_K
    embedder = _get_embedder_query()
    query_vec = embedder.embed_query(query)

    results = collection.query(
        query_embeddings=[query_vec],
        n_results=min(k, collection.count()),
    )

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    if not docs:
        return ""

    lines = ["=== 유사 사례 참조 ==="]
    for doc, meta in zip(docs, metas):
        lines.append(f"\n[출처: {meta['source']} — {meta['section']}]")
        lines.append(doc)
    return "\n".join(lines)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd C:\Users\nunu\Desktop\test\AI_EDU\asm-team13-ai-study && python -m pytest tests/test_rag.py -v
```

Expected: `5 passed`

- [ ] **Step 5: 전체 테스트 확인**

```bash
cd C:\Users\nunu\Desktop\test\AI_EDU\asm-team13-ai-study && python -m pytest tests/ -v
```

Expected: 기존 15 + 신규 5 = `20 passed`

- [ ] **Step 6: 커밋**

```bash
cd C:\Users\nunu\Desktop\test\AI_EDU\asm-team13-ai-study && git add backend/rag.py tests/test_rag.py && git commit -m "feat: add RAG module with ChromaDB + Upstage solar-embedding"
```

---

## Task 4: nodes.py + main.py — RAG 컨텍스트 주입 + 인덱스 자동 빌드

**Files:**
- Modify: `backend/nodes.py`
- Modify: `backend/main.py`

- [ ] **Step 1: `backend/nodes.py` 전체 교체**

`rag.retrieve()`를 `orchestrator_node`와 `_run_persona` 두 곳에 주입한다.

```python
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import interrupt

from backend.config import MODEL_NAME
from backend.prompts import SYSTEM_PROMPTS
from backend.rag import retrieve
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
    """기획서를 분석해 6라운드 심사 계획을 수립한다. RAG로 유사 실패 패턴을 참조한다."""
    context = _format_context(state)

    # RAG: 기획서 전체 요약으로 유사 실패 패턴 검색
    rag_context = retrieve(context[:500])  # 앞 500자로 쿼리 (토큰 절약)

    structured_llm = llm.with_structured_output(OrchestratorPlan)
    rag_block = f"\n\n{rag_context}" if rag_context else ""
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
    """공통 페르소나 실행 로직. llm.astream()으로 토큰 단위 스트리밍. RAG 사례 참조."""
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

    # RAG: 페르소나·섹션 관점의 실패 사례 검색
    rag_query = f"{persona} 관점 {focus_section} 약점" if focus_section else f"{persona} 관점 기획서 약점"
    rag_context = retrieve(rag_query)
    rag_block = f"\n\n{rag_context}" if rag_context else ""

    messages = [
        SystemMessage(content=SYSTEM_PROMPTS[persona]),
        HumanMessage(
            content=(
                f"{context}\n\n{history}{focus_context}{rag_block}\n\n"
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

- [ ] **Step 2: `backend/main.py`에 lifespan 이벤트 추가**

현재 `main.py`의 `app = FastAPI(...)` 선언을 lifespan 방식으로 변경한다.

파일 상단 임포트 블록에 `contextlib` 추가:

```python
import json
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langgraph.types import Command

from backend.graph import graph
from backend.parser import parse_sections
from backend.rag import build_index
from backend.schemas import UploadResponse, ChatRequest, ChatEvent
```

`app = FastAPI(...)` 선언을 아래로 교체 (`lifespan` 추가):

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    build_index()   # 서버 시작 시 RAG 인덱스 빌드 (이미 인덱싱된 문서는 건너뜀)
    yield


app = FastAPI(title="기획서 검증 에이전트 API", version="2.0.0", lifespan=lifespan)
```

- [ ] **Step 3: 임포트 및 서버 기동 확인**

```bash
cd C:\Users\nunu\Desktop\test\AI_EDU\asm-team13-ai-study && python -c "
from backend.nodes import orchestrator_node, investor_node
from backend.main import app
print('nodes + main OK')
"
```

Expected: `nodes + main OK`

- [ ] **Step 4: 전체 테스트 통과 확인**

```bash
cd C:\Users\nunu\Desktop\test\AI_EDU\asm-team13-ai-study && python -m pytest tests/ -v
```

Expected: `20 passed`

- [ ] **Step 5: 커밋**

```bash
cd C:\Users\nunu\Desktop\test\AI_EDU\asm-team13-ai-study && git add backend/nodes.py backend/main.py && git commit -m "feat: inject RAG context into orchestrator and persona nodes"
```

---

## Self-Review

### Spec 커버리지

| 요구사항 | Task | 구현 |
|----------|------|------|
| 예시 기획서 코퍼스 (3개) | Task 2 | ✅ ai_speaking_coach, ai_interview_coach, soho_marketing |
| ChromaDB 벡터 저장소 | Task 3 | ✅ PersistentClient + cosine 컬렉션 |
| Upstage solar-embedding 임베딩 | Task 3 | ✅ passage(인덱싱) + query(검색) 분리 |
| 섹션 단위 청킹 | Task 3 | ✅ parse_sections() 재사용 |
| 멱등 인덱싱 (중복 방지) | Task 3 | ✅ collection.get(ids=[doc_id]) 선체크 |
| 오케스트레이터 RAG 주입 | Task 4 | ✅ 기획서 앞 500자로 쿼리 후 rag_block 주입 |
| 페르소나 RAG 주입 | Task 4 | ✅ "{persona} 관점 {section} 약점" 쿼리 |
| 서버 시작 시 자동 인덱싱 | Task 4 | ✅ lifespan 이벤트로 build_index() |
| 빈 컬렉션 안전 처리 | Task 3 | ✅ count()==0 이면 '' 반환 |
| 테스트 (API 없이 FakeEmbedder) | Task 3 | ✅ 5개 테스트 |

### 주의사항

- `data/chroma_db/`는 `.gitignore`에 추가 — Upstage 임베딩 결과가 저장되므로 커밋하지 않는다.
- `UpstageEmbeddings`는 동기 함수 (`embed_documents`, `embed_query`) — `build_index`와 `retrieve`는 sync 함수로 설계됐고, `orchestrator_node`/`_run_persona`는 async 함수 안에서 동기 호출한다 (빠르게 완료되므로 문제 없음). 병목이 되면 `asyncio.to_thread()` 래핑 검토.
- `retrieve(context[:500])` — 오케스트레이터 쿼리에서 기획서 전체 대신 앞 500자를 사용해 임베딩 비용을 절약한다.
