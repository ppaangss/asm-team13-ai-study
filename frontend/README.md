# Frontend README

Vite + React + TypeScript 기반의 기획서 검증 에이전트 프론트엔드입니다. FastAPI 백엔드의 업로드/채팅 SSE API를 소비하며, 백엔드가 꺼져 있거나 API 키가 없는 경우에도 UI를 확인할 수 있도록 mock review mode를 제공합니다.

## Tech Stack

- Vite
- React 19
- TypeScript
- Framer Motion
- lucide-react
- Plain CSS with design tokens

## Run

```bash
npm install
npm run dev
```

기본 개발 서버는 `http://localhost:5173`입니다.

백엔드 API 주소는 기본값 `http://localhost:8000`이며, 필요하면 환경 변수로 바꿀 수 있습니다.

```env
VITE_API_BASE=http://localhost:8000
```

## Directory Structure

```text
frontend/
├── index.html
├── package.json
├── package-lock.json
├── tsconfig.json
├── tsconfig.node.json
├── vite.config.ts
└── src/
    ├── App.tsx          # 앱 상태, API/SSE 처리, 모든 화면 컴포넌트
    ├── utils.ts         # parseSSEChunk / routeDebugEvent 순수 유틸
    ├── utils.test.ts    # Vitest 단위 테스트 (11개)
    ├── test-setup.ts    # @testing-library/jest-dom 초기화
    ├── main.tsx         # React entrypoint
    ├── styles.css       # design.md 기반 스타일과 반응형 레이아웃
    └── vite-env.d.ts    # Vite 타입 참조
```

현재는 단일 화면 앱이라 `App.tsx` 안에 컴포넌트를 모아두었습니다. 컴포넌트가 더 커지면 다음 기준으로 분리하는 것을 권장합니다.

```text
src/
├── components/
│   ├── chat/
│   ├── insight/
│   ├── upload/
│   └── common/
├── lib/
│   ├── api.ts
│   └── stream.ts
└── types/
    └── events.ts
```

## Architecture

프론트엔드는 세 가지 레이어로 구성됩니다.

1. **Transport layer**
   - `uploadPlan()`이 `POST /upload`로 파일을 전송합니다.
   - `streamChat()`이 `POST /chat/start`, `POST /chat` 응답을 `ReadableStream`으로 읽습니다.
   - 백엔드 SSE는 `data: {...}\n\n` 형식이므로 chunk buffer를 직접 파싱합니다.

2. **State layer**
   - `App()`이 세션 상태를 소유합니다.
   - 핵심 상태:
     - `threadId`
     - `messages`
     - `verificationResults`
     - `dataVerificationResults`
     - `debugLog`
     - `finalReport`
     - `isStreaming`
     - `isDone`
     - `isDemoMode`
     - `activeInsightTab`

3. **Presentation layer**
   - 왼쪽 메인 컬럼:
     - `WorkflowStepper`
     - `FileDropzone`
     - `ChatTranscript`
     - `AnswerFeedbackChip`
   - 오른쪽 인사이트 컬럼:
     - `InsightPanel`
     - `VerificationPanel`
     - `AnswerQualityPanel`
     - `ReportPanel`
     - `DebugLog`

## Data-Driven Flow

이 UI는 화면을 절차적으로 제어하기보다, 백엔드 이벤트와 상태 데이터가 화면을 결정하는 data-driven 구조입니다.

### 1. Upload

사용자가 파일을 선택하거나 드래그 앤 드롭하면 `file` 상태가 채워집니다.

```ts
const [file, setFile] = useState<File | null>(null);
```

`심사 시작`을 누르면:

1. `POST /upload`
2. `thread_id` 저장
3. 초기 assistant 메시지 표시
4. `POST /chat/start` 스트리밍 시작

백엔드 연결에 실패하면 `startDemoReview()`로 전환됩니다.

### 2. Streaming Chat

`streamChat()`은 백엔드의 SSE-like 응답을 직접 읽습니다.

```ts
const reader = response.body.getReader();
const decoder = new TextDecoder();
```

수신 이벤트는 `handleChatEvent()`로 전달됩니다.

- `node !== "dev"`: 일반 채팅 토큰으로 처리
- `node === "dev"`: `debug.type`에 따라 검증/답변품질/리포트 데이터로 처리
- `done === true`: 스트림 종료 처리

### 3. Event Types

프론트가 사용하는 주요 이벤트 타입은 다음과 같습니다.

```ts
type ChatEvent = {
  token: string;
  node: Persona | "dev" | "";
  done: boolean;
  is_final: boolean;
  debug?: DebugEvent | null;
};
```

`debug.type`별 처리:

| type | 저장 위치 | 주요 UI |
| --- | --- | --- |
| `verification` | `verificationResults` | 검증 탭 |
| `data_verification` | `dataVerificationResults`, `debugLog` | 검증 탭, 리포트 탭 |
| `followup_judge` | `debugLog` | 답변 탭, 사용자 말풍선 chip |
| `report` | `finalReport`, `debugLog` | 리포트 탭 |

### 4. Derived UI State

