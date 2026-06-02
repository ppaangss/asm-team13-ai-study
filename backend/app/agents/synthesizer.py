def synthesize(state: dict) -> dict:
    """3개 페르소나 분석 결과를 종합 허점 목록과 질문 풀로 합친다(fan-in, 순수)."""
    weaknesses: list[dict] = []
    pool: list[dict] = []
    for analysis in state.get("persona_analyses", []):
        persona = analysis["persona"]
        for f in analysis.get("findings", []):
            weaknesses.append({
                "persona": persona,
                "section": f["section"],
                "weakness_type": f["weakness_type"],
                "severity": f["severity"],
                "rationale": f["rationale"],
                "suggestion": f["suggestion"],
            })
            pool.append({
                "persona": persona,
                "target_section": f["section"],
                "weakness_type": f["weakness_type"],
                "question": f["question"],
                "intent": f["rationale"],
            })
    return {"weaknesses": weaknesses, "question_pool": pool}
