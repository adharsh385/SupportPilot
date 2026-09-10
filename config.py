import os
from pathlib import Path


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)


DATABASE_PATH = os.path.join(
    BASE_DIR,
    "tickets.db"
)


MODEL_PATH = Path(
    BASE_DIR,
    "data",
    "ticket_classifier.joblib"
)


SECRET_KEY = os.environ.get(
    "FLASK_SECRET_KEY",
    "development-secret-key-change-me-32"
)


JWT_EXPIRATION_MINUTES = int(
    os.environ.get(
        "JWT_EXPIRATION_MINUTES",
        "60"
    )
)


KNOWLEDGE_BASE_PATH = os.path.join(
    BASE_DIR,
    "data",
    "knowledge_base.json"
)


TOP_K = 3


MIN_RELEVANCE = 0.05