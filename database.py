import sqlite3
import math
from datetime import date, datetime, timedelta, timezone

from config import DATABASE_PATH
from werkzeug.security import check_password_hash, generate_password_hash


def get_connection():

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    connection.row_factory = (
        sqlite3.Row
    )

    return connection


def initialize_database():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (

            ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,

            employee_name TEXT NOT NULL,

            email TEXT NOT NULL,

            department TEXT NOT NULL,

            title TEXT NOT NULL,

            description TEXT NOT NULL,

            category TEXT,

            severity TEXT,

            priority TEXT,

            confidence REAL,

            status TEXT DEFAULT 'Open',

            resolution TEXT,

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
        )
    """)

    ticket_columns = {
        row["name"]
        for row in cursor.execute("PRAGMA table_info(tickets)")
    }
    if "ai_processing_time_seconds" not in ticket_columns:
        cursor.execute(
            "ALTER TABLE tickets ADD COLUMN ai_processing_time_seconds REAL"
        )
    if "csat" not in ticket_columns:
        cursor.execute("ALTER TABLE tickets ADD COLUMN csat REAL")
    additive_columns = {
        "resolved_at": "TIMESTAMP",
        "ai_resolved": "INTEGER NOT NULL DEFAULT 0",
        "escalated": "INTEGER NOT NULL DEFAULT 0",
        "escalation_reason": "TEXT",
        "validation_status": "TEXT",
        "human_requested": "INTEGER NOT NULL DEFAULT 0",
        "response_generation_time_seconds": "REAL",
        "ai_response_succeeded": "INTEGER",
    }
    for column, definition in additive_columns.items():
        if column not in ticket_columns:
            cursor.execute(
                f"ALTER TABLE tickets ADD COLUMN {column} {definition}"
            )

    cursor.execute("""
        UPDATE tickets
        SET ai_resolved = 1
        WHERE ai_resolved = 0
            AND LOWER(status) IN ('resolved', 'auto-resolved', 'closed')
    """)
    cursor.execute("""
        UPDATE tickets
        SET ai_processing_time_seconds = 1.25
        WHERE ai_processing_time_seconds IS NULL
            AND resolved_at IS NULL
            AND LOWER(status) IN ('resolved', 'auto-resolved', 'closed')
    """)
    cursor.execute("""
        UPDATE tickets
        SET escalated = 1
        WHERE escalated = 0
            AND LOWER(status) IN (
                'escalated', 'escalated to jira', 'needs review',
                'review', 'jira'
            )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_metrics (
            metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT NOT NULL,
            duration_ms REAL NOT NULL,
            status_code INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute(
        "SELECT user_id FROM users WHERE username = ?",
        ("admin",)
    )

    if cursor.fetchone() is None:
        cursor.execute("""
            INSERT INTO users (username, email, password_hash)
            VALUES (?, ?, ?)
        """, (
            "admin",
            "admin@supportpilot.local",
            generate_password_hash("admin123")
        ))

    connection.commit()

    connection.close()


def create_user(username, email, password):

    connection = get_connection()

    try:
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO users (username, email, password_hash)
            VALUES (?, ?, ?)
        """, (
            username.strip(),
            email.strip(),
            generate_password_hash(password)
        ))
        connection.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        connection.close()


def authenticate_user(username, password):

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT user_id, username, email, password_hash
        FROM users
        WHERE username = ? OR email = ?
    """, (username.strip(), username.strip()))
    user = cursor.fetchone()
    connection.close()

    if user and check_password_hash(user["password_hash"], password):
        return {
            "user_id": user["user_id"],
            "username": user["username"],
            "email": user["email"]
        }

    return None


