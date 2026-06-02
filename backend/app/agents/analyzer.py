import logging
from langchain_core.messages import SystemMessage, HumanMessage
from app.core import llm
from app.schemas import PersonaAnalysis
from app.prompts.templates import PERSONA_SYSTEM

logger = logging.getLogger(__name__)


def format_sections(sections: dict) -> str:
    return "\n\n".join(f"## {k}\n{v}" for k, v in sections.items())


def _analyze(state: dict, persona: str) -> dict:
    sections = state.get("sections", {})
    if not sections:
        return {"persona_analyses": [{"persona": persona, "findings": []}]}
    body = format_sections(sections)
    try:
        model = llm.get_llm(temperature=0.3).with_structured_output(PersonaAnalysis)
        result = model.invoke([
            SystemMessage(content=PERSONA_SYSTEM[persona]),
            HumanMessage(content=f"다음 기획서를 분석하세요.\n\n{body}"),
        ])
        findings = [f.model_dump() for f in result.findings]
    except Exception as e:
        logger.warning("%s 분석 실패: %s", persona, e)
        findings = []
    return {"persona_analyses": [{"persona": persona, "findings": findings}]}


def investor_analyze(state: dict) -> dict:
    return _analyze(state, "투자자")


def cto_analyze(state: dict) -> dict:
    return _analyze(state, "CTO")


def mentor_analyze(state: dict) -> dict:
    return _analyze(state, "멘토")
