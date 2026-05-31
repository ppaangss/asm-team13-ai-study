from dotenv import load_dotenv
import os

load_dotenv()

UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY", "")
MODEL_NAME = "solar-pro2"
MAX_ROUNDS = 6
PERSONA_ORDER = ["investor", "cto", "mentor"]
