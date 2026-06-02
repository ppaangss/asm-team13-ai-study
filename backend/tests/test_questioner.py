from app.agents.questioner import select_next_question, PERSONA_ORDER


def _pool():
    return [
        {"persona": "투자자", "target_section": "차별성", "weakness_type": "t", "question": "투자자Q", "intent": ""},
        {"persona": "CTO", "target_section": "기술스택", "weakness_type": "t", "question": "CTO_Q", "intent": ""},
        {"persona": "멘토", "target_section": "MVP범위", "weakness_type": "t", "question": "멘토Q", "intent": ""},
    ]


def test_rotation_starts_with_investor():
    assert PERSONA_ORDER[0] == "투자자"
    q = select_next_question({"asked": [], "question_pool": _pool()})
    assert q["persona"] == "투자자"


def test_rotation_advances_to_next_persona():
    state = {"asked": [{"persona": "투자자", "question": "투자자Q"}], "question_pool": _pool()}
    q = select_next_question(state)
    assert q["persona"] == "CTO"


def test_generic_fallback_when_pool_empty():
    q = select_next_question({"asked": [], "question_pool": []})
    assert q["persona"] == "투자자"
    assert q["question"]  # 비어 있지 않은 일반 질문
