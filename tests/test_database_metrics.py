import sqlite3

import pytest

import database


def _create_legacy_ticket_table(database_path):
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE tickets (
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.commit()
    connection.close()


def test_database_migrates_metrics_and_persists_feedback(tmp_path, monkeypatch):
    database_path = tmp_path / "tickets.db"
    _create_legacy_ticket_table(database_path)
    monkeypatch.setattr(database, "DATABASE_PATH", database_path)

    database.initialize_database()
    ticket_id = database.save_ticket(
        {
            "employee_name": "Test User",
            "email": "test@example.com",
            "department": "Support",
            "title": "Test ticket",
            "description": "Test description",
            "category": "Network",
            "severity": "Low",
            "priority": "P4",
            "confidence": 65.0,
            "status": "Resolved",
            "resolution": "Test resolution",
        }
    )
    database.update_ticket(
        ticket_id,
        ai_processing_time_seconds=1.25,
        csat=4,
    )

    connection = sqlite3.connect(database_path)
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(tickets)")
    }
    ticket = connection.execute(
        """
        SELECT ai_processing_time_seconds, csat
        FROM tickets
        WHERE ticket_id = ?
        """,
        (ticket_id,),
    ).fetchone()
    connection.close()

    assert {"ai_processing_time_seconds", "csat"} <= columns
    assert ticket == (1.25, 4.0)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"csat": 0}, "between 1 and 5"),
        ({"csat": 6}, "between 1 and 5"),
        ({"ai_processing_time_seconds": -0.1}, "cannot be negative"),
    ],
)
def test_database_rejects_invalid_metrics(kwargs, message, tmp_path, monkeypatch):
    database_path = tmp_path / "tickets.db"
    _create_legacy_ticket_table(database_path)
    monkeypatch.setattr(database, "DATABASE_PATH", database_path)
    database.initialize_database()

    with pytest.raises(ValueError, match=message):
        database.update_ticket(1, **kwargs)
