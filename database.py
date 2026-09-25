import sqlite3

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
            resolution
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        )
    ))

    ticket_id = cursor.lastrowid

    connection.commit()

    connection.close()

    return ticket_id


def update_ticket(
    ticket_id,
    status=None,
    resolution=None
):

    connection = get_connection()

    cursor = connection.cursor()

    if (
        status is not None
        and resolution is not None
    ):

        cursor.execute("""
            UPDATE tickets
            SET status = ?,
                resolution = ?
            WHERE ticket_id = ?
        """, (
            status,
            resolution,
            ticket_id
        ))

    elif status is not None:

        cursor.execute("""
            UPDATE tickets
            SET status = ?
            WHERE ticket_id = ?
        """, (
            status,
            ticket_id
        ))

    elif resolution is not None:

        cursor.execute("""
            UPDATE tickets
            SET resolution = ?
            WHERE ticket_id = ?
        """, (
            resolution,
            ticket_id
        ))

    connection.commit()

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
