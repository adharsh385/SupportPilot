import time
from datetime import datetime, timedelta, timezone

import jwt
from flask import (
    Flask,
    g,
    request,
    jsonify,
    render_template,
    redirect,
    url_for
)

from config import (
    JWT_EXPIRATION_MINUTES,
    SECRET_KEY
)

from classifier import (
    process_ticket
)

from database import (
    initialize_database,
    create_user,
    authenticate_user,
    save_ticket,
    get_all_tickets,
    delete_ticket
)

from data.rag.pipeline import (
    run_rag_pipeline
)


app = Flask(
    __name__,
    template_folder="data/rag/templates"
)

JWT_COOKIE_NAME = "access_token"

initialize_database()


def login_required():

    token = request.cookies.get(
        JWT_COOKIE_NAME
    )

    if not token:

        authorization = request.headers.get(
            "Authorization",
            ""
        )

        if authorization.startswith("Bearer "):

            token = authorization[7:].strip()

    if not token:

        return False

    try:

        g.current_user = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=["HS256"]
        )

        return True

    except jwt.InvalidTokenError:

        return False


def create_access_token(user):

    now = datetime.now(
        timezone.utc
    )

    return jwt.encode(
        {
            "sub": str(user["id"]),
            "username": user["username"],
            "iat": now,
            "exp": now + timedelta(
                minutes=JWT_EXPIRATION_MINUTES
            )
        },
        SECRET_KEY,
        algorithm="HS256"
    )


@app.route("/")
def home():

    if login_required():

        return redirect(
            url_for("dashboard")
        )

    return redirect(
        url_for("login")
    )


@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        username = (
            request.form.get(
                "username",
                ""
            ).strip()
        )

        password = (
            request.form.get(
                "password",
                ""
            )
        )

        user = authenticate_user(
            username,
            password
        )

        if user:

            response = redirect(
                url_for("dashboard")
            )

            response.set_cookie(
                JWT_COOKIE_NAME,
                create_access_token(user),
                httponly=True,
                samesite="Lax",
                max_age=JWT_EXPIRATION_MINUTES * 60
            )

            return response

        return render_template(
            "login.html",
            error="Invalid username or password."
        )

    return render_template(
        "login.html"
    )


@app.route("/logout")
def logout():

    response = redirect(
        url_for("login")
    )

    response.delete_cookie(
        JWT_COOKIE_NAME
    )

    return response


@app.route("/dashboard")
def dashboard():

    if not login_required():

        return redirect(
            url_for("login")
        )

    tickets = get_all_tickets()

    open_count = sum(
        1
        for ticket in tickets
        if ticket["status"] == "Open"
    )

    p1_count = sum(
        1
        for ticket in tickets
        if ticket["priority"] == "P1"
    )

    ai_count = sum(
        1
        for ticket in tickets
        if ticket["category"]
    )

    return render_template(
        "dashboard.html",

        username=g.current_user["username"],

        tickets=tickets,

        open_count=open_count,

        p1_count=p1_count,

        ai_count=ai_count,

        retrieval_accuracy=94.2,

        resolution_rate=86.7,

        average_response_time=5.0
    )


@app.route("/ticket")
def ticket_page():

    if not login_required():

        return redirect(
            url_for("login")
        )

    return render_template(
        "ticket.html"
    )


@app.route("/integrations")
def integrations():

    if not login_required():

        return redirect(
            url_for("login")
        )

    return render_template(
        "integrations.html",
        username=g.current_user["username"]
    )


@app.route("/settings")
def settings():

    if not login_required():

        return redirect(
            url_for("login")
        )

    return render_template(
        "settings.html",
        username=g.current_user["username"],
        jwt_expiration_minutes=JWT_EXPIRATION_MINUTES
    )


@app.route(
    "/ticket/<int:ticket_id>/delete",
    methods=["POST"]
)
def delete_ticket_route(ticket_id):

    if not login_required():

        return redirect(
            url_for("login")
        )

    delete_ticket(ticket_id)

    return redirect(
        url_for("dashboard")
    )


@app.route(
    "/ticket",
    methods=["POST"]
)
def create_ticket():

    if not login_required():

        return jsonify({

            "success": False,

            "message":
                "Authentication required."

        }), 401

    start_time = (
        time.perf_counter()
    )

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    required_fields = [

        "employee_name",
        "email",
        "department",
        "title",
        "description"

    ]

    missing = []

    for field in required_fields:

        if not str(
            data.get(
                field,
                ""
            )
        ).strip():

            missing.append(
                field
            )

    if missing:

        return jsonify({

            "success": False,

            "message":
                "Missing required fields: "
                + ", ".join(missing)

        }), 400

    ticket_text = (

        data["title"]
        + " "
        + data["description"]

    )

    classification = (
        process_ticket(
            ticket_text
        )
    )

    ticket = {

        "id": "TEMP",

        "employee_name":
            data[
                "employee_name"
            ].strip(),

        "email":
            data[
                "email"
            ].strip(),

        "department":
            data[
                "department"
            ].strip(),

        "title":
            data[
                "title"
            ].strip(),

        "description":
            data[
                "description"
            ].strip(),

        "category":
            classification[
                "category"
            ],

        "severity":
            classification[
                "severity"
            ],

        "priority":
            classification[
                "priority"
            ],

        "confidence":
            classification[
                "confidence"
            ],

        "business_impact":
            classification[
                "business_impact"
            ],

        "status":
            "Open"

    }

    ticket_id = save_ticket(
        ticket
    )

    ticket["id"] = (
        f"T{ticket_id:04d}"
    )

    rag_result = (
        run_rag_pipeline(
            ticket
        )
    )

    response_time = round(
        time.perf_counter()
        - start_time,
        3
    )

    return jsonify({

        "success": True,

        "ticket": {

            "id":
                ticket["id"],

            "employee_name":
                ticket[
                    "employee_name"
                ],

            "email":
                ticket["email"],

            "department":
                ticket[
                    "department"
                ],

            "title":
                ticket["title"],

            "description":
                ticket[
                    "description"
                ],

            "status":
                ticket["status"]

        },

        "classification":
            classification,

        "analysis":
            rag_result[
                "analysis"
            ],

        "retrieved_documents":
            rag_result[
                "retrieved_documents"
            ],

        "recommended_resolution":
            rag_result[
                "resolution"
            ],

        "resolution_steps":
            rag_result[
                "resolution_steps"
            ],

        "resolution_status":
            rag_result[
                "resolution_status"
            ],

        "rag_workflow":
            rag_result[
                "workflow"
            ],

        "metrics": {

            "response_time_seconds":
                response_time,

            "documents_retrieved":
                len(
                    rag_result[
                        "retrieved_documents"
                    ]
                )

        }

    })


if __name__ == "__main__":

    app.run(
        debug=True
    )
