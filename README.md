# 기획서 검증 에이전트

AI 페르소나(투자자·CTO·멘토)가 기획서를 라운드제로 심사하고 꼬리 질문으로 약점을 깊게 파고드는 멀티 에이전트 시스템입니다.

---

## 주요 기능

### 1. 멀티 페르소나 심사
- **깐깐한 투자자** — 시장성·차별화·수익 모델·지속가능성 관점
- **냉철한 CTO** — 기술 실현 가능성·LLM 적정성·아키텍처 관점
- **예리한 멘토** — 문제 정의·PMF·GTM·팀 구성 관점

각 페르소나는 기획서 섹션을 분담 배분받아 집중 심사하며, 오케스트레이터가 라운드별 순서와 집중 포인트를 결정합니다.

### 2. ReAct 서브에이전트 아키텍처
```
START → orchestrator
     → investor_analyze → cto_analyze → mentor_analyze
     → orchestrator_review (ReAct 루프, 최대 2회)
     → question_router → [investor | cto | mentor]
     → human (답변 대기) → followup_judge
     → 꼬리 질문 or 다음 라운드 or reporter → END
```
- `orchestrator_review` 가 서브에이전트 분석 결과를 검토하고 품질이 불충분하면 재분석을 요청합니다 (ReAct 루프).
- `question_router` 가 오케스트레이터 계획에 따라 라운드별 질문 페르소나를 결정합니다.

### 3. 꼬리 질문 시스템
`followup_judge` 가 사용자 답변의 핵심 커버율(0~100)을 판단하고, 점수가 임계값 미만이면 같은 페르소나가 꼬리 질문을 이어서 합니다.

| 꼬리 질문 횟수 | 임계값 |
|:-----------:|:------:|
| 0회차 (첫 답변) | 30 |
| 1회차 꼬리 | 15 |
| 2회차 꼬리 | 5 |

> `needs_followup`은 LLM 구조화 출력에 의존하지 않고, `score < threshold`를 코드에서 직접 판정합니다.

### 4. 페르소나별 RAG (Retrieval-Augmented Generation)
- **예시 기획서 RAG** — `data/examples/`에 저장된 기획서 예시로 오케스트레이터 분석을 보강합니다.
- **페르소나 전문 지식 RAG** — `knowledge/{investor,cto,mentor}/` 의 21개 전문 문서(VC 평가 프레임워크, LLM 함정, PMF 검증 등)를 ChromaDB에 인덱싱해 페르소나 분석 시 주입합니다.
- 임베딩 모델: `solar-embedding-1-large` (Upstage)

### 5. 실시간 스트리밍
- FastAPI `StreamingResponse` + SSE로 LLM 토큰을 실시간 전송합니다.
- LangGraph `stream_mode=["messages", "updates"]` 사용 — 토큰 스트리밍과 디버그 이벤트를 동시에 수신합니다.
- `httpx.RemoteProtocolError` 에 대한 try/except/finally 보호 처리가 되어 있으며, `done` 이벤트는 항상 전송됩니다.

### 6. 개발자 모드 디버그 패널
사이드바 토글로 활성화하며, 라운드별 심사 내역을 실시간으로 확인할 수 있습니다.

- 라운드·페르소나·꼬리 질문 횟수 표시
- 답변 커버율 progress bar (`0~100`)
- 판단 임계값 및 최종 판정 (꼬리 질문 / 다음 라운드)
- 생성된 꼬리 질문 전문

### 7. 최종 리포트
모든 라운드 종료 후 `reporter` 노드가 심사 결과를 종합해 약점 목록과 총평을 생성합니다.

### 8. 파일 업로드
- 지원 형식: `.txt`, `.md`, `.pdf`
- 업로드 시 기획서를 섹션 단위로 파싱하고, 새 UUID `thread_id`로 세션을 격리합니다.

---

## 기술 스택

| 영역 | 스택 |
|------|------|
| LLM | Solar Pro 2 (Upstage) |
| 워크플로우 | LangGraph `StateGraph` + `InMemorySaver` |
| 임베딩 / RAG | `solar-embedding-1-large` + ChromaDB |
| 백엔드 | FastAPI + `asyncio` |
| 프론트엔드 | Streamlit 1.57 (Pretendard 폰트, Coinbase 스타일 디자인) |
| 트레이싱 | LangSmith (`.env`에서 설정) |

---

## 프로젝트 구조

```
.
├── backend/
│   ├── config.py        # 환경 변수 및 상수
│   ├── file_reader.py   # TXT/MD/PDF 텍스트 추출
│   ├── graph.py         # LangGraph 그래프 정의 및 라우팅
│   ├── main.py          # FastAPI 서버 (upload / chat/start / chat)
│   ├── nodes.py         # 모든 노드 구현
│   ├── parser.py        # 기획서 섹션 파싱
│   ├── prompts.py       # 페르소나별 시스템 프롬프트
│   ├── rag.py           # ChromaDB 인덱스 빌드 및 검색
│   ├── schemas.py       # Pydantic 스키마 + LangGraph State
│   └── tools.py         # 웹 검색 도구 (Tavily)
├── frontend/
│   └── app.py           # Streamlit 앱
├── knowledge/
│   ├── investor/        # 투자자 전문 지식 (7개 문서)
│   ├── cto/             # CTO 전문 지식 (7개 문서)
│   └── mentor/          # 멘토 전문 지식 (7개 문서)
├── tests/               # pytest 테스트 (61개)
└── data/                # ChromaDB + 예시 기획서 (로컬 전용, 미커밋)
```

---

## 설치 및 실행

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정

`.env` 파일을 프로젝트 루트에 생성합니다 (절대 커밋하지 말 것):

```env
UPSTAGE_API_KEY=your_upstage_api_key
TAVILY_API_KEY=your_tavily_api_key
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_PROJECT=your_project_name
```

### 3. 백엔드 실행

```bash
uvicorn backend.main:app --reload
```

### 4. 프론트엔드 실행

```bash
streamlit run frontend/app.py
```

브라우저에서 `http://localhost:8501` 접속 후 기획서 파일(.txt / .md / .pdf)을 업로드하면 심사가 시작됩니다.

---

## 테스트

```bash
pytest tests/ -v
```

61개 테스트 통과 기준으로 관리합니다.

---

## 주요 설계 결정

- **세션 격리** — 업로드마다 새 UUID `thread_id` 생성. `InMemorySaver`가 thread_id별로 LangGraph 상태를 완전히 분리하므로 이전 기획서 컨텍스트가 오염되지 않습니다.
- **단일 스트리밍 소스** — `_run_persona` 내에서 `llm.astream()` 만 사용합니다. `ainvoke()` + `astream()` 혼용 시 LangGraph가 두 LLM 호출을 모두 스트리밍해 채팅 표시 질문과 디버그 로그 질문이 달라지는 이중 스트리밍 버그가 발생합니다.
- **꼬리 질문 임계값 코드 강제** — LLM의 `needs_followup` 필드를 신뢰하지 않고, `score < threshold`를 직접 계산합니다. LLM이 score=30, threshold=15 상황에서도 `needs_followup=True`를 반환하는 경우가 있었기 때문입니다.
- **`pending_debug` 2-phase 패턴** — `followup_judge_node`에서 Q·A·score를 `pending_debug`에 임시 보관하고, 페르소나 노드가 꼬리 질문 생성 후 `debug_log`에 병합합니다. 이 덕분에 하나의 디버그 항목에 판정 정보와 생성 질문이 모두 담깁니다.
