from src.db.database import get_connection


class MessageRepository:
    def log_message(self, direction: str, phone: str, message_text: str) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO message_logs (direction, phone, message_text)
                VALUES (?, ?, ?)
                """,
                (direction, phone, message_text),
            )

    def list_recent_messages(self, phone: str, limit: int = 12) -> list[dict]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT direction, phone, message_text, created_at
                FROM message_logs
                WHERE phone = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (phone, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]
