from pathlib import Path


BASE_DIR = Path(
    __file__
).resolve().parent


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


MODEL_DIR.mkdir(
    parents=True,
    exist_ok=True
)