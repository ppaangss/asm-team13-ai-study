from dotenv import load_dotenv
import os

load_dotenv()

UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY", "")
MODEL_NAME = "solar-pro2"
MAX_ROUNDS = 6
PERSONA_ORDER = ["investor", "cto", "mentor"]

# LangSmith 트레이싱 (env var 로드 후 자동 활성화됨)
# LANGSMITH_TRACING, LANGSMITH_API_KEY, LANGSMITH_PROJECT 은 .env 에서 관리
