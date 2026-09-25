from datetime import datetime
from functools import wraps

from flask import (
    Flask,
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
    initialize_database,
    authenticate_user,
    create_user,
    delete_ticket,
    save_ticket,
    update_ticket
)
from agent import SupportPilot
from email_service import send_email_notification
from email_service import send_welcome_email
from jira_service import create_jira_ticket
from jira_service import jira_is_configured
from email_service import email_is_configured


app = Flask(__name__)
app.secret_key = "supportpilot-development-key"

initialize_database()

support_pilot = SupportPilot()


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
        email_configured=email_is_configured()
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

    classification = process_ticket(
        ticket_text
    )

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
        "status": "Open"
    }

    ticket_id = save_ticket(
        ticket
    )

    ticket["ticket_id"] = ticket_id

    agent_result = support_pilot.process(
        ticket
    )

    resolution = agent_result[
        "resolution"
    ]

    validation = agent_result[
        "validation"
    ]

    escalation = agent_result[
        "escalation"
    ]

    recommended_resolution = resolution[
        "resolution"
    ]

    resolution_steps = resolution[
        "steps"
    ]

    if escalation["escalate"]:
        status = "Escalated"
    elif validation["valid"]:
        status = "Resolved"
    else:
        status = "Needs Review"

    update_ticket(
        ticket_id,
        status=status,
        resolution=recommended_resolution
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
                + str(
                    len(
                        agent_result[
                            "retrieval"
                        ][
                            "retrieved_documents"
                        ]
                    )
                )
                + " relevant knowledge articles"
            )
        },

        {
            "time": current_time,
            "agent": "Resolution Agent",
            "message": (
                "Generated troubleshooting steps"
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

        "workflow":
            agent_result["workflow"],

        "integrations": {
            "jira": jira_result,
            "email": email_result
        },

        "retrieved_documents":
            agent_result[
                "retrieval"
            ][
                "retrieved_documents"
            ],

        "analysis":
            agent_result[
                "retrieval"
            ][
                "analysis"
            ]
    })


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
