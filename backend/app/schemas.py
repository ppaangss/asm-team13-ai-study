import operator
from typing import Annotated, Literal
from typing_extensions import TypedDict
from pydantic import BaseModel, Field

Persona = Literal["투자자", "CTO", "멘토"]
Severity = Literal["상", "중", "하"]


class Finding(BaseModel):
    section: str = Field(description="대상 섹션 (예: 문제정의)")
    weakness_type: str = Field(description="허점 유형 (예: 차별성 부족)")
    severity: Severity = Field(description="위험도 상/중/하")
    rationale: str = Field(description="왜 약점인지 한두 문장")
    question: str = Field(description="이 약점을 찌르는 날카로운 압박 질문 1개")
    suggestion: str = Field(description="보완 방향 제안")


class PersonaAnalysis(BaseModel):
    findings: list[Finding] = Field(default_factory=list)


class AnswerFeedback(BaseModel):
    assessment: Literal["충분", "보완필요", "회피"] = Field(description="답변 평가")
    feedback: str = Field(description="건설적 피드백")
    follow_up_hint: str = Field(default="", description="다음에 보완하면 좋을 점")


class AgentState(TypedDict):
    sections: dict                                          # 파싱된 섹션
    persona_analyses: Annotated[list[dict], operator.add]   # fan-out 결과 누적
    weaknesses: list[dict]                                  # fan-in 종합 허점
    question_pool: list[dict]                               # 질문 풀
    asked: Annotated[list[dict], operator.add]              # 던진 질문 누적
    transcript: Annotated[list[dict], operator.add]         # Q/A/피드백 기록
    current_question: dict                                  # 직전 질문 (evaluate 입력)
    current_answer: str                                     # interrupt resume 답변
    round: int
    max_rounds: int
    final_report: dict
