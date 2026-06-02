from langchain_core.language_models.chat_models import BaseChatModel
from app.core import config


def get_llm(temperature: float = 0.0, provider: str | None = None) -> BaseChatModel:
    """설정된 공급자에 맞는 Chat 모델을 반환한다.

    기본은 Anthropic Claude. LLM_PROVIDER=upstage 로 Solar 교체.
    """
    name = (provider or config.LLM_PROVIDER).lower()
    if name == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=config.ANTHROPIC_MODEL,
            temperature=temperature,
            api_key=config.ANTHROPIC_API_KEY or None,
        )
    if name == "upstage":
        from langchain_upstage import ChatUpstage
        return ChatUpstage(model=config.UPSTAGE_MODEL, temperature=temperature)
    if name == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=config.OPENAI_MODEL,
            temperature=temperature,
            api_key=config.OPENAI_API_KEY or None,
        )
    raise ValueError(f"알 수 없는 LLM_PROVIDER: {name}")
