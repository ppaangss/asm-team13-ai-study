import os
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
UPSTAGE_MODEL = os.getenv("UPSTAGE_MODEL", "solar-pro2")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
MAX_ROUNDS = int(os.getenv("MAX_ROUNDS", "6"))
