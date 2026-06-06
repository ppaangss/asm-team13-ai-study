# Design System: 기획서 검증 에이전트

이 문서는 Vite React 프론트엔드의 단일 디자인 기준이다. 모든 UI 변경은 이 문서를 먼저 확인하고, 새 스타일이나 컴포넌트가 필요하면 기존 토큰과 규칙을 확장한다.

## Product Principles

- **Clarity first**: 사용자는 업로드 상태, 현재 심사 단계, 어떤 페르소나가 질문 중인지 즉시 이해해야 한다.
- **Pressure-test feel**: UI는 발표 전 모의 심사장의 긴장감을 주되, 위협적이기보다 집중을 돕는 톤을 유지한다.
- **Trust by structure**: 검증 결과, 근거, 리포트, 위험도를 명확한 구조로 보여 신뢰감을 만든다.
- **Low cognitive load**: 화면은 업로드, 질의응답, 검증, 리포트의 네 흐름만 드러낸다. 설명 문구는 짧게 유지한다.
- **Operational product**: 랜딩 페이지처럼 꾸미지 않고, 반복 사용 가능한 업무 도구처럼 조용하고 정교하게 구성한다.

## Design Tokens

### Color

| Token | Value | Usage |
| --- | --- | --- |
| `--color-bg` | `#f6f7f9` | 전체 앱 배경 |
| `--color-surface` | `#ffffff` | 패널, 카드, 입력 영역 |
| `--color-surface-muted` | `#eef1f5` | 보조 배경, 비활성 영역 |
| `--color-ink` | `#101318` | 주요 텍스트 |
| `--color-ink-muted` | `#5d6675` | 설명, 메타 텍스트 |
| `--color-line` | `#d9dee7` | 경계선 |
| `--color-primary` | `#2457e6` | 주요 CTA, 사용자 메시지 |
| `--color-primary-strong` | `#183fb4` | CTA hover |
| `--color-success` | `#16845b` | pass, confirmed |
| `--color-warning` | `#b7791f` | warn, unconfirmed |
| `--color-danger` | `#cf3f4a` | fail, contradicted, high risk |
| `--color-info` | `#2870a6` | 진행, 시스템 정보 |

### Persona Accents

| Persona | Accent | Usage |
| --- | --- | --- |
| Investor | `#7c4dff` | 시장성, 수익성, 투자자 메시지 |
| CTO | `#047c8a` | 기술 실현성, 아키텍처 메시지 |
| Mentor | `#c46619` | PMF, 범위, 전략 메시지 |
| Reporter | `#2457e6` | 오케스트레이터, 최종 리포트 |

### Typography

- Font stack: `Pretendard Variable`, `Pretendard`, `Inter`, `system-ui`, `sans-serif`.
- Display: 32px / 40px, weight 760. 첫 화면 제목에만 사용한다.
- Section title: 22px / 30px, weight 720.
- Panel title: 16px / 24px, weight 700.
- Body: 15px / 24px, weight 450.
- Caption: 12px / 18px, weight 600.
- Letter spacing은 `0`을 기본으로 한다. 좁은 글자 간격은 사용하지 않는다.

### Spacing, Radius, Shadow

- Spacing scale: `4, 8, 12, 16, 20, 24, 32, 40, 56`.
- Compact panels use `16px` or `20px` padding.
- App shell gutters use `24px` desktop, `16px` tablet, `12px` mobile.
- Radius:
  - Small controls: `8px`
  - Panels/cards: `10px`
  - Pills/message bubbles: `18px`
- Shadow:
  - Panel: `0 10px 30px rgba(16, 19, 24, 0.08)`
  - Floating input: `0 14px 40px rgba(16, 19, 24, 0.12)`
- Z-index:
  - Base: `1`
  - Sticky bars: `20`
  - Drawer: `40`
  - Toast/modal: `60`

### Motion

