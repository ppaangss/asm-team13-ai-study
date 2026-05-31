from pydantic import BaseModel
from typing import Annotated, Any
import operator
from typing_extensions import TypedDict


# ── LangGraph State ──────────────────────────────────────────
class PlannerState(TypedDict):
    sections: dict[str, str]
    messages: Annotated[list[dict], operator.add]
    round: int
    persona_outputs: Annotated[list[dict], operator.add]
    final_report: str


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


class FinalReport(BaseModel):
    summary: str
    weaknesses: list[dict[str, Any]]
