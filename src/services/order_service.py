from datetime import datetime
import re
import unicodedata

from src.repositories.order_repository import OrderRepository
from src.services.config_service import ConfigService


class OrderService:
    def __init__(self) -> None:
        self.repository = OrderRepository()
        self.config_service = ConfigService()

    def create_order(self, customer_phone: str, session_data: dict) -> dict:
        order_number = self._generate_order_number()
        customer_name = session_data["customer_name"]
        order_type = session_data["delivery_type"]
        order_detail = session_data["order_detail"]
        address = session_data.get("address")
        reference_text = session_data.get("reference_text")
        location = session_data.get("location") or {}
        location_label = location.get("label")
        delivery_zone, delivery_fee = self._resolve_delivery_zone_and_fee(
            address or location_label,
            order_type,
        )
        location_latitude = location.get("latitude")
        location_longitude = location.get("longitude")
        map_url = self._build_map_url(location_latitude, location_longitude)
        observations = session_data.get("observations")
        payment_method = session_data.get("payment_method")
        cash_change_for = session_data.get("cash_change_for")
        parsed_order = session_data.get("parsed_order") or {"items": [], "total": None}
        subtotal = parsed_order.get("total")
        total = round((subtotal or 0) + delivery_fee, 2) if subtotal is not None else None
        estimated_minutes = self._estimate_minutes(order_type)
        eta_label = self._build_eta_label(order_type, estimated_minutes)

        self.repository.create_order(
            order_number=order_number,
            customer_phone=customer_phone,
            customer_name=customer_name,
            order_type=order_type,
            order_detail=order_detail,
            address=address,
            reference_text=reference_text,
            delivery_zone=delivery_zone,
            location_label=location_label,
            location_latitude=location_latitude,
            location_longitude=location_longitude,
            map_url=map_url,
            observations=observations,
            payment_method=payment_method,
            cash_change_for=cash_change_for,
            subtotal=subtotal,
            delivery_fee=delivery_fee,
            total=total,
        )

        return {
            "order_number": order_number,
            "customer_phone": customer_phone,
            "customer_name": customer_name,
            "order_type": order_type,
            "order_detail": order_detail,
            "address": address,
            "reference_text": reference_text,
            "delivery_zone": delivery_zone,
            "location_label": location_label,
            "location_latitude": location_latitude,
            "location_longitude": location_longitude,
            "map_url": map_url,
            "observations": observations,
            "payment_method": payment_method,
            "cash_change_for": cash_change_for,
            "parsed_order": parsed_order,
            "subtotal": subtotal,
            "delivery_fee": delivery_fee,
            "total": total,
            "estimated_minutes": estimated_minutes,
            "eta_label": eta_label,
            "created_at_display": datetime.now().strftime("%I:%M %p"),
        }

    def _generate_order_number(self) -> str:
        today = datetime.now().strftime("%Y%m%d")
        total_today = self.repository.count_orders_for_date(today)
        sequence = total_today + 1
        return f"AIRA-{today}-{sequence:04d}"

    def _calculate_delivery_fee(self, order_type: str | None) -> float:
        if order_type != "Delivery":
            return 0.0
        business = self.config_service.get_business()
        return float(business.get("default_delivery_fee", 0.0))

    def _estimate_minutes(self, order_type: str | None) -> int | None:
        business = self.config_service.get_business()
        if order_type == "Delivery":
            return int(business.get("delivery_eta_minutes", 45))
        if order_type == "Recojo":
            return int(business.get("pickup_eta_minutes", 20))
        return None

    @staticmethod
    def _build_eta_label(order_type: str | None, minutes: int | None) -> str | None:
        if minutes is None:
            return None
        if order_type == "Delivery":
            return f"Entrega estimada en {minutes} min"
        if order_type == "Recojo":
            return f"Recojo estimado en {minutes} min"
        return None

    def _resolve_delivery_zone_and_fee(
        self,
        location_text: str | None,
        order_type: str | None,
    ) -> tuple[str | None, float]:
        if order_type != "Delivery":
            return None, 0.0

        business = self.config_service.get_business()
        normalized_location = self._normalize(location_text or "")
        for zone_name, fee in business.get("delivery_zone_fees", {}).items():
            if self._normalize(zone_name) in normalized_location:
                return zone_name, float(fee)
        return None, self._calculate_delivery_fee(order_type)

    @staticmethod
    def _build_map_url(latitude: float | None, longitude: float | None) -> str | None:
        if latitude is None or longitude is None:
            return None
        return f"https://maps.google.com/?q={latitude},{longitude}"

    @staticmethod
    def _normalize(value: str) -> str:
        ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
        cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", ascii_value.lower())
        return " ".join(cleaned.strip().split())
