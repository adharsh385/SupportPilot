import sqlite3

from werkzeug.security import check_password_hash, generate_password_hash

from config import (
    DATABASE_PATH
)


def get_connection():

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""

        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT UNIQUE NOT NULL,

            email TEXT UNIQUE NOT NULL,

            password_hash TEXT NOT NULL

        )

    """)

    cursor.execute("""

        CREATE TABLE IF NOT EXISTS tickets (

            ticket_id INTEGER
            PRIMARY KEY AUTOINCREMENT,

            employee_name TEXT,

            email TEXT,

            department TEXT,

            title TEXT NOT NULL,

            description TEXT NOT NULL,

            category TEXT,

            severity TEXT,

            priority TEXT,

            confidence REAL,

            status TEXT DEFAULT 'Open',

            created_at TIMESTAMP
            DEFAULT CURRENT_TIMESTAMP

        )

    """)

    conn.commit()

    conn.close()


def save_ticket(ticket):

    conn = get_connection()

    cursor = conn.cursor()

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

            status

        )

        VALUES (

            ?, ?, ?, ?, ?,

            ?, ?, ?, ?, ?

        )

    """, (

        ticket.get(
            "employee_name",
            ""
        ),

        ticket.get(
            "email",
            ""
        ),

        ticket.get(
            "department",
            ""
        ),

        ticket["title"],

        ticket["description"],

        ticket["category"],

        ticket["severity"],

        ticket["priority"],

        ticket["confidence"],

        ticket.get(
            "status",
            "Open"
        )

    ))

    conn.commit()

    ticket_id = (
        cursor.lastrowid
    )

    conn.close()

    return ticket_id


def create_user(username, email, password):

    conn = get_connection()

    try:

        cursor = conn.execute(
            """
            INSERT INTO users (username, email, password_hash)
            VALUES (?, ?, ?)
            """,
            (username, email, generate_password_hash(password))
        )

        conn.commit()
        return cursor.lastrowid

    except sqlite3.IntegrityError:

        return None

    finally:

        conn.close()


def authenticate_user(username, password):

    conn = get_connection()

    user = conn.execute(
        """
        SELECT id, username, email, password_hash
        FROM users
        WHERE username = ? OR email = ?
        """,
        (username, username)
    ).fetchone()

    conn.close()

    if user and check_password_hash(user["password_hash"], password):

        return dict(user)

    return None


def get_all_tickets():

    conn = get_connection()

    tickets = conn.execute(
        """
        SELECT * FROM tickets
        WHERE status != 'Deleted'
        ORDER BY created_at DESC, ticket_id DESC
        """
    ).fetchall()

    conn.close()

    return [dict(ticket) for ticket in tickets]


def delete_ticket(ticket_id):

    conn = get_connection()

    cursor = conn.execute(
        "UPDATE tickets SET status = 'Deleted' WHERE ticket_id = ?",
        (ticket_id,)
    )

    conn.commit()
    conn.close()

    return cursor.rowcount > 0