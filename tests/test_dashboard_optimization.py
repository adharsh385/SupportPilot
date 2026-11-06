import pytest
import time
from datetime import date

import app as webapp
import database
from agent import EscalationAgent


@pytest.fixture
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(
        database,
        "DATABASE_PATH",
        tmp_path / "dashboard-test.db",
    )
    database.initialize_database()
    webapp.app.config.update(TESTING=True)
    yield


def authenticated_client():
    client = webapp.app.test_client()
    with client.session_transaction() as session:
        session.update({
            "user_id": 1,
            "username": "test-user",
            "email": "test@example.com",
        })
    return client


def add_ticket(status="Open", **updates):
    ticket_id = database.save_ticket({
        "employee_name": "Test User",
        "email": "test@example.com",
        "department": "IT",
        "title": "Test issue",
        "description": "Test description",
        "category": "Network",
        "severity": "Low",
        "priority": "P4",
        "confidence": 90,
        "status": status,
    })
    if updates:
        database.update_ticket(ticket_id, **updates)
    return ticket_id


def test_dashboard_api_requires_authentication(isolated_database):
    client = webapp.app.test_client()

    assert client.get("/dashboard").status_code == 302
    assert client.get("/api/dashboard/metrics/").status_code == 401
    assert client.get("/api/dashboard/chart/").status_code == 401


def test_empty_dashboard_metrics_and_chart_are_safe(isolated_database):
    client = authenticated_client()

    metrics = client.get("/api/dashboard/metrics/").get_json()["metrics"]
    chart = client.get("/api/dashboard/chart/").get_json()["days"]
    workflow = client.get("/api/dashboard/escalation/").get_json()["workflow"]

    assert metrics["total_tickets"] == 0
    assert metrics["total_tickets_today"] == 0
    assert metrics["ai_resolution_rate"] == 0
    assert metrics["average_resolution_time_seconds"] is None
    assert metrics["resolution_time_samples"] == 0
    assert metrics["resolved_without_timing"] == 0
    assert metrics["user_satisfaction"] is None
    assert len(chart) == 7
    assert sum(day["received"] for day in chart) == 0
    assert sum(day["resolved"] for day in chart) == 0
    assert workflow == {
        "classified": 0,
        "automatically_resolved": 0,
        "escalated": 0,
        "waiting_validation": 0,
    }


def test_dashboard_kpis_and_chart_use_database_values(isolated_database):
    add_ticket(
        "Resolved",
        resolution="Source: KB article",
        ai_processing_time_seconds=2,
        response_generation_time_seconds=1.5,
        ai_response_succeeded=True,
        ai_resolved=True,
        validation_status="Validated",
        csat=4,
    )
    add_ticket(
        "Escalated",
        resolution="",
        ai_processing_time_seconds=3,
        response_generation_time_seconds=2.5,
        ai_response_succeeded=False,
        escalated=True,
        escalation_reason="AI response failed",
        validation_status="Failed",
    )
    client = authenticated_client()

    metrics = client.get("/api/dashboard/metrics/").get_json()["metrics"]
    days = client.get("/api/dashboard/chart/").get_json()["days"]
    workflow = client.get("/api/dashboard/escalation/").get_json()["workflow"]

    assert metrics["total_tickets"] == 2
    assert metrics["total_tickets_today"] == 2
    assert metrics["ai_resolution_rate"] == 50
    assert metrics["resolution_success_rate"] == 50
    assert metrics["average_response_time_seconds"] == 2
    assert metrics["resolution_time_samples"] == 1
    assert metrics["resolved_without_timing"] == 0
    assert metrics["user_satisfaction"] == 4
    assert metrics["response_attempts"] == 2
    assert metrics["successful_responses"] == 1
    assert metrics["failed_responses"] == 1
    assert sum(day["received"] for day in days) == 2
    assert sum(day["resolved"] for day in days) == 1
    assert workflow["classified"] == 2
    assert workflow["automatically_resolved"] == 1
    assert workflow["escalated"] == 1


