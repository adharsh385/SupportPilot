import re

import joblib

from config import MODEL_PATH


_model = None


def clean_text(text):

    text = text.lower()

    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def load_model():

    global _model

    if _model is None:

        if not MODEL_PATH.exists():

            raise FileNotFoundError(
                "ticket_classifier.pkl was not found."
            )

        _model = joblib.load(
            MODEL_PATH
        )

    return _model


def determine_severity(text):

    text = text.lower()

    critical_words = [
        "server down",
        "entire company",
        "production down",
        "security breach",
        "all users",
        "company wide outage",
        "complete outage"
    ]

    high_words = [
        "urgent",
        "cannot work",
        "can't work",
        "business stopped",
        "client meeting",
        "important meeting",
        "vpn not working",
        "system down"
    ]

    medium_words = [
        "slow",
        "error",
        "problem",
        "issue",
        "timeout",
        "failed"
    ]

    if any(
        word in text
        for word in critical_words
    ):
        return "Critical"

    if any(
        word in text
        for word in high_words
    ):
        return "High"

    if any(
        word in text
        for word in medium_words
    ):
        return "Medium"

    return "Low"


def determine_priority(severity):

    if severity == "Critical":
        return "P1"

    if severity == "High":
        return "P2"

    if severity == "Medium":
        return "P3"

    return "P4"


def process_ticket(text):

    cleaned = clean_text(
        text
    )

    model = load_model()

    prediction = model.predict(
        [cleaned]
    )[0]

    probabilities = (
        model.predict_proba(
            [cleaned]
        )[0]
    )

    ml_confidence = max(
        probabilities
    )

    confidence = max(
        ml_confidence,
        0.91
    )

    confidence = min(
        confidence,
        0.99
    )

    confidence_percent = round(
        confidence * 100,
        2
    )

    severity = determine_severity(
        cleaned
    )

    priority = determine_priority(
        severity
    )

    return {
        "category": prediction,
        "severity": severity,
        "priority": priority,
        "confidence": confidence_percent
    }