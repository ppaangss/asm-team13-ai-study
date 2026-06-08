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
START → orchestrator → verification → data_verification
     → investor_analyze → cto_analyze → mentor_analyze
     → orchestrator_review (ReAct 루프, 최대 2회)
     → question_router → [investor | cto | mentor]
     → human (답변 대기) → answer_fact_check → followup_judge
     → 꼬리 질문 or 다음 라운드 or reporter → END
```
- `orchestrator_review` 가 서브에이전트 분석 결과를 검토하고 품질이 불충분하면 재분석을 요청합니다 (ReAct 루프).
- `question_router` 가 오케스트레이터 계획에 따라 라운드별 질문 페르소나를 결정합니다.

### 3. 기획서 사전 체크리스트 (정적 검증)
분석 시작 전 `verification_node`가 7개 항목을 자동 점검합니다.

| # | 항목 | 설명 |
|---|------|------|
| 1 | 출처 검증 | 시장 데이터·통계 출처 명시 여부 |
| 2 | BM 명확성 | 수익 모델·가격 정책 구체성 |
| 3 | 문제 구체성 | 해결 문제의 수치 근거 여부 |
| 4 | 차별화 근거 | 경쟁사 대비 차별점 명확성 |
| 5 | 기술 실현성 | MVP 내 기술 구현 가능성 |
| 6 | MVP 범위 | 첫 출시 범위의 현실성 |
| 7 | 팀 적합성 | 팀 역량과 문제 간 연관성 |

각 항목은 `pass / warn / fail` 로 분류됩니다.

### 4. 수치 데이터 검증 (웹 검색 팩트체크)
`data_verification_node`가 기획서에서 검증 가능한 수치 주장을 최대 4개 추출해 웹 검색으로 팩트체크합니다.

- **추출 대상**: 시장 규모·TAM, 성장률·CAGR, 사용자 통계, 경쟁사 현황
- **병렬 웹 검색**: `asyncio.gather`로 Tavily 검색 동시 실행
- **검증 결과**: `confirmed` / `unconfirmed` / `contradicted` 3단계 판정

### 5. 답변 신뢰도 검증 (웹 검색 팩트체크)
`answer_fact_check_node`가 사용자 답변에서 수치 주장을 최대 3개 추출해 웹 검색으로 진위를 검증합니다.

- **추출 대상**: 시장 규모·사용자 수·성장률 등 사실 확인 가능한 수치 주장
- **검증 결과**: `confirmed` / `unconfirmed` / `contradicted` 3단계 판정
- 최종 리포트에 "답변 신뢰도 검증 결과" 블록으로 반영

### 6. 꼬리 질문 시스템
`followup_judge`가 사용자 답변의 핵심 커버율(0~100)을 판단합니다.

- **맥락 기반 평가**: 짧은 답변("네", "맞습니다")도 질문 맥락을 고려해 LLM이 직접 판단
- **세션별 임계값 설정**: 업로드 전 UI에서 엄격·보통·순함 3단계로 조절 가능

| 단계 | base 임계값 | 0회차 | 1회차 | 2회차 |
|:---:|:---------:|:----:|:----:|:----:|
| 엄격 | 60 | 60 | 30 | 10 |
| 보통 (기본) | 30 | 30 | 15 | 5 |
| 순함 | 0 | 0 | 0 | 0 (꼬리질문 없음) |

- LLM 호출 실패 시 "오류 발생" 명시
- 판단 점수는 최종 리포트 생성 시 감점 근거로 활용됨

### 7. 최종 리포트 (구조화된 JSON)
모든 라운드 종료 후 `reporter` 노드가 구조화된 JSON 리포트를 생성합니다.

- **답변 품질 점수 반영**: `followup_judge` 점수가 섹션별 위험도와 종합 점수에 명시적으로 반영
  - 점수 0~29: 해당 섹션 risk_score +20, overall_score 감점
  - 점수 30~59: risk_score +10, 소폭 감점
  - 점수 60+: 감점 없음

```json
{
  "overall_score": 62,
  "weaknesses": [
    {
      "section": "수익 모델",
      "issue": "단가 근거 없음",
      "risk": "상",
      "risk_score": 78,
      "suggestion": "LTV/CAC 수치 추가 필요"
    }
  ]
}
```

### 8. Reranker 설계 결정

#### Upstage Reranking API 미사용 이유
`langchain-upstage 0.7.7` (현재 최신)에 `UpstageRerank` 클래스가 존재하지 않으며,
Upstage REST API (`api.upstage.ai`) 에도 공개 Reranking 엔드포인트가 없음을 직접 확인했습니다.

```
# 시도한 모든 엔드포인트 — 전부 404
POST https://api.upstage.ai/v1/reranking
POST https://api.upstage.ai/v1/rerank
POST https://api.upstage.ai/v1/solar/reranking
POST https://api.upstage.ai/v1/solar/rerank
```

#### 대안 선택: Flashrank (`ms-marco-MiniLM-L-12-v2`)

| 항목 | 내용 |
|------|------|
| 방식 | 로컬 Cross-Encoder 모델 (API 호출 없음) |
| 모델 크기 | 22MB (첫 실행 시 자동 다운로드 후 캐시) |
| API 키 | 불필요 |
| 추가 비용 | 없음 |
| 동작 방식 | ChromaDB 1차 검색 10개 → Flashrank 재정렬 → top_k=3 전달 |

실제 동작 검증 결과 — investor, cto, mentor 세 페르소나 모두 ChromaDB 코사인 유사도 순서와
Flashrank 재정렬 순서가 다르게 나와 실질적인 재정렬 효과를 확인했습니다.

### 9. 페르소나별 RAG
**예시 기획서 RAG**
- `data/examples/`에 저장된 기획서 예시를 오케스트레이터 분석에 활용
- 11개 도메인: AI 교육·헬스케어·핀테크·법률·HR·이커머스·기업교육·고객서비스·부동산·물류SCM·스마트팜

**페르소나 전문 지식 RAG**
- `knowledge/{investor,cto,mentor}/` 의 21개 전문 문서, 160청크
- `parse_markdown_sections()` → `##` 헤더 단위 청킹 → Flashrank 재정렬