def test_average_resolution_time_uses_precise_utc_timestamps(
    isolated_database,
):
    ticket_id = add_ticket()
    connection = database.get_connection()
    connection.execute(
        """
        UPDATE tickets
        SET status = 'Resolved',
            created_at = '2026-10-06T10:00:00.000000+00:00',
            resolved_at = '2026-10-06T10:02:03.456789+00:00'
        WHERE ticket_id = ?
        """,
        (ticket_id,),
    )
    connection.commit()
    connection.close()

    metrics = authenticated_client().get(
        "/api/dashboard/metrics/"
    ).get_json()["metrics"]

    assert metrics["average_resolution_time_seconds"] == 123.46


def test_resolving_ticket_records_dashboard_resolution_time(
    isolated_database,
):
    ticket_id = add_ticket()
    database.update_ticket(ticket_id, status="Resolved")

    metrics = authenticated_client().get(
        "/api/dashboard/metrics/"
    ).get_json()["metrics"]

    assert metrics["resolution_time_samples"] == 1
    assert metrics["average_resolution_time_seconds"] is not None
    assert metrics["resolved_without_timing"] == 0


def test_legacy_resolved_ticket_is_reported_without_fabricating_time(
    isolated_database,
):
    ticket_id = add_ticket("Resolved")
    connection = database.get_connection()
    connection.execute(
        "UPDATE tickets SET resolved_at = NULL WHERE ticket_id = ?",
        (ticket_id,),
    )
    connection.commit()
    connection.close()

    metrics = authenticated_client().get(
        "/api/dashboard/metrics/"
    ).get_json()["metrics"]

    assert metrics["average_resolution_time_seconds"] is None
    assert metrics["resolution_time_samples"] == 0
    assert metrics["resolved_without_timing"] == 1


def test_chart_falls_back_to_latest_active_week_and_labels_legacy_resolutions(
    isolated_database,
):
    ticket_id = add_ticket("Resolved", ai_resolved=True)
    connection = database.get_connection()
    connection.execute(
        "UPDATE tickets SET created_at = ?, resolved_at = NULL "
        "WHERE ticket_id = ?",
        ("2026-09-28 10:00:00", ticket_id),
    )
    connection.commit()
    connection.close()

    chart = database.get_weekly_ticket_counts(today=date(2026, 10, 6))

    assert chart["uses_latest_activity_week"] is True
    assert chart["period_start"] == "2026-09-28"
    assert chart["legacy_resolution_date_fallbacks"] == 1
    assert sum(day["received"] for day in chart["days"]) == 1
    assert sum(day["resolved"] for day in chart["days"]) == 1


def test_satisfaction_form_saves_score_for_resolved_ticket(
    isolated_database,
):
    ticket_id = add_ticket("Resolved", ai_resolved=True)
    client = authenticated_client()

    response = client.post(
        f"/tickets/{ticket_id}/satisfaction",
        data={"csat": "4"},
    )

    assert response.status_code == 302
    assert database.get_all_tickets()[0]["csat"] == 4
    assert database.get_dashboard_metrics()["user_satisfaction"] == 4


def test_satisfaction_form_rejects_invalid_score(isolated_database):
    ticket_id = add_ticket("Resolved", ai_resolved=True)
    client = authenticated_client()

    response = client.post(
        f"/tickets/{ticket_id}/satisfaction",
        data={"csat": "not-a-score"},
    )

    assert response.status_code == 400
    assert database.get_all_tickets()[0]["csat"] is None


def test_monitoring_error_rate_excludes_authentication_denials(
    isolated_database,
):
    database.record_api_metric("/api/dashboard/metrics/", 3, 401)
    database.record_api_metric("/api/dashboard/metrics/", 8, 500)

    metrics = database.get_dashboard_metrics()

    assert metrics["api_error_rate"] == 50


