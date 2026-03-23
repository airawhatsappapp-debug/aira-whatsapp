import json

from src.db.database import get_connection


class SessionRepository:
    def get_session(self, customer_phone: str) -> dict | None:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT stage, payload_json
                FROM conversation_sessions
                WHERE customer_phone = ?
                """,
                (customer_phone,),
            ).fetchone()
        if not row:
            return None
        return {
            "stage": row["stage"],
            "payload": json.loads(row["payload_json"]),
        }

    def save_session(self, customer_phone: str, stage: str, payload: dict) -> None:
        payload_json = json.dumps(payload, ensure_ascii=True)
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO conversation_sessions (customer_phone, stage, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT(customer_phone) DO UPDATE SET
                    stage = excluded.stage,
                    payload_json = excluded.payload_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (customer_phone, stage, payload_json),
            )

    def clear_session(self, customer_phone: str) -> None:
        with get_connection() as connection:
            connection.execute(
                "DELETE FROM conversation_sessions WHERE customer_phone = ?",
                (customer_phone,),
            )
