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
    sections_by_persona: dict[str, list[str]]
    # {"investor": ["5. 수익 모델", "6. 시장 분석"], "cto": [...], "mentor": [...]}


# ── 검증 에이전트 스키마 ──────────────────────────────────────
class VerificationItem(BaseModel):
    label: str
    status: Literal["pass", "warn", "fail"]
    reason: str


class VerificationResult(BaseModel):
    items: list[VerificationItem]


# ── 꼬리 질문 판단 스키마 ──────────────────────────────────────
class FollowupJudge(BaseModel):
    needs_followup: bool
    score: int    # 0-100: 답변 핵심 커버율 (0=전혀 없음, 100=완벽히 답변)
    reason: str   # 판단 근거 (디버그용)


# ── ReAct 서브에이전트 스키마 ────────────────────────────────────
class PersonaFindings(BaseModel):
    persona: Literal["investor", "cto", "mentor"]
    assigned_sections: dict[str, str]   # 이 페르소나에 배분된 섹션들
    findings: str                        # 허점 분석 결과 (자유 텍스트)
    round: int


class OrchestratorReview(BaseModel):
    is_sufficient: bool
    follow_up_requests: dict[str, str]  # {persona: 보완 요청 내용} — 충분하면 {}


# ── LangGraph State ──────────────────────────────────────────
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
    # 꼬리 질문 필드
    followup_count: int
    current_persona: str
    needs_followup: bool
    # 디버그 로그 (개발자 모드용)
    debug_log: Annotated[list, operator.add]
    pending_debug: dict  # followup_judge 판정 후 꼬리질문 생성 전까지 임시 보관
    # 검증 에이전트 결과
    verification_results: list[dict]


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
    debug: dict | None = None  # 개발자 모드용 디버그 페이로드


class FinalReport(BaseModel):
    summary: str
    weaknesses: list[dict[str, Any]]