def test_classifier_evaluation_uses_isolated_sample_data(
    isolated_database, monkeypatch
):
    def predict(text):
        lowered = text.lower()
        if "vpn" in lowered:
            category = "VPN"
        elif any(word in lowered for word in ("wifi", "wi-fi", "internet")):
            category = "Network"
        elif "password" in lowered:
            category = "Password"
        elif any(word in lowered for word in ("application", "software")):
            category = "Software"
        elif any(
            word in lowered for word in ("laptop", "keyboard", "monitor")
        ):
            category = "Hardware"
        else:
            category = "System"
        return {"category": category}

    monkeypatch.setattr(webapp, "process_ticket", predict)
    client = authenticated_client()

    evaluation_response = client.get("/api/dashboard/classifier-evaluation/")
    evaluation = evaluation_response.get_json()["evaluation"]

    assert evaluation["dataset"] == "isolated_sample_test_data"
    assert evaluation["samples"] == 12
    assert evaluation["accuracy"] == 100
    assert evaluation["precision"] == 100
    assert evaluation["recall"] == 100
    assert evaluation["f1_score"] == 100
    assert database.get_all_tickets() == []


def test_real_classifier_falls_back_to_escalation_when_kb_missing(
    isolated_database,
):
    client = authenticated_client()

    response = client.post("/ticket", json={
        "employee_name": "Test User",
        "email": "test@example.com",
        "department": "IT",
        "title": "VPN connection not working",
        "description": "Corporate VPN connection is timing out",
    })

    assert response.status_code == 200
    result = response.get_json()
    assert result["classification"]["category"] == "VPN"
    assert result["ticket"]["status"] == "Escalated"
    assert result["escalation"]["reason"] == "AI response failed"
    saved_ticket = database.get_all_tickets()[0]
    assert saved_ticket["ai_response_succeeded"] == 0
    assert saved_ticket["escalated"] == 1


@pytest.mark.parametrize(
    ("ticket", "validation", "threshold", "reason"),
    [
        ({"confidence": 30}, {"valid": True}, 55, "AI confidence"),
        ({"human_requested": True}, {"valid": True}, 55, "Human support"),
        (
            {"resolution_failed": True},
            {"valid": False},
            55,
            "AI response failed",
        ),
        ({"confidence": 90}, {"valid": False}, 55, "validation"),
    ],
)
def test_escalation_rules_cover_requested_failure_and_confidence(
    ticket, validation, threshold, reason
):
    result = EscalationAgent(threshold).run(ticket, validation)

    assert result["escalate"] is True
    assert reason.lower() in result["reason"].lower()


def test_failed_ai_response_is_saved_as_escalated(
    isolated_database, monkeypatch
):
    monkeypatch.setattr(webapp, "AI_RESPONSE_RETRIES", 0)
    monkeypatch.setattr(webapp, "process_ticket", lambda _text: {
        "category": "Network",
        "severity": "Low",
        "priority": "P4",
        "confidence": 92,
    })
    monkeypatch.setattr(
        webapp.support_pilot,
        "process",
        lambda _ticket: (_ for _ in ()).throw(
            RuntimeError("synthetic AI failure")
        ),
    )
    monkeypatch.setattr(
        webapp,
        "create_jira_ticket",
        lambda **_kwargs: {"success": False},
    )
    client = authenticated_client()

    response = client.post("/ticket", json={
        "employee_name": "Test User",
        "email": "test@example.com",
        "department": "IT",
        "title": "Network issue",
        "description": "Cannot access the office network",
    })

    assert response.status_code == 200
    result = response.get_json()
    assert result["ticket"]["status"] == "Escalated"
    assert result["escalation"]["reason"] == "AI response failed"
    saved_ticket = database.get_all_tickets()[0]
    assert saved_ticket["ai_response_succeeded"] == 0
    assert saved_ticket["escalated"] == 1
    assert saved_ticket["validation_status"] == "Failed"


def test_classifier_exception_creates_escalated_ticket(
    isolated_database, monkeypatch
):
    def fail_classification(_text):
        raise FileNotFoundError("synthetic missing classifier")

    monkeypatch.setattr(webapp, "process_ticket", fail_classification)
    client = authenticated_client()

    response = client.post("/ticket", json={
        "employee_name": "Test User",
        "email": "test@example.com",
        "department": "IT",
        "title": "Unknown issue",
        "description": "The classifier model is unavailable",
    })

    result = response.get_json()
    assert response.status_code == 200
    assert result["ticket"]["status"] == "Escalated"
    assert result["classification"]["category"] == "Unclassified"
    assert result["escalation"]["reason"] == "AI classification failed"
    assert database.get_all_tickets()[0]["escalated"] == 1


