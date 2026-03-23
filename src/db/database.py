import sqlite3
from pathlib import Path

from src.services.settings import get_settings


def get_connection() -> sqlite3.Connection:
    settings = get_settings()
    database_path = Path(settings.database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def bootstrap_database() -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    with get_connection() as connection:
        connection.executescript(schema_path.read_text(encoding="utf-8"))
        _ensure_customer_columns(connection)
        _ensure_order_columns(connection)
        _ensure_support_tables(connection)


def _ensure_customer_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(customers)").fetchall()
    }
    required_columns = {
        "internal_note": "TEXT",
    }

    for column_name, column_type in required_columns.items():
        if column_name in existing_columns:
            continue
        connection.execute(f"ALTER TABLE customers ADD COLUMN {column_name} {column_type}")


def _ensure_order_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(orders)").fetchall()
    }
    required_columns = {
        "reference_text": "TEXT",
        "delivery_zone": "TEXT",
        "location_label": "TEXT",
        "location_latitude": "REAL",
        "location_longitude": "REAL",
        "map_url": "TEXT",
        "payment_method": "TEXT",
        "cash_change_for": "REAL",
        "subtotal": "REAL",
        "delivery_fee": "REAL",
        "total": "REAL",
        "internal_note": "TEXT",
    }

    for column_name, column_type in required_columns.items():
        if column_name in existing_columns:
            continue
        connection.execute(f"ALTER TABLE orders ADD COLUMN {column_name} {column_type}")


def _ensure_support_tables(connection: sqlite3.Connection) -> None:
    existing_tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "order_events" not in existing_tables:
        connection.execute(
            """
            CREATE TABLE order_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT NOT NULL,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