몇몇 화면 상태는 원본 데이터를 바탕으로 계산됩니다.

```ts
const followupEvents = debugLog.filter(isFollowupDebug);
const latestFollowup = followupEvents.at(-1) ?? null;
const phase = finalReport || isDone ? 3 : threadId ? 2 : verificationResults.length ? 1 : 0;
```

`activeInsightTab`은 이벤트 흐름에 따라 자동 전환됩니다.

- 리포트 수신 시: `report`
- 답변 품질 판정 수신 시: `answer`
- 검증 결과 수신 시: `verification`

## Component Overview

### `FileDropzone`

- `.txt`, `.md`, `.pdf`, `.docx`만 허용합니다.
- 클릭 선택과 drag-and-drop을 모두 지원합니다.
- 지원하지 않는 파일은 `onReject()`로 에러 메시지를 올립니다.

### `WorkflowStepper`

- 업로드, 검증, 심사, 리포트 단계를 표시합니다.
- 현재 단계는 pulse animation으로 표시합니다.
- 모바일에서는 세로 타임라인 형태로 전환됩니다.

### `ChatTranscript`

- `messages` 배열을 그대로 렌더링합니다.
- assistant 메시지는 persona badge와 함께 왼쪽 정렬됩니다.
- user 메시지는 오른쪽 정렬됩니다.
- 최신 `followup_judge` 이벤트는 마지막 user 메시지에 `AnswerFeedbackChip`으로 붙습니다.

### `InsightPanel`

- 오른쪽 고정 패널입니다.
- 데스크톱에서는 `sticky` + 내부 스크롤로 동작합니다.
- 탭 구조:
  - `검증`
  - `답변`
  - `리포트`
  - `로그`
- 긴 정보를 한 번에 쌓지 않고 필요한 정보만 보여줍니다.

### `VerificationPanel`

- `verification` 이벤트의 정적 체크리스트를 표시합니다.
- `data_verification` 이벤트의 수치 주장 검증 결과도 함께 표시합니다.

### `AnswerQualityPanel`

- `followup_judge` 이벤트의 `score`, `threshold`, `reason`, `needs_followup`을 시각화합니다.
- 점수는 답변 품질, 영향력, 꼬리질문 여부로 해석됩니다.

### `ReportPanel`

- `report` 이벤트를 최종 결과로 렌더링합니다.
- 표시 정보:
  - 종합 완성도
  - 평균 답변 품질
  - 검증 필요 수치 개수
  - 수치 데이터 검증 필요성
  - 취약점과 위험 점수
  - 마무리 제안

## Mock Review Mode

백엔드가 꺼져 있거나 `/upload`가 실패하면 자동으로 mock review mode가 실행됩니다.

사용되는 mock 데이터:

- `MOCK_VERIFICATION`
- `MOCK_DATA_VERIFICATION`
- `MOCK_QUESTIONS`
- `MOCK_REPORT`

mock mode는 다음 목적을 가집니다.

- 백엔드/API 키 없이 UI 데모 가능
- 스트리밍 메시지 UX 확인
- 답변 품질/리포트/검증 패널 동작 확인
- 발표나 UI 리뷰에서 안정적인 화면 재현

## Styling System

스타일 기준은 루트의 `design.md`입니다.

`styles.css`는 다음 원칙을 따릅니다.

- design token 기반 색상 사용
- product-grade operational UI
- 카드 중첩 최소화
- 오른쪽 정보 패널은 sticky + 내부 스크롤
- 모바일에서는 단일 컬럼과 세로 stepper 사용
- `prefers-reduced-motion` 환경에서는 animation 최소화

## Backend Contract

프론트가 기대하는 백엔드 API는 다음과 같습니다.

### Upload

```http
POST /upload
Content-Type: multipart/form-data
```

응답:

```json
{
  "thread_id": "uuid",
  "first_persona": "investor"
}
```

### Start Chat

```http
POST /chat/start
Content-Type: application/json
```

요청:

```json
{
  "thread_id": "uuid",
  "message": ""
}
```

### Continue Chat

```http
POST /chat
Content-Type: application/json
```

요청:

```json
{
  "thread_id": "uuid",
  "message": "사용자 답변"
}
```

응답은 모두 `data: {...}\n\n` 스트리밍 형식입니다.

## Testing

```bash
npm test          # 단발 실행
npm run test:watch  # watch 모드
```

Vitest + jsdom 환경에서 실행됩니다. 현재 `utils.ts`의 `parseSSEChunk`와 `routeDebugEvent`에 대한 11개 테스트가 포함됩니다.

## Development Notes

- 백엔드 이벤트 구조를 바꾸지 말고, UI 해석은 프론트에서 처리합니다.
- SSE 파싱 및 이벤트 라우팅 로직은 `utils.ts`에 분리하여 테스트 가능하게 유지합니다.
- 새 UI를 추가할 때는 먼저 `design.md`의 토큰과 컴포넌트 규칙을 확인합니다.
- `backend/`는 UI 작업에서 수정하지 않습니다.
- `dist/`, `node_modules/`, `*.tsbuildinfo`는 커밋하지 않습니다.
