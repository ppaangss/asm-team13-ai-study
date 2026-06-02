from langgraph.types import interrupt

PERSONA_ORDER = ["투자자", "CTO", "멘토"]


def select_next_question(state: dict) -> dict:
    """페르소나 로테이션으로 다음 질문 1개를 고른다(순수).

    이번 라운드 담당 페르소나의 미사용 질문을 우선 선택하고,
    없으면 아무 미사용 질문, 그것도 없으면 일반 질문으로 폴백한다.
    """
    asked = state.get("asked", [])
    pool = state.get("question_pool", [])
    target = PERSONA_ORDER[len(asked) % len(PERSONA_ORDER)]
    used = {q["question"] for q in asked}

    for q in pool:
        if q["persona"] == target and q["question"] not in used:
            return q
    for q in pool:
        if q["question"] not in used:
            return q
    return {
        "persona": target,
        "target_section": "",
        "weakness_type": "",
        "question": f"{target} 관점에서 아직 충분히 설명되지 않은 부분을 한 가지 짚어 보완해 주세요.",
        "intent": "추가 점검",
    }


def ask(state: dict) -> dict:
    """다음 질문을 고르고 interrupt로 사용자 답변을 대기한다(human-in-the-loop)."""
    q = select_next_question(state)
    answer = interrupt({"persona": q["persona"], "question": q["question"]})
    return {
        "asked": [q],
        "current_question": q,
        "current_answer": answer,
        "transcript": [
            {"role": "assistant", "type": "question", "persona": q["persona"], "content": q["question"]},
            {"role": "user", "type": "answer", "content": answer},
        ],
    }
