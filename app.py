from datetime import datetime
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
import json
import logging
import os
from pathlib import Path
import secrets
import time

from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for
)

from classifier import process_ticket
from database import (
    get_all_tickets,
    get_dashboard_metrics,
    get_escalation_status,
    get_weekly_ticket_counts,
    initialize_database,
    authenticate_user,
    create_user,
    delete_ticket,
    save_ticket,
    record_api_metric,
    update_ticket
)
from agent import SupportPilot
from config import (
    AI_RESPONSE_RETRIES,
    AI_RESPONSE_TIMEOUT_SECONDS,
    BASE_DIR,
    ESCALATION_CONFIDENCE_THRESHOLD,
)
from email_service import send_email_notification
from email_service import send_welcome_email
from jira_service import create_jira_ticket
from jira_service import jira_is_configured
from email_service import email_is_configured


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
app_started_at = time.monotonic()

log_path = Path(__file__).resolve().parent / "dashboard" / "supportpilot.log"
log_path.parent.mkdir(parents=True, exist_ok=True)
app_logger = logging.getLogger("supportpilot")
app_logger.setLevel(logging.INFO)
if not any(
    getattr(handler, "baseFilename", None) == str(log_path)
    for handler in app_logger.handlers
):
    file_handler = logging.FileHandler(log_path, encoding="utf-8")

    class JsonLogFormatter(logging.Formatter):
        def format(self, record):
            return json.dumps({
                "timestamp": datetime.now().astimezone().isoformat(
                    timespec="seconds"
                ),
                "level": record.levelname,
                "event": getattr(record, "event", record.getMessage()),
                "message": record.getMessage(),
                "ticket_id": getattr(record, "ticket_id", None),
                "status": getattr(record, "status", None),
                "confidence": getattr(record, "confidence", None),
                "duration_ms": getattr(record, "duration_ms", None),
            })

    file_handler.setFormatter(JsonLogFormatter())
    app_logger.addHandler(file_handler)

initialize_database()

support_pilot = SupportPilot()


@app.before_request
def start_request_timer():
    g.request_started_at = time.perf_counter()


@app.after_request
def record_request_metrics(response):
    if request.path.startswith("/api/"):
        duration_ms = (time.perf_counter() - g.request_started_at) * 1000
        try:
            record_api_metric(request.path, duration_ms, response.status_code)
        except Exception:
            app_logger.exception(
                "api_metric_record_failed",
                extra={"event": "api_metric_record_failed"},
            )
        if response.status_code >= 400:
            app_logger.warning(
                "api_request_error",
                extra={
                    "event": "api_request_error",
                    "status": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                },
            )
    return response


def login_required(view):

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({
                    "success": False,
                    "message": "Login required."
                }), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped_view


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    error = None

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = authenticate_user(username, password)

        if user:
            session.clear()
            session.update(user)
            next_page = request.args.get("next") or url_for("dashboard")
            return redirect(next_page)

        error = "Invalid username or password."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(username) < 3:
            error = "Username must contain at least 3 characters."
        elif not email or "@" not in email:
            error = "Enter a valid email address."
        elif len(password) < 6:
            error = "Password must contain at least 6 characters."
        elif password != confirm_password:
            error = "Passwords do not match."
        elif create_user(username, email, password) is None:
            error = "Username or email already exists."
        else:
            send_welcome_email(username, email)
            return redirect(url_for("login", registered="1"))

    return render_template("register.html", error=error)