def test_ai_response_timeout_escalates(isolated_database, monkeypatch):
    monkeypatch.setattr(webapp, "AI_RESPONSE_RETRIES", 0)
    monkeypatch.setattr(webapp, "AI_RESPONSE_TIMEOUT_SECONDS", 0.001)
    monkeypatch.setattr(webapp, "process_ticket", lambda _text: {
        "category": "Network",
        "severity": "Low",
        "priority": "P4",
        "confidence": 92,
    })
    monkeypatch.setattr(
        webapp.support_pilot,
        "process",
        lambda _ticket: time.sleep(0.05),
    )
    monkeypatch.setattr(
        webapp,
        "create_jira_ticket",
        lambda **_kwargs: {"success": False},
    )
    client = authenticated_client()

    response = client.post("/ticket", json={
        "employee_name": "Test User",
        "email": "test@example.com",
        "department": "IT",
        "title": "Network issue",
        "description": "Cannot access the office network",
    })

    assert response.status_code == 200
    result = response.get_json()
    assert result["ticket"]["status"] == "Escalated"
    assert result["validation"]["message"] == "AI response timed out"


def test_ai_response_retries_then_resolves(isolated_database, monkeypatch):
    attempts = []

    def process(_ticket):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("temporary retrieval failure")
        validation = {
            "valid": True,
            "status": "Validated",
            "message": "Validated",
        }
        return {
            "resolution": {
                "resolution": "Restart the network adapter",
                "steps": ["Restart adapter"],
            },
            "validation": validation,
            "escalation": EscalationAgent().run(
                {"confidence": 90}, validation
            ),
            "retrieval": {"retrieved_documents": [], "analysis": "sample"},
            "workflow": [],
        }

    monkeypatch.setattr(webapp, "AI_RESPONSE_RETRIES", 1)
    monkeypatch.setattr(webapp, "process_ticket", lambda _text: {
        "category": "Network",
        "severity": "Low",
        "priority": "P4",
        "confidence": 90,
    })
    monkeypatch.setattr(webapp.support_pilot, "process", process)
    client = authenticated_client()

    response = client.post("/ticket", json={
        "employee_name": "Test User",
        "email": "test@example.com",
        "department": "IT",
        "title": "Network issue",
        "description": "Cannot access the office network",
    })

    assert response.status_code == 200
    assert len(attempts) == 2
    assert response.get_json()["ticket"]["status"] == "Resolved"
    assert database.get_all_tickets()[0]["ai_response_succeeded"] == 1


def test_human_support_request_escalates_ticket(
    isolated_database, monkeypatch
):
    validation = {"valid": True, "status": "Validated", "message": "Validated"}
    monkeypatch.setattr(webapp, "process_ticket", lambda _text: {
        "category": "Network",
        "severity": "Low",
        "priority": "P4",
        "confidence": 90,
    })
    monkeypatch.setattr(webapp.support_pilot, "process", lambda ticket: {
        "resolution": {
            "resolution": "Suggested fix",
            "steps": ["Check adapter"],
        },
        "validation": validation,
        "escalation": EscalationAgent().run(ticket, validation),
        "retrieval": {"retrieved_documents": [], "analysis": "sample"},
        "workflow": [],
    })
    monkeypatch.setattr(
        webapp,
        "create_jira_ticket",
        lambda **_kwargs: {"success": False},
    )
    client = authenticated_client()

    response = client.post("/ticket", json={
        "employee_name": "Test User",
        "email": "test@example.com",
        "department": "IT",
        "title": "Network issue",
        "description": "Please have a person review this",
        "human_support_requested": True,
    })

    assert response.status_code == 200
    result = response.get_json()
    assert result["ticket"]["status"] == "Escalated"
    assert result["escalation"]["reason"] == "Human support requested"
