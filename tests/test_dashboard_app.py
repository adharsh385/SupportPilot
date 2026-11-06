import pandas as pd
import pytest

import classifier
from classifier import process_ticket
from dashboard_app import (
    build_dashboard_frame,
    calculate_classifier_metrics,
    calculate_kpis,
    check_escalation,
    run_escalation_rule_checks,
)


def test_classifier_metrics_are_case_insensitive_and_weighted():
    metrics = calculate_classifier_metrics(
        ["VPN", "VPN", "Hardware", "Network"],
        ["vpn", "Network", "Hardware", "Network"],
    )

    assert metrics == {
        "accuracy": 75.0,
        "precision": 87.5,
        "recall": 75.0,
    }


@pytest.mark.parametrize(
    ("expected", "predicted"),
    [
        ([], []),
        (["VPN"], []),
        ([""], ["VPN"]),
    ],
)
def test_classifier_metrics_reject_invalid_labels(expected, predicted):
    with pytest.raises(ValueError):
        calculate_classifier_metrics(expected, predicted)


def test_kpis_use_measured_ticket_values():
    frame = pd.DataFrame(
        {
            "status": ["Resolved", "Open", "Escalated"],
            "resolution": ["Source: KB", "", "Knowledge article"],
            "ai_processing_time_seconds": [2.0, 4.0, None],
            "response_generation_time_seconds": [1.0, 2.0, None],
            "csat": [5.0, None, 4.0],
        }
    )

    kpis = calculate_kpis(frame)

    assert kpis["total_tickets"] == 3
    assert kpis["auto_resolution_rate"] == pytest.approx(100 / 3, abs=0.01)
    assert kpis["avg_ai_processing_time"] == 3.0
    assert kpis["avg_ai_response_time"] == 1.5
    assert kpis["customer_satisfaction"] == 4.5
    assert kpis["customer_satisfaction_pct"] == 90.0
    assert kpis["kb_coverage"] == pytest.approx(200 / 3, abs=0.01)


@pytest.mark.parametrize(
    "ticket",
    [
        {"priority": "Critical", "confidence": 95},
        {"severity": "Critical", "confidence": 95},
        {"priority": "P1", "confidence": 95},
        {"priority": "P3", "confidence": 69.9},
        {"priority": "P3", "confidence": 0.69},
        {"priority": "P3", "confidence": 95, "ai_response_succeeded": 0},
        {"priority": "P3", "confidence": 95, "human_requested": 1},
    ],
)
def test_escalation_flags_all_human_intervention_triggers(ticket):
    assert check_escalation(ticket) is True


def test_escalation_does_not_flag_ticket_at_confidence_threshold():
    assert check_escalation({"priority": "P3", "confidence": 70}) is False
    assert check_escalation({"priority": "P3", "confidence": 0.70}) is False


def test_dashboard_frame_does_not_treat_missing_reason_as_escalation():
    frame = build_dashboard_frame(
        pd.DataFrame(
            {
                "ticket_id": [1, 2],
                "status": ["Open", "Open"],
                "title": ["Routine issue", "Human request"],
                "category": ["Network", "Network"],
                "priority": ["P3", "P3"],
                "severity": ["Low", "Low"],
                "confidence": [95, 95],
                "created_at": [None, None],
                "resolution": [None, None],
                "escalation_reason": [None, None],
                "human_requested": [0, 1],
            }
        )
    )

    assert frame["requires_human_review"].tolist() == [False, True]


def test_escalation_rule_checks_match_agent_behavior():
    results = run_escalation_rule_checks()

    assert len(results) == 3
    assert all(result["Passed"] for result in results)


def test_classifier_confidence_reports_model_probability(monkeypatch):
    class FakeModel:
        def predict(self, texts):
            return ["Network"]

        def predict_proba(self, texts):
            return [[0.6, 0.4]]

    monkeypatch.setattr(classifier, "_model", FakeModel())

    result = process_ticket("internet connection problem")

    assert result["confidence"] == 60.0
