# asm-team13-ai-study

기획서를 업로드하면 투자자·CTO·멘토 페르소나가 압박 질문을 던지고, 답변에 피드백을 준 뒤
위험도 포함 종합 리포트를 만드는 모의 심사 챗봇.

## 구조

```
frontend/   Streamlit UI (코인베이스/카카오 스타일)
backend/    LangGraph 백엔드 (app/ 패키지, templates/, tests/)
```

프론트엔드는 `backend/app` 의 `parse_proposal` / `build_graph` 등을 import 해서 사용한다.

## 실행

```
uv sync
cp .env.example .env   # ANTHROPIC_API_KEY 등 입력 (기본 LLM_PROVIDER=anthropic)
uv run streamlit run frontend/app.py
```

- 백엔드 테스트: `uv run pytest -q`
- 백엔드 단독 UI(선택): `uv run streamlit run backend/ui.py`

## LLM 교체

`.env` 에서 `LLM_PROVIDER=upstage` 로 변경하면 Solar 로 전환된다. (anthropic / upstage / openai 지원)

## 입력 양식

`backend/templates/기획서_양식.md` 의 마크다운 헤딩(`#`, `##`) 구조를 따른 txt/md 파일을 업로드한다.
