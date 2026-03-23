import httpx

from src.services.settings import Settings
from src.services.whatsapp_service import WhatsAppService


class NotificationService:
    def __init__(self, settings: Settings, whatsapp_service: WhatsAppService) -> None:
        self.settings = settings
        self.whatsapp_service = whatsapp_service

    async def notify_new_order(self, order: dict) -> None:
        notification_number = self.settings.whatsapp_notification_number
        if not notification_number:
            return

        message = self.build_order_notification(order)
        try:
            await self.whatsapp_service.send_text_message(notification_number, message)
        except httpx.HTTPError:
            print(f"[Aira notification warning] No se pudo notificar la orden {order['order_number']}.")

    async def notify_customer_status_update(self, order: dict) -> None:
        customer_phone = order.get("customer_phone")
        if not customer_phone:
            return

        message = self.build_customer_status_message(order)
        if not message:
            return

        try:
            await self.whatsapp_service.send_text_message(customer_phone, message)
        except httpx.HTTPError:
            print(f"[Aira notification warning] No se pudo avisar al cliente sobre {order['order_number']}.")

    @staticmethod
    def build_order_notification(order: dict) -> str:
        address = order.get("address") or "No aplica"
        reference_text = order.get("reference_text") or "Sin referencia"
        delivery_zone = order.get("delivery_zone")
        location_label = order.get("location_label")
        map_url = order.get("map_url")
        observations = order.get("observations") or "Sin observaciones"
        payment_method = order.get("payment_method") or "No especificado"
        cash_change_for = order.get("cash_change_for")
        items_block = NotificationService._build_items_block(order.get("parsed_order", {}).get("items", []))
        subtotal_line = f"\nSubtotal: S/ {order['subtotal']:.2f}" if order.get("subtotal") is not None else ""
        delivery_line = (
            f"\nDelivery: S/ {order['delivery_fee']:.2f}"
            if order.get("delivery_fee") is not None and order.get("order_type") == "Delivery"
            else ""
        )
        total_line = f"\nTotal final: S/ {order['total']:.2f}" if order.get("total") is not None else ""
        eta_line = f"\nTiempo estimado: {order['eta_label']}" if order.get("eta_label") else ""
        change_line = (
            f"\nVuelto: pagar con S/ {cash_change_for:.2f}"
            if cash_change_for is not None
            else ""
        )
        time_display = order.get("created_at_display") or order.get("created_at") or "Hora no disponible"
        return (
            f"Nueva orden: {order['order_number']}\n"
            f"Cliente: {order['customer_name']}\n"
            f"Telefono: {order['customer_phone']}\n"
            f"Tipo: Pedido\n"
            f"Detalle: {order['order_detail']}\n"
            f"{items_block}"
            f"Entrega: {order['order_type']}\n"
            f"Direccion: {address}\n"
            f"{NotificationService._build_zone_block(delivery_zone)}"
            f"Referencia: {reference_text}\n"
            f"{NotificationService._build_location_block(location_label, map_url)}"
            f"Pago: {payment_method}"
            f"{change_line}\n"
            f"Observaciones: {observations}\n"
            f"{eta_line}"
            f"{subtotal_line}"
            f"{delivery_line}"
            f"{total_line}\n"
            f"Hora: {time_display}"
        )

    @staticmethod
    def _build_items_block(items: list[dict]) -> str:
        if not items:
            return ""
        lines = ["Items:"]
        for item in items:
            lines.append(f"- {item['quantity']} x {item['name']} (S/ {item['subtotal']:.2f})")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _build_location_block(location_label: str | None, map_url: str | None) -> str:
        lines = []
        if location_label:
            lines.append(f"Ubicacion: {location_label}")
        if map_url:
            lines.append(f"Mapa: {map_url}")
        if not lines:
            return ""
        return "\n".join(lines) + "\n"

    @staticmethod
    def _build_zone_block(delivery_zone: str | None) -> str:
        if not delivery_zone:
            return ""
        return f"Zona delivery: {delivery_zone}\n"

    @staticmethod
    def build_customer_status_message(order: dict) -> str | None:
        status = (order.get("status") or "").lower().strip()
        customer_name = order.get("customer_name") or "cliente"
        order_number = order.get("order_number") or "tu pedido"

        templates = {
            "preparando": (
                f"Hola {customer_name}, tu pedido {order_number} ya esta en preparacion. "
                "Te avisaremos cuando siga avanzando."
            ),
            "en camino": (
                f"Hola {customer_name}, tu pedido {order_number} ya esta en camino. "
                "Gracias por tu paciencia."
            ),
            "entregado": (
                f"Hola {customer_name}, tu pedido {order_number} fue marcado como entregado. "
                "Gracias por tu compra."
            ),
            "cancelado": (
                f"Hola {customer_name}, tu pedido {order_number} fue cancelado. "
                "Si necesitas ayuda, puedes escribirnos por este mismo chat."
            ),
        }
        message = templates.get(status)
        if not message:
            return None
        eta_label = order.get("eta_label")
        if status == "preparando" and eta_label:
            return f"{message} {eta_label}."
        return message