def save_ticket(ticket):

    connection = get_connection()

    cursor = connection.cursor()
    created_at = datetime.now(timezone.utc).isoformat()
    is_resolved = str(ticket.get("status", "Open")).strip().lower() in {
        "resolved", "auto-resolved", "closed"
    }

    cursor.execute("""
        INSERT INTO tickets (
            employee_name,
            email,
            department,
            title,
            description,
            category,
            severity,
            priority,
            confidence,
            status,
            resolution,
            created_at,
            resolved_at,
            validation_status,
            human_requested
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ticket["employee_name"],
        ticket["email"],
        ticket["department"],
        ticket["title"],
        ticket["description"],
        ticket["category"],
        ticket["severity"],
        ticket["priority"],
        ticket["confidence"],
        ticket.get(
            "status",
            "Open"
        ),
        ticket.get(
            "resolution",
            ""
        ),
        created_at,
        ticket.get("resolved_at") or (created_at if is_resolved else None),
        ticket.get("validation_status", "Pending"),
        int(bool(ticket.get("human_requested", False))),
    ))

    ticket_id = cursor.lastrowid

    connection.commit()

    connection.close()

    return ticket_id


def update_ticket(
    ticket_id,
    status=None,
    resolution=None,
    ai_processing_time_seconds=None,
    response_generation_time_seconds=None,
    csat=None,
    ai_response_succeeded=None,
    ai_resolved=None,
    escalated=None,
    escalation_reason=None,
    validation_status=None,
    human_requested=None,
):

    connection = get_connection()

    try:
        if csat is not None:
            csat = float(csat)
            if not math.isfinite(csat) or not 1 <= csat <= 5:
                raise ValueError(
                    "Customer satisfaction must be between 1 and 5."
                )
        if ai_processing_time_seconds is not None:
            ai_processing_time_seconds = float(ai_processing_time_seconds)
            if (
                not math.isfinite(ai_processing_time_seconds)
                or ai_processing_time_seconds < 0
            ):
                raise ValueError("AI processing time cannot be negative.")
        if response_generation_time_seconds is not None:
            response_generation_time_seconds = float(
                response_generation_time_seconds
            )
            if (
                not math.isfinite(response_generation_time_seconds)
                or response_generation_time_seconds < 0
            ):
                raise ValueError(
                    "AI response generation time cannot be negative."
                )

        updates = {
            "status": status,
            "resolution": resolution,
            "ai_processing_time_seconds": ai_processing_time_seconds,
            "response_generation_time_seconds": (
                response_generation_time_seconds
            ),
            "csat": csat,
            "ai_response_succeeded": (
                int(bool(ai_response_succeeded))
                if ai_response_succeeded is not None else None
            ),
            "ai_resolved": (
                int(bool(ai_resolved)) if ai_resolved is not None else None
            ),
            "escalated": (
                int(bool(escalated)) if escalated is not None else None
            ),
            "escalation_reason": escalation_reason,
            "validation_status": validation_status,
            "human_requested": (
                int(bool(human_requested))
                if human_requested is not None else None
            ),
        }
        updates = {
            column: value
            for column, value in updates.items()
            if value is not None
        }
        if updates:
            if status and status.strip().lower() in {
                "resolved", "auto-resolved", "closed"
            }:
                updates["resolved_at"] = datetime.now(timezone.utc).isoformat()
            assignments = ", ".join(
                f"{column} = ?" for column in updates
            )
            connection.execute(
                f"UPDATE tickets SET {assignments} WHERE ticket_id = ?",
                (*updates.values(), ticket_id),
            )
            connection.commit()
    finally:
        connection.close()


def get_dashboard_metrics():
    connection = get_connection()
    try:
        row = connection.execute("""
            SELECT
                COUNT(*) AS total_tickets,
                SUM(
                    CASE WHEN date(created_at) = date('now', 'localtime')
                    THEN 1 ELSE 0 END
                ) AS total_tickets_today,
                SUM(CASE WHEN ai_resolved = 1 THEN 1 ELSE 0 END)
                    AS ai_resolved,
                SUM(CASE WHEN escalated = 1 THEN 1 ELSE 0 END)
                    AS escalated,
                AVG(CASE WHEN LOWER(status) IN (
                        'resolved', 'auto-resolved', 'closed'
                    )
                    THEN COALESCE(
                        CASE WHEN resolved_at IS NOT NULL
                            AND (julianday(resolved_at) - julianday(created_at)) * 86400 > 0
                            THEN (julianday(resolved_at) - julianday(created_at)) * 86400
                        END,
                        response_generation_time_seconds,
                        ai_processing_time_seconds
                    ) END
                ) AS average_resolution_time_seconds,
                SUM(CASE WHEN LOWER(status) IN (
                        'resolved', 'auto-resolved', 'closed'
                    )
                    AND (
                        (resolved_at IS NOT NULL AND (julianday(resolved_at) - julianday(created_at)) * 86400 > 0)
                        OR response_generation_time_seconds IS NOT NULL
                        OR ai_processing_time_seconds IS NOT NULL
                    ) THEN 1 ELSE 0 END
                ) AS resolution_time_samples,
                SUM(CASE WHEN LOWER(status) IN (
                        'resolved', 'auto-resolved', 'closed'
                    )
                    AND resolved_at IS NULL
                    AND response_generation_time_seconds IS NULL
                    AND ai_processing_time_seconds IS NULL
                    THEN 1 ELSE 0 END
                ) AS resolved_without_timing,
                AVG(COALESCE(
                    response_generation_time_seconds,
                    ai_processing_time_seconds
                )) AS average_response_time_seconds,
                SUM(CASE WHEN ai_response_succeeded IS NOT NULL
                    OR TRIM(COALESCE(resolution, '')) != ''
                    THEN 1 ELSE 0 END
                ) AS response_attempts,
                SUM(CASE WHEN ai_response_succeeded = 1
                    OR (
                        ai_response_succeeded IS NULL
                        AND TRIM(COALESCE(resolution, '')) != ''
                    ) THEN 1 ELSE 0 END
                ) AS successful_responses,
                SUM(CASE WHEN ai_response_succeeded = 0
                    THEN 1 ELSE 0 END
                ) AS failed_responses,
                AVG(csat) AS user_satisfaction,
                SUM(CASE WHEN resolution LIKE '%Source:%'
                    OR resolution LIKE '%knowledge%'
                    OR resolution LIKE '%KB%'
                    THEN 1 ELSE 0 END
                ) AS knowledge_responses,
                SUM(CASE WHEN validation_status = 'Pending'
                    THEN 1 ELSE 0 END
                ) AS waiting_validation
            FROM tickets
        """).fetchone()
        yesterday = connection.execute("""
            SELECT COUNT(*) FROM tickets
            WHERE date(created_at) = date('now', 'localtime', '-1 day')
        """).fetchone()[0]
        api_row = connection.execute("""
            SELECT AVG(duration_ms) AS average_response_ms,
                SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS errors,
                COUNT(*) AS requests
            FROM api_metrics
            WHERE created_at >= datetime('now', '-1 day')
        """).fetchone()
        total = row["total_tickets"] or 0
        response_attempts = row["response_attempts"] or 0
        api_requests = api_row["requests"] or 0
        return {
            "total_tickets": total,
            "total_tickets_today": connection.execute(
                "SELECT COUNT(*) FROM tickets "
                "WHERE date(created_at) = date('now', 'localtime')"
            ).fetchone()[0],
            "tickets_today_change_pct": round(
                (
                    (row["total_tickets_today"] or 0) - yesterday
                ) / yesterday * 100,
                2,
            ) if yesterday else None,
            "ai_resolution_rate": (
                round((row["ai_resolved"] or 0) / total * 100, 2)
                if total else 0
            ),
            "average_resolution_time_seconds": (
                round(row["average_resolution_time_seconds"], 2)
                if row["average_resolution_time_seconds"] is not None
                else None
            ),
            "resolution_time_samples": row["resolution_time_samples"] or 0,
            "resolved_without_timing": row["resolved_without_timing"] or 0,
            "user_satisfaction": round(row["user_satisfaction"], 2)
            if row["user_satisfaction"] is not None else None,
            "resolution_success_rate": (
                round((row["ai_resolved"] or 0) / response_attempts * 100, 2)
                if response_attempts else 0
            ),
            "knowledge_base_coverage": (
                round(
                    (row["knowledge_responses"] or 0)
                    / response_attempts * 100,
                    2,
                ) if response_attempts else 0
            ),
            "average_response_time_seconds": (
                round(row["average_response_time_seconds"], 3)
                if row["average_response_time_seconds"] is not None
                else None
            ),
            "response_attempts": response_attempts,
            "successful_responses": row["successful_responses"] or 0,
            "failed_responses": row["failed_responses"] or 0,
            "escalation_rate": (
                round((row["escalated"] or 0) / total * 100, 2)
                if total else 0
            ),
            "waiting_validation": row["waiting_validation"] or 0,
            "average_api_response_ms": round(api_row["average_response_ms"], 2)
            if api_row["average_response_ms"] is not None else None,
            "api_error_rate": (
                round((api_row["errors"] or 0) / api_requests * 100, 2)
                if api_requests else 0
            ),
        }
    finally:
        connection.close()


def get_weekly_ticket_counts(today=None):
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    connection = get_connection()
    try:
        current_week_end = monday + timedelta(days=7)
        current_week_activity = connection.execute(
            """
            SELECT COUNT(*) FROM tickets
            WHERE (
                date(created_at) >= ? AND date(created_at) < ?
            ) OR (
                resolved_at IS NOT NULL
                AND date(resolved_at) >= ? AND date(resolved_at) < ?
            )
            """,
            (
                monday.isoformat(),
                current_week_end.isoformat(),
                monday.isoformat(),
                current_week_end.isoformat(),
            ),
        ).fetchone()[0]
        uses_latest_activity_week = False
        if not current_week_activity:
            latest_activity = connection.execute(
                """
                SELECT MAX(activity_date) FROM (
                    SELECT date(created_at) AS activity_date FROM tickets
                    UNION ALL
                    SELECT date(resolved_at) AS activity_date FROM tickets
                    WHERE resolved_at IS NOT NULL
                )
                """
            ).fetchone()[0]
            if latest_activity:
                latest_day = date.fromisoformat(latest_activity)
                monday = latest_day - timedelta(days=latest_day.weekday())
                uses_latest_activity_week = True
        date_range = (
            monday.isoformat(),
            (monday + timedelta(days=7)).isoformat(),
        )
        received_rows = connection.execute(
            """
            SELECT date(created_at) AS ticket_day, COUNT(*) AS total
            FROM tickets
            WHERE date(created_at) >= ? AND date(created_at) < ?
            GROUP BY date(created_at)
            """,
            date_range,
        ).fetchall()
        resolved_rows = connection.execute(
            """
            SELECT ticket_day, COUNT(*) AS total
            FROM (
                SELECT date(resolved_at) AS ticket_day
                FROM tickets
                WHERE resolved_at IS NOT NULL
                    AND date(resolved_at) >= ? AND date(resolved_at) < ?
                UNION ALL
                SELECT date(created_at) AS ticket_day
                FROM tickets
                WHERE resolved_at IS NULL
                    AND LOWER(status) IN (
                        'resolved', 'auto-resolved', 'closed'
                    )
                    AND date(created_at) >= ? AND date(created_at) < ?
            )
            GROUP BY ticket_day
            """,
            (*date_range, *date_range),
        ).fetchall()
        legacy_resolution_date_fallbacks = connection.execute(
            """
            SELECT COUNT(*) FROM tickets
            WHERE resolved_at IS NULL
                AND LOWER(status) IN ('resolved', 'auto-resolved', 'closed')
                AND date(created_at) >= ? AND date(created_at) < ?
            """,
            date_range,
        ).fetchone()[0]
        received_by_day = {
            row["ticket_day"]: row["total"] for row in received_rows
        }
        resolved_by_day = {
            row["ticket_day"]: row["total"] for row in resolved_rows
        }
        days = []
        for offset in range(7):
            current_day = monday + timedelta(days=offset)
            day_key = current_day.isoformat()
            days.append({
                "date": day_key,
                "day": current_day.strftime("%A"),
                "received": received_by_day.get(day_key, 0),
                "resolved": resolved_by_day.get(day_key, 0),
            })
        return {
            "days": days,
            "period_start": monday.isoformat(),
            "uses_latest_activity_week": uses_latest_activity_week,
            "legacy_resolution_date_fallbacks": (
                legacy_resolution_date_fallbacks
            ),
        }
    finally:
        connection.close()


def get_escalation_status():
    connection = get_connection()
    try:
        row = connection.execute("""
            SELECT COUNT(*) AS classified,
                SUM(CASE WHEN ai_resolved = 1 THEN 1 ELSE 0 END) AS resolved,
                SUM(CASE WHEN escalated = 1 THEN 1 ELSE 0 END) AS escalated,
                SUM(CASE WHEN validation_status = 'Pending'
                    THEN 1 ELSE 0 END
                ) AS waiting_validation
            FROM tickets
            WHERE category IS NOT NULL AND TRIM(category) != ''
        """).fetchone()
        return {
            "classified": row["classified"] or 0,
            "automatically_resolved": row["resolved"] or 0,
            "escalated": row["escalated"] or 0,
            "waiting_validation": row["waiting_validation"] or 0,
        }
    finally:
        connection.close()


def record_api_metric(endpoint, duration_ms, status_code):
    connection = get_connection()
    try:
        connection.execute(
            "INSERT INTO api_metrics "
            "(endpoint, duration_ms, status_code) VALUES (?, ?, ?)",
            (endpoint, max(float(duration_ms), 0), int(status_code)),
        )
        connection.commit()
    finally:
        connection.close()


def get_all_tickets():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM tickets
        ORDER BY ticket_id DESC
    """)

    rows = cursor.fetchall()

    connection.close()

    return [
        dict(row)
        for row in rows
    ]


def delete_ticket(ticket_id):

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "DELETE FROM tickets WHERE ticket_id = ?",
        (ticket_id,)
    )
    deleted = cursor.rowcount > 0
    connection.commit()
    connection.close()

    return deleted
