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
    # 답변 신뢰도 검증 결과 (라운드마다 누적)
    answer_fact_checks: Annotated[list[dict], operator.add]
    # 세션 설정 (업로드 시 사용자 입력)
    max_rounds: int
    followup_thresholds: dict


# ── API 요청/응답 ─────────────────────────────────────────────
class UploadResponse(BaseModel):
    thread_id: str
    first_persona: str = "investor"


class ChatRequest(BaseModel):
    thread_id: str
    message: str
    max_rounds: int | None = None
    followup_threshold: int | None = None


class ChatEvent(BaseModel):
    token: str
    node: str
    done: bool
    is_final: bool = False
    debug: dict | None = None  # 개발자 모드용 디버그 페이로드


# ── 수치 데이터 검증 스키마 ───────────────────────────────────
class DataClaimList(BaseModel):
    claims: list[str]   # 검증 대상 수치 주장 목록 (최대 4개)


class DataVerificationItem(BaseModel):
    claim: str                                                          # 원문 수치 주장
    status: Literal["confirmed", "unconfirmed", "contradicted"]        # 검증 결과
    reason: str                                                         # 판단 근거
    source: str                                                         # 검색 출처


class DataVerificationResult(BaseModel):
    items: list[DataVerificationItem]


class WeaknessItem(BaseModel):
    section: str        # 섹션명
    issue: str          # 핵심 허점
    risk: Literal["상", "중", "하"]  # 위험도
    risk_score: int     # 위험 점수 0~100 (높을수록 위험)
    suggestion: str     # 보완 제안


class FinalReport(BaseModel):
    summary: str                        # 전반적 평가 (2~3문장)
    overall_score: int                  # 종합 완성도 점수 0~100 (높을수록 좋음)
    weaknesses: list[WeaknessItem]      # 섹션별 허점 목록
    closing: str                        # 마무리 한마디
