import logging
from langchain_core.messages import SystemMessage, HumanMessage
from app.core import llm
from app.schemas import AnswerFeedback
from app.prompts.templates import EVALUATOR_SYSTEM

logger = logging.getLogger(__name__)


def evaluate(state: dict) -> dict:
    """직전 질문에 대한 사용자 답변을 평가하고 피드백을 남긴다. round 증가."""
    q = state.get("current_question", {})
    answer = state.get("current_answer", "")
    persona = q.get("persona", "심사위원")
    try:
        model = llm.get_llm(temperature=0.3).with_structured_output(AnswerFeedback)
        fb = model.invoke([
            SystemMessage(content=EVALUATOR_SYSTEM),
            HumanMessage(content=f"[질문] {q.get('question','')}\n[답변] {answer}"),
        ])
        feedback = {"assessment": fb.assessment, "content": fb.feedback, "follow_up": fb.follow_up_hint}
    except Exception as e:
        logger.warning("답변 평가 실패: %s", e)
        feedback = {"assessment": "보완필요", "content": "답변을 평가하지 못했습니다.", "follow_up": ""}
    return {
        "transcript": [{
            "role": "assistant", "type": "feedback", "persona": persona,
            "assessment": feedback["assessment"], "content": feedback["content"],
            "follow_up": feedback["follow_up"],
        }],
        "round": state.get("round", 0) + 1,
    }
