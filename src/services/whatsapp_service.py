import httpx

from src.services.settings import Settings


class WhatsAppService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send_text_message(self, to_phone: str, body: str) -> None:
        await self._send_payload(
            to_phone,
            {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "text",
                "text": {"body": body},
            },
        )

    async def send_reply_buttons(
        self,
        to_phone: str,
        body: str,
        buttons: list[dict],
        footer: str | None = None,
    ) -> None:
        if not buttons or len(buttons) > 3:
            raise ValueError("Reply buttons must contain between 1 and 3 options.")

        payload_buttons = []
        for button in buttons:
            title = button["title"].strip()
            if not title:
                raise ValueError("Reply button title cannot be empty.")
            payload_buttons.append(
                {
                    "type": "reply",
                    "reply": {
                        "id": button["id"],
                        "title": title[:20],
                    },
                }
            )

        interactive_payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body[:1024]},
                "action": {"buttons": payload_buttons},
            },
        }
        if footer:
            interactive_payload["interactive"]["footer"] = {"text": footer[:60]}

        await self._send_payload(to_phone, interactive_payload)

    async def send_list_message(
        self,
        to_phone: str,
        body: str,
        button_text: str,
        sections: list[dict],
        header_text: str | None = None,
        footer: str | None = None,
    ) -> None:
        total_rows = sum(len(section.get("rows", [])) for section in sections)
        if not sections or total_rows == 0 or total_rows > 10:
            raise ValueError("List messages must contain between 1 and 10 rows.")

        interactive_sections = []
        for section in sections:
            rows = []
            for row in section.get("rows", []):
                title = row["title"].strip()
                if not title:
                    raise ValueError("List row title cannot be empty.")
                rows.append(
                    {
                        "id": row["id"],
                        "title": title[:24],
                        "description": row.get("description", "")[:72],
                    }
                )
            interactive_sections.append(
                {
                    "title": section["title"][:24],
                    "rows": rows,
                }
            )

        interactive_payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body[:1024]},
                "action": {
                    "button": button_text[:20],
                    "sections": interactive_sections,
                },
            },
        }
        if header_text:
            interactive_payload["interactive"]["header"] = {
                "type": "text",
                "text": header_text[:60],
            }
        if footer:
            interactive_payload["interactive"]["footer"] = {"text": footer[:60]}

        await self._send_payload(to_phone, interactive_payload)

    async def send_message(self, to_phone: str, message: dict) -> None:
        message_type = message.get("type", "text")
        if message_type == "text":
            await self.send_text_message(to_phone, message["body"])
            return
        if message_type == "reply_buttons":
            await self.send_reply_buttons(
                to_phone=to_phone,
                body=message["body"],
                buttons=message["buttons"],
                footer=message.get("footer"),
            )
            return
        if message_type == "list":
            await self.send_list_message(
                to_phone=to_phone,
                body=message["body"],
                button_text=message["button_text"],
                sections=message["sections"],
                header_text=message.get("header"),
                footer=message.get("footer"),
            )
            return
        raise ValueError(f"Unsupported outbound message type: {message_type}")

    async def _send_payload(self, to_phone: str, payload: dict) -> None:
        if not self.settings.whatsapp_access_token or not self.settings.whatsapp_phone_number_id:
            print(f"[Aira mock send] To: {to_phone} | Payload: {payload}")
            return

        url = (
            "https://graph.facebook.com/v23.0/"
            f"{self.settings.whatsapp_phone_number_id}/messages"
        )
        headers = {
            "Authorization": f"Bearer {self.settings.whatsapp_access_token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
