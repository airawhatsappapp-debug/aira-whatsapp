from src.services.conversation_service import ConversationService
from src.services.whatsapp_service import WhatsAppService


class WebhookService:
    def __init__(
        self,
        conversation_service: ConversationService,
        whatsapp_service: WhatsAppService,
    ) -> None:
        self.conversation_service = conversation_service
        self.whatsapp_service = whatsapp_service

    async def handle_payload(self, payload: dict) -> None:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                for message in messages:
                    phone = message.get("from")
                    text = self._extract_message_text(message)
                    location_data = self._extract_location(message)
                    if not phone or (not text and not location_data):
                        continue
                    responses = await self.conversation_service.process_incoming_message(
                        phone,
                        text,
                        location_data=location_data,
                    )
                    for response in responses:
                        try:
                            await self.whatsapp_service.send_message(phone, response)
                        except ValueError:
                            fallback = response.get("fallback_text") or response.get("body", "")
                            if fallback:
                                await self.whatsapp_service.send_text_message(phone, fallback)

    @staticmethod
    def _extract_message_text(message: dict) -> str:
        message_type = message.get("type")
        if message_type == "text":
            return message.get("text", {}).get("body", "")
        if message_type != "interactive":
            return ""

        interactive = message.get("interactive", {})
        interactive_type = interactive.get("type")
        if interactive_type == "button_reply":
            reply = interactive.get("button_reply", {})
            return WebhookService._map_interactive_reply(reply.get("id"), reply.get("title"))
        if interactive_type == "list_reply":
            reply = interactive.get("list_reply", {})
            return WebhookService._map_interactive_reply(reply.get("id"), reply.get("title"))
        return ""

    @staticmethod
    def _map_interactive_reply(reply_id: str | None, reply_title: str | None) -> str:
        if not reply_id:
            return reply_title or ""
        if reply_id == "aira:delivery:delivery":
            return "delivery"
        if reply_id == "aira:delivery:pickup":
            return "recojo"
        if reply_id == "aira:payment:cash":
            return "efectivo"
        if reply_id == "aira:payment:yape":
            return "yape"
        if reply_id == "aira:payment:transfer":
            return "transferencia"
        if reply_id == "aira:confirm:yes":
            return "si"
        if reply_id == "aira:confirm:no":
            return "no"
        if reply_id == "aira:repeat:last-order":
            return "repite el ultimo pedido"
        if reply_id == "aira:show:menu":
            return "menu"
        if reply_id == "aira:show:categories":
            return "__show_menu__"
        if reply_id.startswith("aira:menu-category:"):
            return f"__show_category__:{reply_id.removeprefix('aira:menu-category:')}"
        if reply_id.startswith("aira:menu-item:"):
            return f"1 {reply_id.removeprefix('aira:menu-item:')}"
        return reply_title or reply_id

    @staticmethod
    def _extract_location(message: dict) -> dict | None:
        if message.get("type") != "location":
            return None
        location = message.get("location", {})
        latitude = location.get("latitude")
        longitude = location.get("longitude")
        if latitude is None or longitude is None:
            return None
        return {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "name": location.get("name"),
            "address": location.get("address"),
        }
