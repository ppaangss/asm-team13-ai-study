import logging
from langchain_core.messages import SystemMessage, HumanMessage
from app.core import llm
from app.prompts.templates import REPORTER_SYSTEM

logger = logging.getLogger(__name__)


def _format_for_report(transcript: list[dict], weaknesses: list[dict]) -> str:
    lines = ["[대화 기록]"]
    for t in transcript:
        tag = {"question": "질문", "answer": "답변", "feedback": "피드백"}.get(t.get("type"), t.get("type"))
        lines.append(f"- ({t.get('persona','')}/{tag}) {t.get('content','')}")
    lines.append("\n[도출된 허점]")
    for w in weaknesses:
        lines.append(f"- [{w.get('severity','')}] ({w.get('section','')}) {w.get('weakness_type','')}: {w.get('suggestion','')}")
    return "\n".join(lines)


def report(state: dict) -> dict:
    """전체 대화와 허점을 종합해 최종 리포트를 만든다."""
    weaknesses = state.get("weaknesses", [])
    transcript = state.get("transcript", [])
    try:
        model = llm.get_llm(temperature=0.3)
        res = model.invoke([
            SystemMessage(content=REPORTER_SYSTEM),
            HumanMessage(content=_format_for_report(transcript, weaknesses)),
        ])
        summary = res.content
    except Exception as e:
        logger.warning("리포트 요약 실패: %s", e)
        n_q = len([t for t in transcript if t.get("type") == "question"])
        summary = f"총 {n_q}개의 압박 질문과 {len(weaknesses)}개의 허점이 도출되었습니다."
    return {"final_report": {
        "summary": summary,
        "weaknesses": weaknesses,
        "questions": state.get("asked", []),
    }}
