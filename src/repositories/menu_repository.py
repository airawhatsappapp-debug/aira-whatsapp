from src.db.database import get_connection


class MenuRepository:
    def has_menu_data(self) -> bool:
        with get_connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM menu_categories").fetchone()
        return bool(row["total"]) if row else False

    def replace_menu(self, categories: list[dict]) -> None:
        with get_connection() as connection:
            connection.execute("DELETE FROM menu_items")
            connection.execute("DELETE FROM menu_categories")

            for category_index, category in enumerate(categories):
                cursor = connection.execute(
                    """
                    INSERT INTO menu_categories (name, sort_order)
                    VALUES (?, ?)
                    """,
                    (category["name"], category_index),
                )
                category_id = cursor.lastrowid

                for item_index, item in enumerate(category["items"]):
                    connection.execute(
                        """
                        INSERT INTO menu_items (category_id, name, price, is_active, sort_order)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            category_id,
                            item["name"],
                            item["price"],
                            1 if item.get("is_active", True) else 0,
                            item_index,
                        ),
                    )

    def list_menu(self) -> list[dict]:
        with get_connection() as connection:
            categories = connection.execute(
                """
                SELECT id, name
                FROM menu_categories
                ORDER BY sort_order ASC, id ASC
                """
            ).fetchall()

            items = connection.execute(
                """
                SELECT id, category_id, name, price, is_active
                FROM menu_items
                ORDER BY sort_order ASC, id ASC
                """
            ).fetchall()

        items_by_category: dict[int, list[dict]] = {}
        for row in items:
            items_by_category.setdefault(row["category_id"], []).append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "price": row["price"],
                    "is_active": bool(row["is_active"]),
                }
            )

        return [
            {
                "id": category["id"],
                "name": category["name"],
                "items": items_by_category.get(category["id"], []),
            }
            for category in categories
        ]