@app.route("/dashboard")
@login_required
def dashboard():
    tickets_data = get_all_tickets()
    category_counts = {}
    priority_counts = {}

    for ticket in tickets_data:
        category = ticket.get("category") or "Unclassified"
        priority = ticket.get("priority") or "Unknown"
        category_counts[category] = category_counts.get(category, 0) + 1
        priority_counts[priority] = priority_counts.get(priority, 0) + 1

    counts = {
        "total": len(tickets_data),
        "resolved": sum(
            ticket["status"] == "Resolved"
            for ticket in tickets_data
        ),
        "open": sum(ticket["status"] == "Open" for ticket in tickets_data),
        "escalated": sum(
            ticket["status"] == "Escalated"
            for ticket in tickets_data
        )
    }
    return render_template(
        "dashboard.html",
        user=session,
        tickets=tickets_data[:8],
        counts=counts,
        category_counts=sorted(
            category_counts.items(),
            key=lambda item: item[1],
            reverse=True
        ),
        priority_counts=sorted(priority_counts.items()),
        jira_configured=jira_is_configured(),
        email_configured=email_is_configured(),
        escalation_threshold=ESCALATION_CONFIDENCE_THRESHOLD,
    )


@app.route("/agent")
@login_required
def agent_page():
    return render_template("index.html", user=session)


@app.route("/tickets")
@login_required
def tickets():
    tickets_data = get_all_tickets()
    resolved_count = sum(
        ticket.get("status") == "Resolved"
        for ticket in tickets_data
    )

    confidence_values = [
        float(ticket.get("confidence") or 0)
        for ticket in tickets_data
    ]
    retrieval_accuracy = round(
        sum(confidence_values) / len(confidence_values),
        1
    ) if confidence_values else 0
    resolution_rate = round(
        resolved_count / len(tickets_data) * 100,
        1
    ) if tickets_data else 0

    return render_template(
        "tickets.html",
        user=session,
        tickets=tickets_data,
        metrics={
            "retrieval_accuracy": retrieval_accuracy,
            "resolution_rate": resolution_rate,
            "average_response_time": "Under 1 sec",
            "workflow_status": "Generated Resolution"
        }
    )


@app.route("/tickets/<int:ticket_id>/delete", methods=["POST"])
@login_required
def delete_ticket_route(ticket_id):
    delete_ticket(ticket_id)
    return redirect(url_for("tickets"))


@app.route("/tickets/<int:ticket_id>/satisfaction", methods=["POST"])
@login_required
def ticket_satisfaction(ticket_id):
    ticket = next(
        (
            item for item in get_all_tickets()
            if item["ticket_id"] == ticket_id
        ),
        None,
    )
    if ticket is None:
        abort(404)
    if str(ticket.get("status", "")).strip().lower() not in {
        "resolved", "auto-resolved", "closed"
    }:
        abort(400, "Satisfaction can only be recorded for resolved tickets.")

    try:
        score = int(request.form["csat"])
    except (KeyError, TypeError, ValueError):
        abort(400, "Select a satisfaction score from 1 to 5.")
    try:
        update_ticket(ticket_id, csat=score)
    except (TypeError, ValueError) as error:
        abort(400, str(error))

    app_logger.info(
        "ticket_satisfaction_recorded",
        extra={
            "event": "ticket_satisfaction_recorded",
            "ticket_id": ticket_id,
        },
    )
    flash("Satisfaction score saved.", "success")
    return redirect(url_for("dashboard"))


@app.route("/api/tickets")
@login_required
def tickets_api():
    return jsonify({
        "success": True,
        "tickets": get_all_tickets()
    })


@app.route("/integrations")
@login_required
def integrations():
    return render_template(
        "integrations.html",
        user=session,
        jira_configured=jira_is_configured(),
        email_configured=email_is_configured()
    )


