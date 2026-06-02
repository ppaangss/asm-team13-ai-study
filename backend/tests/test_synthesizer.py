from app.agents.synthesizer import synthesize


def test_flattens_findings_into_weaknesses_and_pool():
    state = {"persona_analyses": [
        {"persona": "투자자", "findings": [
            {"section": "차별성", "weakness_type": "차별성 부족", "severity": "상",
             "rationale": "유사 서비스 존재", "question": "이미 OOO 있지 않나요?", "suggestion": "차별점 명시"},
        ]},
        {"persona": "CTO", "findings": []},
    ]}
    out = synthesize(state)
    assert len(out["weaknesses"]) == 1
    assert out["weaknesses"][0]["persona"] == "투자자"
    assert out["weaknesses"][0]["severity"] == "상"
    assert len(out["question_pool"]) == 1
    assert out["question_pool"][0]["persona"] == "투자자"
    assert out["question_pool"][0]["question"] == "이미 OOO 있지 않나요?"