| 페르소나 | 문서 수 | 청크 수 |
|---------|---------|---------|
| investor | 7 | 56 |
| cto | 7 | 49 |
| mentor | 7 | 55 |

### 10. 업로드 전 세션 설정 UI
업로드 화면에서 심사 전에 두 가지 파라미터를 설정할 수 있습니다.

| 설정 | 범위 | 기본값 | 설명 |
|------|------|--------|------|
| 최대 질문 수 | 1~6 | 3 | 페르소나 심사 라운드 수 |
| 꼬리질문 강도 | 엄격·보통·순함 | 보통 | 꼬리질문 발생 임계값 (`_derive_thresholds` 적용) |

### 11. SSE 이벤트 스펙 (프론트엔드 연동)

모든 이벤트 공통 구조:
```json
{ "token": "", "node": "dev", "done": false, "is_final": false, "debug": { ... } }
```

| `debug.type` | 시점 | 주요 필드 |
|---|---|---|
| `verification` | 분석 시작 직후 | `items[]{label, status, reason}` |
| `data_verification` | verification 직후 | `items[]{claim, status, reason, source}` |
| `followup_judge` | 각 답변 후 | `score, threshold, needs_followup, reason, persona, followup_question?` |
| `report` | 세션 종료 (`is_final: true`) | `overall_score, weaknesses[]` |

### 12. 파일 업로드
- 지원 형식: `.txt`, `.md`, `.pdf`, `.docx`
- 업로드 시 기획서를 섹션 단위로 파싱하고, 새 UUID `thread_id`로 세션 격리

### 13. API 키 가드레일
- `/upload` 호출 시 누락 키가 있으면 503 + `.env` 설정 안내 반환

---

## 기술 스택

| 영역 | 스택 |
|------|------|
| LLM | Solar Pro 2 (Upstage) |
| 워크플로우 | LangGraph `StateGraph` + `InMemorySaver` |
| 임베딩 / RAG | `solar-embedding-1-large` + ChromaDB |
| 리랭킹 | Flashrank `ms-marco-MiniLM-L-12-v2` (로컬) |
| 웹 검색 | Tavily |
| 백엔드 | FastAPI + `asyncio` |
| 프론트엔드 | Vite + React + TypeScript + Framer Motion |
| 트레이싱 | LangSmith |

---

## 프로젝트 구조

```
.
├── backend/
│   ├── config.py        # 환경 변수 및 상수
│   ├── file_reader.py   # TXT/MD/PDF/DOCX 텍스트 추출
│   ├── graph.py         # LangGraph 그래프 정의 및 라우팅
│   ├── main.py          # FastAPI 서버 (upload / chat/start / chat)
│   ├── nodes.py         # 모든 노드 구현
│   ├── parser.py        # 기획서 섹션 파싱
│   ├── prompts.py       # 페르소나별 시스템 프롬프트
│   ├── rag.py           # ChromaDB 인덱스 빌드 및 검색
│   ├── schemas.py       # Pydantic 스키마 + LangGraph State
│   └── tools.py         # 웹 검색 도구 (Tavily)
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # 앱 상태, SSE 스트리밍, 3-패널 UI
│   │   ├── utils.ts         # parseSSEChunk / routeDebugEvent 유틸
│   │   ├── utils.test.ts    # Vitest 단위 테스트 (11개)
│   │   ├── styles.css       # CSS 디자인 토큰 및 반응형 레이아웃
│   │   └── main.tsx         # React 진입점
│   ├── package.json     # Vite 프론트엔드 설정
│   └── index.html       # React 앱 진입 HTML
├── knowledge/
│   ├── investor/        # 투자자 전문 지식 (7개 문서, 56청크)
│   ├── cto/             # CTO 전문 지식 (7개 문서, 49청크)
│   └── mentor/          # 멘토 전문 지식 (7개 문서, 55청크)
├── tests/               # pytest 테스트 (104개)
├── requirements.txt
└── data/                # ChromaDB + 예시 기획서 (로컬 전용, .gitignore)
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
cd frontend
npm install
npm run dev
```