@app.route("/analytics")
@login_required
def analytics():
    tickets_data = get_all_tickets()
    try:
        classifier_evaluation = evaluate_classifier_sample()
    except Exception:
        classifier_evaluation = None
        app_logger.exception(
            "classifier_evaluation_unavailable",
            extra={"event": "classifier_evaluation_unavailable"},
        )
    category_counts = {}
    priority_counts = {}

    for ticket in tickets_data:
        category = ticket.get("category") or "Unclassified"
        priority = ticket.get("priority") or "Unknown"
        category_counts[category] = category_counts.get(category, 0) + 1
        priority_counts[priority] = priority_counts.get(priority, 0) + 1

    return render_template(
        "analytics.html",
        user=session,
        total=len(tickets_data),
        classifier_evaluation=classifier_evaluation,
        recent_tickets=sorted(
            tickets_data,
            key=lambda ticket: ticket["ticket_id"]
        ),
        category_max=max(category_counts.values(), default=1),
        priority_max=max(priority_counts.values(), default=1),
        category_counts=sorted(
            category_counts.items(),
            key=lambda item: item[1],
            reverse=True
        ),
        priority_counts=sorted(priority_counts.items())
    )


@app.route("/operations-dashboard")
@login_required
def operations_dashboard():
    return redirect(url_for("dashboard"))


def evaluate_classifier_sample():
    sample_path = BASE_DIR / "data" / "classifier_evaluation_samples.json"
    with sample_path.open(encoding="utf-8") as sample_file:
        samples = json.load(sample_file)
    expected = [sample["expected_category"] for sample in samples]
    predicted = [
        process_ticket(sample["text"])["category"] for sample in samples
    ]
    labels = sorted(set(expected) | set(predicted))
    true_positive = {label: 0 for label in labels}
    false_positive = {label: 0 for label in labels}
    false_negative = {label: 0 for label in labels}
    for actual, guess in zip(expected, predicted):
        if actual == guess:
            true_positive[actual] += 1
        else:
            false_positive[guess] += 1
            false_negative[actual] += 1
    total = len(expected)
    precision = sum(
        true_positive[label] / (true_positive[label] + false_positive[label])
        if true_positive[label] + false_positive[label] else 0
        for label in labels
    ) / len(labels)
    recall = sum(
        true_positive[label] / (true_positive[label] + false_negative[label])
        if true_positive[label] + false_negative[label] else 0
        for label in labels
    ) / len(labels)
    f1_score = (
        2 * precision * recall / (precision + recall)
        if precision + recall else 0
    )
    return {
        "dataset": "isolated_sample_test_data",
        "samples": total,
        "accuracy": round(
            sum(
                actual == guess
                for actual, guess in zip(expected, predicted)
            ) / total * 100,
            2,
        ),
        "precision": round(precision * 100, 2),
        "recall": round(recall * 100, 2),
        "f1_score": round(f1_score * 100, 2),
    }


@app.route("/api/dashboard/metrics")
@app.route("/api/dashboard/metrics/")
@login_required
def dashboard_metrics_api():
    metrics = get_dashboard_metrics()
    try:
        evaluation = evaluate_classifier_sample()
        metrics["classification_accuracy"] = evaluation["accuracy"]
    except (FileNotFoundError, ValueError, OSError):
        evaluation = None
        metrics["classification_accuracy"] = None
    metrics["system_uptime_seconds"] = round(
        time.monotonic() - app_started_at, 1
    )
    return jsonify({
        "success": True,
        "metrics": metrics,
        "classifier_evaluation": evaluation,
    })


@app.route("/api/dashboard/chart")
@app.route("/api/dashboard/chart/")
@login_required
def dashboard_chart_api():
    return jsonify({"success": True, **get_weekly_ticket_counts()})


@app.route("/api/dashboard/escalation")
@app.route("/api/dashboard/escalation/")
@login_required
def dashboard_escalation_api():
    return jsonify({"success": True, "workflow": get_escalation_status()})


@app.route("/api/dashboard/classifier-evaluation")
@app.route("/api/dashboard/classifier-evaluation/")
@login_required
def classifier_evaluation_api():
    try:
        result = evaluate_classifier_sample()
    except FileNotFoundError:
        return jsonify({
            "success": False,
            "message": "Classifier test data is unavailable.",
        }), 503
    except Exception:
        app_logger.exception(
            "classifier_evaluation_failed",
            extra={"event": "classifier_evaluation_failed"},
        )
        return jsonify({
            "success": False,
            "message": "Classifier evaluation failed.",
        }), 503
    app_logger.info(
        "classifier_evaluation_completed",
        extra={"event": "classifier_evaluation_completed"},
    )
    return jsonify({"success": True, "evaluation": result})


