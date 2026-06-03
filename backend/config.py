from dotenv import load_dotenv
import os

load_dotenv()

UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
MODEL_NAME = "solar-pro2"
MAX_ROUNDS = 10
MAX_FOLLOWUPS = 3
PERSONA_ORDER = ["investor", "cto", "mentor"]

# RAG 설정
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "data/chroma_db")
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
EXAMPLES_DIR = os.getenv("EXAMPLES_DIR", "data/examples")
PERSONA_KNOWLEDGE_DIR = os.getenv("PERSONA_KNOWLEDGE_DIR", "knowledge")
PERSONA_CHROMA_DB_PATH = os.getenv("PERSONA_CHROMA_DB_PATH", "data/persona_chroma_db")

# LangSmith 트레이싱 (env var 로드 후 자동 활성화됨)
# LANGSMITH_TRACING, LANGSMITH_API_KEY, LANGSMITH_PROJECT 은 .env 에서 관리