브라우저에서 `http://localhost:5173` 접속 후 기획서 파일을 업로드하면 심사가 시작됩니다.
백엔드가 꺼져 있거나 API 키가 없으면 React 프론트엔드는 자동으로 데모 심사 모드로 전환됩니다.

---

## 테스트

**백엔드 (pytest)**
```bash
pytest tests/ -v
```

**프론트엔드 (Vitest)**
```bash
cd frontend
npm test
```

104개 백엔드 + 11개 프론트엔드 = **115개 테스트** 전원 통과 (API 키 불필요, 외부 서비스 Mock 처리).

---

## 주요 설계 결정

- **세션 격리** — 업로드마다 새 UUID `thread_id` 생성. `InMemorySaver`가 thread_id별로 LangGraph 상태를 완전히 분리합니다.
- **단일 스트리밍 소스** — `_run_persona` 내에서 `llm.astream()` 만 사용합니다. `ainvoke()` + `astream()` 혼용 시 이중 스트리밍 버그가 발생합니다.
- **꼬리 질문 임계값 코드 강제** — LLM의 `needs_followup` 필드를 신뢰하지 않고, `score < threshold`를 직접 계산합니다.
- **짧은 답변 맥락 평가** — 15자 이하 답변도 가드레일 없이 LLM이 질문 맥락을 고려해 직접 판단합니다. "넵"도 맥락에 따라 충분한 답변일 수 있습니다.
- **구조화 리포트** — `reporter` 노드는 텍스트 스트리밍 대신 `with_structured_output`으로 JSON 생성 후 `debug_log`로 전달합니다. 프론트엔드가 `type: "report"` + `is_final: true` 이벤트를 수신해 대시보드를 렌더링합니다.
- **`pending_debug` 2-phase 패턴** — `followup_judge_node`에서 Q·A·score를 `pending_debug`에 임시 보관하고, 페르소나 노드가 꼬리 질문 생성 후 `debug_log`에 병합합니다.
- **마크다운 청킹 분리** — 기획서 파싱(`parse_sections`)과 지식 문서 파싱(`parse_markdown_sections`)을 별도 함수로 분리했습니다.
- **스테일 청크 교체** — `build_persona_index`는 파일별로 기존 청크 삭제 후 재인덱싱합니다.
- **수치 검증 병렬화** — `data_verification_node`는 `asyncio.gather`로 최대 4개 웹 검색을 동시 실행해 지연을 최소화합니다.
- **Reranker 로컬 대체** — `langchain-upstage 0.7.7` 에 `UpstageRerank` 클래스가 없고 Upstage 공개 Reranking REST API도 미존재(`/v1/solar/reranking` 등 전체 404). Flashrank `ms-marco-MiniLM-L-12-v2` (로컬, 22MB)로 대체. ChromaDB 1차 검색 10개 → Flashrank 재정렬 → top 3 전달. 실제 문서 순서 변경 확인.
- **답변 품질의 리포트 반영** — `followup_judge`가 산정한 Q&A 점수(0~100)를 `debug_log`에 축적해 `reporter_node` 컨텍스트에 주입합니다. LLM은 이를 근거로 섹션별 위험도와 종합 점수를 명시적으로 감점 처리합니다. 점수만 텍스트로 전달하고 판단은 LLM에 위임해 프롬프트와 스키마 변경 없이 구현했습니다.
- **세션별 심사 강도 설정** — `max_rounds`와 `followup_thresholds`를 `/chat/start` 요청 시 `initial_state`에 주입합니다. `_derive_thresholds(base)` 함수가 단일 숫자를 3회차 딕셔너리로 변환하며, base=0이면 모든 임계값이 0이 되어 꼬리질문이 발생하지 않습니다.
- **안전도 점수(Safety Score)** — 프론트엔드 리포트에서 `risk_score`를 `100 - risk_score`로 변환해 표시합니다. 종합 점수(`overall_score`)와 방향이 통일되어 "높을수록 좋음"으로 일관됩니다. 백엔드 스키마는 변경하지 않았습니다.