@app.route("/api/dashboard/monitoring")
@app.route("/api/dashboard/monitoring/")
@login_required
def dashboard_monitoring_api():
    metrics = get_dashboard_metrics()
    metrics["system_uptime_seconds"] = round(
        time.monotonic() - app_started_at, 1
    )
    try:
        evaluation = evaluate_classifier_sample()
        metrics["classification_accuracy"] = evaluation["accuracy"]
    except Exception:
        metrics["classification_accuracy"] = None
    return jsonify({"success": True, "monitoring": metrics})


@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html", user=session)


@app.route("/health")
def health():
    return jsonify({
        "success": True,
        "application": "SupportPilot",
        "status": "Running",
        "capabilities": [
            "Ticket Classification",
            "RAG Knowledge Retrieval",
            "Multi-Agent Workflow"
        ]
    })


@app.route("/system-health")
@login_required
def system_health():
    return render_template(
        "health.html",
        user=session,
        jira_configured=jira_is_configured(),
        email_configured=email_is_configured()
    )


@app.route("/ticket", methods=["POST"])
@login_required
def process_ticket_route():

    data = request.get_json(silent=True) or {}

    required_fields = [
        "employee_name",
        "email",
        "department",
        "title",
        "description"
    ]

    missing_fields = [
        field
        for field in required_fields
        if not str(data.get(field, "")).strip()
    ]

    if missing_fields:
        return jsonify({
            "success": False,
            "message": (
                "Missing required fields: "
                + ", ".join(missing_fields)
            )
        }), 400

    employee_name = str(
        data["employee_name"]
    ).strip()

    email = str(
        data["email"]
    ).strip()

    department = str(
        data["department"]
    ).strip()

    title = str(
        data["title"]
    ).strip()

    description = str(
        data["description"]
    ).strip()

    ticket_text = (
        title + " " + description
    )

    human_requested = bool(data.get("human_support_requested", False))

    processing_started_at = time.perf_counter()
    classification_failed = False
    try:
        classification = process_ticket(
            ticket_text
        )
    except Exception:
        app_logger.exception(
            "ticket_classification_failed",
            extra={"event": "ticket_classification_failed"},
        )
        classification_failed = True
        classification = {
            "category": "Unclassified",
            "severity": "Unknown",
            "priority": "P4",
            "confidence": 0,
        }

    ticket = {
        "employee_name": employee_name,
        "email": email,
        "department": department,
        "title": title,
        "description": description,
        "category": classification["category"],
        "severity": classification["severity"],
        "priority": classification["priority"],
        "confidence": classification["confidence"],
        "status": "Open",
        "human_requested": human_requested,
        "validation_status": "Pending",
    }

    ticket_id = save_ticket(
        ticket
    )

    app_logger.info(
        "ticket_created",
        extra={"event": "ticket_created", "ticket_id": ticket_id},
    )
    classification_event = (
        "ticket_classification_failed"
        if classification_failed else "ticket_classified"
    )
    app_logger.info(
        classification_event,
        extra={
            "event": classification_event,
            "ticket_id": ticket_id,
            "status": classification["category"],
            "confidence": classification["confidence"],
        },
    )

    ticket["ticket_id"] = ticket_id

    agent_result = None
    pipeline_error = (
        "AI classification failed" if classification_failed else None
    )
    response_started_at = time.perf_counter()
    max_attempts = 0 if classification_failed else AI_RESPONSE_RETRIES + 1
    for attempt in range(max_attempts):
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(support_pilot.process, ticket)
        try:
            agent_result = future.result(timeout=AI_RESPONSE_TIMEOUT_SECONDS)
            break
        except FutureTimeoutError:
            pipeline_error = "AI response timed out"
            future.cancel()
        except Exception:
            pipeline_error = "AI response generation failed"
            app_logger.exception(
                "ai_response_attempt_failed",
                extra={
                    "event": "ai_response_attempt_failed",
                    "ticket_id": ticket_id,
                },
            )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        if attempt < AI_RESPONSE_RETRIES:
            app_logger.warning(
                "ai_response_retry",
                extra={"event": "ai_response_retry", "ticket_id": ticket_id},
            )

    response_time = time.perf_counter() - response_started_at
    if agent_result:
        resolution = agent_result["resolution"]
        validation = agent_result["validation"]
        escalation = agent_result["escalation"]
        recommended_resolution = resolution["resolution"]
        resolution_steps = resolution["steps"]
    else:
        ticket["classification_failed"] = classification_failed
        ticket["resolution_failed"] = True
        validation = {
            "valid": False,
            "status": "Failed",
            "message": pipeline_error or "AI response generation failed.",
        }
        escalation = support_pilot.escalation_agent.run(ticket, validation)
        recommended_resolution = ""
        resolution_steps = []

    if escalation["escalate"]:
        status = "Escalated"
    elif validation["valid"]:
        status = "Resolved"
    else:
        status = "Needs Review"

    ai_processing_time_seconds = time.perf_counter() - processing_started_at
    update_ticket(
        ticket_id,
        status=status,
        resolution=recommended_resolution,
        ai_processing_time_seconds=ai_processing_time_seconds,
        response_generation_time_seconds=(
            response_time if not classification_failed else None
        ),
        ai_response_succeeded=(
            bool(agent_result) if not classification_failed else None
        ),
        ai_resolved=bool(
            agent_result and validation["valid"] and not escalation["escalate"]
        ),
        escalated=bool(escalation["escalate"]),
        escalation_reason=escalation.get("reason"),
        validation_status="Validated" if validation["valid"] else "Failed",
        human_requested=human_requested,
    )
    app_logger.info(
        "ai_response_recorded",
        extra={
            "event": "ai_response_recorded",
            "ticket_id": ticket_id,
            "status": status,
            "duration_ms": round(response_time * 1000, 2),
        },
    )
    resolution_event = (
        "ai_resolution_completed" if agent_result else "ai_resolution_failed"
    )
    app_logger.info(
        resolution_event,
        extra={
            "event": resolution_event,
            "ticket_id": ticket_id,
            "status": status,
        },
    )
    app_logger.info(
        "resolution_validation_completed",
        extra={
            "event": "resolution_validation_completed",
            "ticket_id": ticket_id,
            "status": validation["status"],
        },
    )
    if escalation["escalate"]:
        app_logger.warning(
            "ticket_escalated",
            extra={
                "event": "ticket_escalated",
                "ticket_id": ticket_id,
                "status": escalation.get("reason"),
            },
        )
        app_logger.info(
            "human_review_assignment_requested",
            extra={
                "event": "human_review_assignment_requested",
                "ticket_id": ticket_id,
                "status": escalation.get("reason"),
            },
        )

    jira_result = {
        "success": False,
        "configured": False,
        "status": "Demo Mode",
        "ticket_id": f"SP-{ticket_id}"
    }

    if escalation["escalate"]:

        jira_response = create_jira_ticket(
            ticket_id=ticket_id,
            title=title,
            description=description,
            category=classification["category"],
            priority=classification["priority"],
            resolution=recommended_resolution
        )

        if jira_response.get("success"):

            app_logger.info(
                "human_review_handoff_created",
                extra={
                    "event": "human_review_handoff_created",
                    "ticket_id": ticket_id,
                    "status": "Jira",
                },
            )

            jira_result = {
                "success": True,
                "configured": True,
                "status": "Active",
                "ticket_id": jira_response.get(
                    "ticket_id",
                    f"SP-{ticket_id}"
                ),
                "message": jira_response.get(
                    "message",
                    "Jira ticket created."
                )
            }

        else:

            jira_result = {
                "success": False,
                "configured": jira_response.get(
                    "configured",
                    False
                ),
                "status": "Demo Mode",
                "ticket_id": f"SP-{ticket_id}",
                "message": jira_response.get(
                    "message",
                    "Jira integration not configured."
                )
            }

    send_email = bool(
        data.get(
            "send_email",
            False
        )
    )

    if send_email:

        email_response = send_email_notification(
            employee_name=employee_name,
            recipient=email,
            ticket_id=ticket_id,
            title=title,
            category=classification["category"],
            priority=classification["priority"],
            resolution=recommended_resolution
        )

        if email_response.get("success"):

            email_result = {
                "success": True,
                "configured": email_response.get(
                    "configured",
                    True
                ),
                "status": email_response.get(
                    "status",
                    "Sent"
                ),
                "message": email_response.get(
                    "message"
                )
            }

        else:

            email_result = {
                "success": False,
                "configured": email_response.get(
                    "configured",
                    False
                ),
                "status": email_response.get(
                    "status",
                    "Not sent"
                ),
                "message": email_response.get(
                    "message"
                )
            }

    else:

        email_result = {
            "success": False,
            "configured": False,
            "status": "Demo Mode",
            "message": (
                "Email automation available. "
                "No email was sent for this demo."
            )
        }

    current_time = datetime.now().strftime(
        "%I:%M %p"
    )

    retrieval_documents = (
        agent_result.get("retrieval", {}).get("retrieved_documents", [])
        if agent_result else []
    )
    workflow_activity = [

        {
            "time": current_time,
            "agent": "Diagnosis Agent",
            "message": (
                "Identified "
                + classification["category"]
                + " issue"
            )
        },

        {
            "time": current_time,
            "agent": "Retrieval Agent",
            "message": (
                "Found "
                + str(len(retrieval_documents))
                + " relevant knowledge articles"
                if agent_result else (
                    "AI workflow could not continue; "
                    "ticket sent for human review"
                )
            )
        },

        {
            "time": current_time,
            "agent": "Resolution Agent",
            "message": (
                "Generated troubleshooting steps" if agent_result
                else "AI could not generate a resolution"
            )
        },

        {
            "time": current_time,
            "agent": "Validation Agent",
            "message": (
                "Resolution validation: "
                + validation["status"]
            )
        }
    ]

    if escalation["escalate"]:

        workflow_activity.append({
            "time": current_time,
            "agent": "Escalation Agent",
            "message": (
                "Issue is not resolved automatically and requires "
                "manual review"
            )
        })

    elif validation["valid"]:

        workflow_activity.append({
            "time": current_time,
            "agent": "System",
            "message": (
                "Workflow completed: validated resolution generated; "
                "ticket marked Resolved"
            )
        })

    else:

        workflow_activity.append({
            "time": current_time,
            "agent": "System",
            "message": (
                "Workflow completed, but the issue is not resolved and "
                "needs manual review"
            )
        })

    return jsonify({

        "success": True,

        "ticket": {
            "ticket_id": ticket_id,
            "employee_name": employee_name,
            "email": email,
            "department": department,
            "title": title,
            "description": description,
            "status": status
        },

        "classification": classification,

        "recommended_resolution":
            recommended_resolution,

        "resolution_steps":
            resolution_steps,

        "validation":
            validation,

        "escalation":
            escalation,

        "workflow_activity":
            workflow_activity,

        "workflow": agent_result["workflow"] if agent_result else [],

        "integrations": {
            "jira": jira_result,
            "email": email_result
        },

        "retrieved_documents": retrieval_documents,

        "analysis": (
            agent_result["retrieval"]["analysis"]
            if agent_result
            else "AI response unavailable; escalated for human review."
        ),

        "response_time_seconds": response_time,
    })


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        use_reloader=False,
    )
