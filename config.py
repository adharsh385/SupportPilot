from pathlib import Path
import os

from dotenv import load_dotenv


BASE_DIR = Path(
    __file__
).resolve().parent

load_dotenv(BASE_DIR / ".env")


MODEL_DIR = BASE_DIR / "models"

MODEL_PATH = (
    MODEL_DIR
    / "ticket_classifier.pkl"
)


DATABASE_PATH = (
    BASE_DIR
    / "tickets.db"
)


KNOWLEDGE_BASE_PATH = (
    BASE_DIR
    / "data"
    / "knowledge_base.json"
)


TOP_K = 3

MIN_RELEVANCE = 0.03

try:
    ESCALATION_CONFIDENCE_THRESHOLD = float(
        os.getenv("ESCALATION_CONFIDENCE_THRESHOLD", "55")
    )
except ValueError:
    ESCALATION_CONFIDENCE_THRESHOLD = 55.0

try:
    AI_RESPONSE_TIMEOUT_SECONDS = max(
        1, int(os.getenv("AI_RESPONSE_TIMEOUT_SECONDS", "30"))
    )
except ValueError:
    AI_RESPONSE_TIMEOUT_SECONDS = 30

try:
    AI_RESPONSE_RETRIES = max(0, int(os.getenv("AI_RESPONSE_RETRIES", "1")))
except ValueError:
    AI_RESPONSE_RETRIES = 1


MODEL_DIR.mkdir(
    parents=True,
    exist_ok=True
)
