from src.db.database import get_connection


class CustomerRepository:
    def upsert_customer(self, phone: str, name: str | None = None) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO customers (phone, name)
                VALUES (?, ?)
                ON CONFLICT(phone) DO UPDATE SET
                    name = COALESCE(excluded.name, customers.name),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (phone, name),
            )

    def get_customer(self, phone: str):
        with get_connection() as connection:
            row = connection.execute(
                "SELECT phone, name, internal_note FROM customers WHERE phone = ?",
                (phone,),
            ).fetchone()
        return dict(row) if row else None

    def update_customer_note(self, phone: str, note: str | None) -> dict | None:
        normalized_note = (note or "").strip() or None
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO customers (phone, internal_note)
                VALUES (?, ?)
                ON CONFLICT(phone) DO UPDATE SET
                    internal_note = excluded.internal_note,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (phone, normalized_note),
            )
        return self.get_customer(phone)