- Fast interaction: `160ms ease-out`.
- Panel entrance: `240ms cubic-bezier(.2,.8,.2,1)`.
- Streaming message reveal: subtle opacity and y transition only.
- Respect `prefers-reduced-motion: reduce`; disable nonessential transforms and long transitions.

## Layout System

- **App shell**: fixed-width operational surface with a left workflow column and right insight column on desktop.
- **Upload view**: no marketing hero. Show product title, three persona capability cards, and a focused file dropzone.
- **Review view**: chat transcript is primary. Verification, progress, and debug/report panels are secondary.
- **Report view**: final report appears as a structured result panel with score, weaknesses, and next actions.
- Breakpoints:
  - Desktop: `>= 1100px`, two-column layout.
  - Tablet: `768px - 1099px`, stacked panels.
  - Mobile: `< 768px`, single column, compact spacing, sticky input.

## Components

### Button

- Primary buttons use blue fill, white text, and a leading lucide icon when action intent benefits from it.
- Secondary buttons use muted surface fill and ink text.
- Destructive actions use danger color only when data is actually removed.
- Button height: 44px default, 36px compact.

### Icon Button

- Use lucide icons for upload, send, refresh, report, debug, and status actions.
- Always provide `aria-label`.
- Size: 36px square, radius 8px.

### File Dropzone

- Shows idle, selected, uploading, success, and error states.
- Accepts `.txt`, `.md`, `.pdf`, `.docx`.
- Primary upload action remains disabled until a file is selected.

### Chat Message

- Assistant messages align left with persona accent border.
- User messages align right with primary fill.
- Each assistant message includes persona badge, short label, and streamed content.
- Message width is constrained to avoid long unreadable lines.

### Persona Badge

- Badge contains icon, name, and accent color.
- Use the same persona mapping everywhere:
  - Investor: 깐깐한 투자자
  - CTO: 냉철한 CTO
  - Mentor: 예리한 멘토
  - Reporter: 오케스트레이터

### Status Badge

- Status color is always paired with text.
- Static verification statuses: `pass`, `warn`, `fail`.
- Data verification statuses: `confirmed`, `unconfirmed`, `contradicted`.

### Progress Stepper

- Shows Upload, Verification, Review, Report.
- Active state uses primary color; completed state uses success color.
- Do not animate progress in a way that implies backend completion before events arrive.

### Verification Panel

- Separate static checklist from data claim verification.
- Show counts and individual reasons.
- Empty state should say verification will appear after analysis starts.

### Debug Drawer

- Hidden by default behind a developer mode toggle.
- Shows follow-up judge scores, thresholds, reasons, and generated follow-up questions.
- Never mix debug events into the normal user transcript.

### Report Summary

- Shows final score, summary, weakness list, risk level, and suggestions.
- High-risk weakness items must be visually scannable and not buried in prose.

## Content Rules

- UI language is Korean, concise, and product-like.
- Prefer direct labels: `기획서 업로드`, `심사 시작`, `답변 보내기`, `최종 리포트`.
- Avoid visible instructional walls. Put long explanations in tooltips or empty states only when needed.
- Persona copy may be sharp, but system UI copy stays calm.

## Accessibility Rules

- Every interactive control needs keyboard focus styling.
- Never rely on color alone for status; include text labels.
- Maintain readable contrast for text and badges.
- Keep mobile tap targets at least 36px high.
- Streaming content must remain readable if animation is disabled.
- Inputs and buttons must have accessible labels.

## Implementation Rules

- All new React UI must use this design system.
- Add or change design tokens before adding one-off colors, shadows, spacing, or motion values.
- Do not add UI cards inside other cards.
- Do not touch `backend/` for UI-only work.
- POST streaming endpoints must be consumed with `fetch` + `ReadableStream`, not `EventSource`.
- Backend event shape is treated as stable:
  - `{ token, node, done, is_final, debug }`
- Debug/report events render outside the normal chat transcript.
