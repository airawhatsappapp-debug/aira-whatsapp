from src.db.database import get_connection
from src.models.schemas import OrderRecord


class OrderRepository:
    def record_order_event(self, order_number: str, event_type: str, title: str, detail: str | None) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO order_events (order_number, event_type, title, detail)
                VALUES (?, ?, ?, ?)
                """,
                (order_number, event_type, title, detail),
            )

    def create_order(
        self,
        order_number: str,
        customer_phone: str,
        customer_name: str,
        order_type: str,
        order_detail: str,
        address: str | None,
        reference_text: str | None,
        delivery_zone: str | None,
        location_label: str | None,
        location_latitude: float | None,
        location_longitude: float | None,
        map_url: str | None,
        observations: str | None,
        payment_method: str | None,
        cash_change_for: float | None,
        subtotal: float | None,
        delivery_fee: float | None,
        total: float | None,
        status: str = "nuevo",
    ) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO orders (
                    order_number,
                    customer_phone,
                    customer_name,
                    order_type,
                    order_detail,
                    address,
                    reference_text,
                    delivery_zone,
                    location_label,
                    location_latitude,
                    location_longitude,
                    map_url,
                    observations,
                    payment_method,
                    cash_change_for,
                    subtotal,
                    delivery_fee,
                    total,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_number,
                    customer_phone,
                    customer_name,
                    order_type,
                    order_detail,
                    address,
                    reference_text,
                    delivery_zone,
                    location_label,
                    location_latitude,
                    location_longitude,
                    map_url,
                    observations,
                    payment_method,
                    cash_change_for,
                    subtotal,
                    delivery_fee,
                    total,
                    status,
                ),
            )
            connection.execute(
                """
                INSERT INTO order_events (order_number, event_type, title, detail)
                VALUES (?, ?, ?, ?)
                """,
                (
                    order_number,
                    "order_created",
                    "Pedido creado",
                    f"{customer_name} | {order_type} | {order_detail}",
                ),
            )

    def list_orders(self, limit: int = 20) -> list[OrderRecord]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT
                       o.order_number,
                       o.customer_phone,
                       o.customer_name,
                       (
                           SELECT COUNT(*)
                           FROM orders o2
                           WHERE o2.customer_phone = o.customer_phone
                       ) AS customer_total_orders,
                       c.internal_note AS customer_note,
                       o.order_type,
                       o.order_detail,
                       o.address,
                       o.reference_text,
                       o.delivery_zone,
                       o.location_label,
                       o.location_latitude,
                       o.location_longitude,
                       o.map_url,
                       o.observations,
                       o.internal_note,
                       o.payment_method,
                       o.cash_change_for,
                       o.subtotal,
                       o.delivery_fee,
                       o.total,
                       o.status,
                       o.created_at
                FROM orders o
                LEFT JOIN customers c ON c.phone = o.customer_phone
                ORDER BY o.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [OrderRecord(**dict(row)) for row in rows]

    def count_orders_for_date(self, date_prefix: str) -> int:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM orders
                WHERE order_number LIKE ?
                """,
                (f"AIRA-{date_prefix}-%",),
            ).fetchone()
        return int(row["total"]) if row else 0

    def get_order_by_number(self, order_number: str) -> OrderRecord | None:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT
                       o.order_number,
                       o.customer_phone,
                       o.customer_name,
                       (
                           SELECT COUNT(*)
                           FROM orders o2
                           WHERE o2.customer_phone = o.customer_phone
                       ) AS customer_total_orders,
                       c.internal_note AS customer_note,
                       o.order_type,
                       o.order_detail,
                       o.address,
                       o.reference_text,
                       o.delivery_zone,
                       o.location_label,
                       o.location_latitude,
                       o.location_longitude,
                       o.map_url,
                       o.observations,
                       o.internal_note,
                       o.payment_method,
                       o.cash_change_for,
                       o.subtotal,
                       o.delivery_fee,
                       o.total,
                       o.status,
                       o.created_at
                FROM orders o
                LEFT JOIN customers c ON c.phone = o.customer_phone
                WHERE o.order_number = ?
                """,
                (order_number,),
            ).fetchone()
        return OrderRecord(**dict(row)) if row else None

    def update_order_status(self, order_number: str, status: str) -> OrderRecord | None:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE orders
                SET status = ?
                WHERE order_number = ?
                """,
                (status, order_number),
            )
            connection.execute(
                """
                INSERT INTO order_events (order_number, event_type, title, detail)
                VALUES (?, ?, ?, ?)
                """,
                (
                    order_number,
                    "status_changed",
                    "Estado actualizado",
                    status,
                ),
            )
        return self.get_order_by_number(order_number)

    def update_order_note(self, order_number: str, note: str | None) -> OrderRecord | None:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE orders
                SET internal_note = ?
                WHERE order_number = ?
                """,
                ((note or "").strip() or None, order_number),
            )
            connection.execute(
                """
                INSERT INTO order_events (order_number, event_type, title, detail)
                VALUES (?, ?, ?, ?)
                """,
                (
                    order_number,
                    "internal_note",
                    "Nota interna actualizada",
                    (note or "").strip() or "Sin nota",
                ),
            )
        return self.get_order_by_number(order_number)

    def list_order_events(self, order_number: str) -> list[dict]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT event_type, title, detail, created_at
                FROM order_events
                WHERE order_number = ?
                ORDER BY created_at ASC, id ASC
                """,
                (order_number,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_order_summary(self) -> dict:
        with get_connection() as connection:
            totals_row = connection.execute(
                """
                SELECT COUNT(*) AS total_orders, COALESCE(SUM(total), 0) AS total_revenue
                FROM orders
                """
            ).fetchone()
            status_rows = connection.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM orders
                GROUP BY status
                """
            ).fetchall()

        by_status = {row["status"]: int(row["total"]) for row in status_rows}
        return {
            "total_orders": int(totals_row["total_orders"]) if totals_row else 0,
            "total_revenue": float(totals_row["total_revenue"]) if totals_row else 0.0,
            "by_status": by_status,
        }

    def get_customer_operational_summary(self, customer_phone: str) -> dict:
        with get_connection() as connection:
            customer_row = connection.execute(
                """
                SELECT internal_note
                FROM customers
                WHERE phone = ?
                """,
                (customer_phone,),
            ).fetchone()

            totals_row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_orders,
                    MAX(created_at) AS last_order_at
                FROM orders
                WHERE customer_phone = ?
                """,
                (customer_phone,),
            ).fetchone()

            preferred_order_type_row = connection.execute(
                """
                SELECT order_type, COUNT(*) AS total
                FROM orders
                WHERE customer_phone = ?
                GROUP BY order_type
                ORDER BY total DESC, MAX(created_at) DESC
                LIMIT 1
                """,
                (customer_phone,),
            ).fetchone()

            preferred_payment_row = connection.execute(
                """
                SELECT payment_method, COUNT(*) AS total
                FROM orders
                WHERE customer_phone = ? AND payment_method IS NOT NULL AND payment_method != ''
                GROUP BY payment_method
                ORDER BY total DESC, MAX(created_at) DESC
                LIMIT 1
                """,
                (customer_phone,),
            ).fetchone()

            preferred_observation_row = connection.execute(
                """
                SELECT observations, COUNT(*) AS total
                FROM orders
                WHERE customer_phone = ? AND observations IS NOT NULL AND observations != ''
                GROUP BY observations
                ORDER BY total DESC, MAX(created_at) DESC
                LIMIT 1
                """,
                (customer_phone,),
            ).fetchone()

            latest_delivery_row = connection.execute(
                """
                SELECT address, reference_text
                FROM orders
                WHERE customer_phone = ? AND (address IS NOT NULL OR reference_text IS NOT NULL)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (customer_phone,),
            ).fetchone()

            recent_rows = connection.execute(
                """
                SELECT order_number, order_detail, order_type, payment_method, total, status, created_at
                FROM orders
                WHERE customer_phone = ?
                ORDER BY created_at DESC
                LIMIT 5
                """,
                (customer_phone,),
            ).fetchall()

        return {
            "total_orders": int(totals_row["total_orders"]) if totals_row else 0,
            "last_order_at": totals_row["last_order_at"] if totals_row else None,
            "customer_note": customer_row["internal_note"] if customer_row else None,
            "preferred_order_type": preferred_order_type_row["order_type"] if preferred_order_type_row else None,
            "preferred_payment_method": preferred_payment_row["payment_method"] if preferred_payment_row else None,
            "preferred_observation": preferred_observation_row["observations"] if preferred_observation_row else None,
            "last_address": latest_delivery_row["address"] if latest_delivery_row else None,
            "last_reference_text": latest_delivery_row["reference_text"] if latest_delivery_row else None,
            "recent_orders": [dict(row) for row in recent_rows],
        }
