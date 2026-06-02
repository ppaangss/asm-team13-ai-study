from types import SimpleNamespace
import pytest
from app.schemas import PersonaAnalysis, Finding, AnswerFeedback


class _FakeStructured:
    def __init__(self, value):
        self._value = value

    def invoke(self, _messages):
        return self._value


class FakeLLM:
    """with_structured_output 대상 모델에 따라 미리 정한 인스턴스를 반환한다."""

    def with_structured_output(self, model):
        name = model.__name__
        if name == "PersonaAnalysis":
            value = PersonaAnalysis(findings=[Finding(
                section="차별성", weakness_type="차별성 부족", severity="상",
                rationale="유사 서비스 존재 가능", question="이미 OOO 있지 않나요?", suggestion="차별점 명시",
            )])
        elif name == "AnswerFeedback":
            value = AnswerFeedback(assessment="보완필요", feedback="근거가 약합니다.", follow_up_hint="데이터 제시")
        else:
            value = model()
        return _FakeStructured(value)

    def invoke(self, _messages):
        return SimpleNamespace(content="종합 요약입니다.")


@pytest.fixture
def fake_llm(monkeypatch):
    from app.core import llm
    monkeypatch.setattr(llm, "get_llm", lambda *a, **k: FakeLLM())
    return FakeLLM()
