import re
import unicodedata

from src.services.config_service import ConfigService
from src.services.menu_service import MenuService


class MessageUnderstandingService:
    def __init__(self, config_service: ConfigService, menu_service: MenuService) -> None:
        self.config_service = config_service
        self.menu_service = menu_service
        self.language_dictionary = self.config_service.get_language_dictionary()

    def understand(self, message_text: str, stage: str) -> dict:
        normalized = self._normalize_with_dictionary(message_text)
        normalized = self._compact_whatsapp_style(normalized)
        return {
            "normalized": normalized,
            "greeting_only": normalized in {"hola", "hola aira", "buenas", "buenos dias", "buenas tardes", "buenas noches"},
            "asks_menu": self._asks_menu(normalized),
            "asks_hours": self._asks_hours(normalized),
            "asks_delivery_info": self._asks_delivery_info(normalized),
            "asks_location_help": self._asks_location_help(normalized),
            "asks_store_location": self._asks_store_location(normalized),
            "asks_payment_info": self._asks_payment_info(normalized),
            "asks_photos": self._asks_photos(normalized),
            "customer_name": self._extract_name(message_text, normalized),
            "delivery_type": self._extract_delivery_type(normalized),
            "address": self._extract_address(message_text, normalized, stage),
            "reference_text": self._extract_reference(message_text, normalized, stage),
            "observation": self._extract_partial_observation(message_text, normalized, stage),
            "observation_declined": self._declined_observation(normalized, stage),
            "reuse_last_observation": self._wants_same_observation(normalized),
            "reference_declined": self._declined_reference(normalized, stage),
            "order_detail": self._extract_order_detail(message_text, normalized),
            "payment_method": self._extract_payment_method(normalized),
            "reuse_last_address": self._wants_same_address(normalized),
            "reuse_last_payment": self._wants_same_payment(normalized),
            "reuse_last_order": self._wants_last_order(normalized),
            "cash_change_for": self._extract_cash_change_amount(normalized, stage),
            "cash_change_declined": self._declined_cash_change(normalized, stage),
            "confirmation": self._extract_confirmation(normalized, stage),
            "correction_intent": self._extract_correction_intent(normalized),
            "additive_order_intent": self._extract_additive_order_intent(normalized),
            "has_meaningful_data": self._has_meaningful_data(message_text, normalized),
        }

    @staticmethod
    def _normalize(value: str) -> str:
        ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
        cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", ascii_value.lower())
        return " ".join(cleaned.strip().split())

    def _normalize_with_dictionary(self, value: str) -> str:
        normalized = self._normalize(value)
        for source, target in self.language_dictionary["common_replacements"].items():
            normalized = re.sub(rf"\b{re.escape(source)}\b", target, normalized)
        return " ".join(normalized.split())

    @staticmethod
    def _compact_whatsapp_style(normalized: str) -> str:
        normalized = re.sub(r"\b(?:oe|oee|bro|mano|causa|amigo|amiga|amix|pe|ps)\b", " ", normalized)
        normalized = re.sub(r"\b(?:por favor|porfa|porfis)\b", " ", normalized)
        return " ".join(normalized.split())

    @staticmethod
    def _asks_menu(normalized: str) -> bool:
        return normalized in {"menu", "ver menu", "carta", "que tienen", "que vendes", "que ofrecen", "pasa menu", "manda menu"} or (
            "menu" in normalized and len(normalized.split()) <= 5
        )

    @staticmethod
    def _asks_hours(normalized: str) -> bool:
        keywords = ("horario", "hora", "atienden", "abren", "cierran", "estan abiertos", "estan atendiendo")
        return any(keyword in normalized for keyword in keywords)

    @staticmethod
    def _asks_delivery_info(normalized: str) -> bool:
        keywords = ("delivery", "envio", "envian", "reparto", "recojo", "recoger")
        return any(keyword in normalized for keyword in keywords) and "quiero" not in normalized

    @staticmethod
    def _asks_location_help(normalized: str) -> bool:
        keywords = ("ubicacion", "direccion", "donde estan", "local")
        return any(keyword in normalized for keyword in keywords) and "delivery" not in normalized

    @staticmethod
    def _asks_store_location(normalized: str) -> bool:
        keywords = ("donde estan", "ubicacion del local", "direccion del local", "como llegar", "local")
        return any(keyword in normalized for keyword in keywords) and "delivery" not in normalized

    @staticmethod
    def _asks_payment_info(normalized: str) -> bool:
        keywords = ("yape", "efectivo", "transferencia", "metodos de pago", "como pago", "formas de pago", "pago", "se puede pagar", "aceptan yape")
        return any(keyword in normalized for keyword in keywords)

    @staticmethod
    def _asks_photos(normalized: str) -> bool:
        keywords = ("foto", "fotos", "imagen", "imagenes", "local", "producto")
        return any(keyword in normalized for keyword in keywords)

    @staticmethod
    def _extract_name(message_text: str, normalized: str) -> str | None:
        match = re.search(
            r"\b(?:soy|me llamo|mi nombre es)\s+([A-Za-zÁÉÍÓÚÑáéíóúñ ]{2,40}?)(?=\s+(?:y|quiero|deseo|para|con)\b|[,.]|$)",
            message_text,
            flags=re.IGNORECASE,
        )
        if match:
            return " ".join(match.group(1).strip().split()).title()

        if normalized.startswith("sin "):
            return None

        if normalized and len(normalized.split()) <= 3 and all(part.isalpha() for part in normalized.split()):
            ignored = {
                "hola",
                "menu",
                "carta",
                "delivery",
                "recojo",
                "si",
                "no",
                "bro",
                "oe",
                "causa",
                "mano",
            }
            if normalized not in ignored:
                return " ".join(part.capitalize() for part in normalized.split())
        return None

    def _extract_delivery_type(self, normalized: str) -> str | None:
        if any(word in normalized for word in ("delivery", "envio", "enviar a casa", "para mi casa", "domicilio")):
            return "Delivery"
        if any(word in normalized for word in ("recojo", "recoger", "recojo en local", "paso a recoger", "voy por eso", "yo paso", "paso yo")):
            return "Recojo"
        if any(phrase in normalized for phrase in self.language_dictionary["peruvian_phrases"]["delivery"]):
            return "Delivery"
        if any(phrase in normalized for phrase in self.language_dictionary["peruvian_phrases"]["pickup"]):
            return "Recojo"
        return None

    @staticmethod
    def _extract_address(message_text: str, normalized: str, stage: str) -> str | None:
        address_markers = (
            "av ",
            "avenida",
            "calle",
            "jr ",
            "jiron",
            "mz ",
            "mza",
            "lote",
            "sector",
            "urbanizacion",
            "direccion",
            "altura",
            "cuadra",
            "numero",
        )
        if "direccion" in normalized:
            parts = re.split(r"direccion(?: es)?[: ]", message_text, flags=re.IGNORECASE)
            if len(parts) > 1 and parts[-1].strip():
                return parts[-1].strip()
        if any(prefix in normalized for prefix in ("estoy en", "mi direccion es", "vivo en")):
            parts = re.split(r"(?:estoy en|mi direccion es|vivo en)[: ]", message_text, flags=re.IGNORECASE)
            if len(parts) > 1 and parts[-1].strip():
                return parts[-1].strip()
        match = re.search(
            r"((?:av\.?|avenida|calle|jr\.?|jiron|mz\.?|mza|lote|sector|urbanizacion|altura|cuadra)\s+.*?)(?=\s+(?:sin|con|frente|costado|espalda|puerta|al lado|cerca)\b|$)",
            message_text,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1).strip(" ,.")
        if any(marker in normalized for marker in address_markers):
            return message_text.strip()
        if stage == "collect_address" and len(message_text.strip()) >= 6:
            return message_text.strip()
        return None

    @staticmethod
    def _extract_reference(message_text: str, normalized: str, stage: str) -> str | None:
        if "referencia" in normalized:
            parts = re.split(r"referencia(?: es)?[: ]", message_text, flags=re.IGNORECASE)
            if len(parts) > 1 and parts[-1].strip():
                return parts[-1].strip()

        if stage == "collect_reference":
            if normalized in {"no", "ninguna", "sin referencia"}:
                return None
            if len(message_text.strip()) >= 4:
                return message_text.strip()

        reference_markers = (
            "frente",
            "costado",
            "espalda",
            "puerta",
            "al lado",
            "cerca",
            "parque",
            "altura",
            "media cuadra",
            "tienda",
            "farmacia",
            "colegio",
            "mercado",
        )
        if any(marker in normalized for marker in reference_markers):
            return message_text.strip()
        return None

    @staticmethod
    def _extract_observation(message_text: str, normalized: str, stage: str) -> str | None:
        if stage == "collect_observations" and normalized and normalized not in {"no", "ninguna", "ninguno", "sin observaciones"}:
            return message_text.strip()

        match = re.search(r"\bsin\s+([A-Za-zÁÉÍÓÚÑáéíóúñ ]{2,40})", message_text, flags=re.IGNORECASE)
        if match:
            return f"Sin {match.group(1).strip()}"
        return None

    @staticmethod
    def _declined_observation(normalized: str, stage: str) -> bool:
        if stage != "collect_observations":
            return False
        return normalized in {"no", "ninguna", "ninguno", "sin observaciones"}

    @classmethod
    def _extract_partial_observation(cls, message_text: str, normalized: str, stage: str) -> str | None:
        if stage == "await_confirmation" and any(
            marker in normalized
            for marker in ("sin ", "con ", "extra ", "aparte", "dejalo igual", "solo cambia", "solo cambiale")
        ):
            return message_text.strip()
        return cls._extract_observation(message_text, normalized, stage)

    @staticmethod
    def _declined_reference(normalized: str, stage: str) -> bool:
        if stage != "collect_reference":
            return False
        return normalized in {"no", "ninguna", "sin referencia"}

    def _extract_order_detail(self, message_text: str, normalized: str) -> str | None:
        if self._looks_like_order(normalized):
            detail = message_text.strip()
            detail = re.sub(
                r"^\s*(hola|buenas|buenos dias|buenas tardes|buenas noches)[,:\s]*",
                "",
                detail,
                flags=re.IGNORECASE,
            )
            detail = re.sub(
                r"\b(?:soy|me llamo|mi nombre es)\s+[A-Za-zÁÉÍÓÚÑáéíóúñ ]{2,40}(?=\s+(?:y|quiero|deseo|para|con)\b|[,.]|$)",
                "",
                detail,
                flags=re.IGNORECASE,
            )
            keyword_match = re.search(r"\b(?:quiero|deseo|me da|me das)\s+(.+)$", detail, flags=re.IGNORECASE)
            if keyword_match:
                detail = keyword_match.group(1).strip()

            detail = re.sub(
                r"^\s*(mejor|mejorcito|cambialo(?:\s+por)?|cambialo\s+a|cambiala(?:\s+por)?|ya\s+no(?:\s+quiero)?|ahora\s+quiero|mas\s+bien)\s+",
                "",
                detail,
                flags=re.IGNORECASE,
            )

            detail = re.sub(r"\b(?:para\s+)?delivery\b.*$", "", detail, flags=re.IGNORECASE)
            detail = re.sub(r"\b(?:para\s+)?recojo\b.*$", "", detail, flags=re.IGNORECASE)
            detail = re.sub(r"\bpara\s+llevar\b.*$", "", detail, flags=re.IGNORECASE)
            detail = re.sub(r"\bpaso a recoger\b.*$", "", detail, flags=re.IGNORECASE)
            detail = re.sub(r"\bsin\s+[A-Za-zÁÉÍÓÚÑáéíóúñ ]{2,40}$", "", detail, flags=re.IGNORECASE)
            detail = detail.strip(" ,.-")
            return detail or message_text.strip()
        return None

    def _looks_like_order(self, normalized: str) -> bool:
        if any(phrase in normalized for phrase in ("quiero ", "deseo ", "me da", "me das", "para pedir", "pedido", "dame ", "separa ", "me apuntas", "me anotas")):
            return True
        if any(phrase in normalized for phrase in self.language_dictionary["peruvian_phrases"]["order"]):
            return True

        active_items = self._active_menu_item_names()
        return any(item_name in normalized for item_name in active_items)

    @staticmethod
    def _extract_payment_method(normalized: str) -> str | None:
        if "efectivo" in normalized:
            return "Efectivo"
        if "yape" in normalized:
            return "Yape"
        if "transferencia" in normalized or "transferir" in normalized:
            return "Transferencia"
        return None

    @staticmethod
    def _wants_same_address(normalized: str) -> bool:
        phrases = (
            "misma direccion",
            "la misma direccion",
            "usar la misma direccion",
            "mi direccion de siempre",
            "la direccion de siempre",
            "direccion anterior",
            "usa mi direccion",
        )
        return any(phrase in normalized for phrase in phrases)

    @staticmethod
    def _wants_same_payment(normalized: str) -> bool:
        phrases = (
            "mismo pago",
            "el mismo pago",
            "igual pago",
            "paga como siempre",
            "pago como siempre",
            "usa yape de siempre",
            "pago de siempre",
        )
        return any(phrase in normalized for phrase in phrases)

    @staticmethod
    def _wants_last_order(normalized: str) -> bool:
        phrases = (
            "lo mismo",
            "el mismo pedido",
            "mi pedido de siempre",
            "repite el ultimo",
            "repite mi ultimo pedido",
            "repetir ultimo pedido",
            "lo de siempre",
            "igual que la ultima vez",
        )
        return any(phrase in normalized for phrase in phrases)

    @staticmethod
    def _wants_same_observation(normalized: str) -> bool:
        phrases = (
            "misma observacion",
            "la misma observacion",
            "observacion de siempre",
            "igual observacion",
            "usa la misma indicacion",
        )
        return any(phrase in normalized for phrase in phrases)

    @staticmethod
    def _extract_cash_change_amount(normalized: str, stage: str) -> float | None:
        if stage != "collect_cash_change":
            return None

        match = re.search(r"(?:con|pago con|tengo)\s+(\d+(?:\.\d{1,2})?)", normalized)
        if match:
            return float(match.group(1))

        only_number = re.fullmatch(r"\d+(?:\.\d{1,2})?", normalized)
        if only_number:
            return float(normalized)
        return None

    @staticmethod
    def _declined_cash_change(normalized: str, stage: str) -> bool:
        if stage != "collect_cash_change":
            return False
        return normalized in {"no", "sencillo", "con sencillo", "no necesito vuelto"}

    @staticmethod
    def _extract_confirmation(normalized: str, stage: str) -> str | None:
        if stage != "await_confirmation":
            return None
        if normalized in {"si", "confirmar", "ok", "dale", "correcto", "yes", "listo", "ya", "ta bien"}:
            return "confirm"
        if normalized in {"no", "cambiar", "editar", "corregir", "todavia no"}:
            return "deny"
        return None

    @staticmethod
    def _extract_correction_intent(normalized: str) -> bool:
        correction_markers = (
            "mejor ",
            "mas bien",
            "cambialo",
            "cambiala",
            "cambiale",
            "quitale",
            "sacale",
            "dejalo igual pero",
            "dejala igual pero",
            "corregir",
            "correccion",
            "editar pedido",
            "ya no ",
            "ahora quiero",
            "reemplaza",
            "reemplazar",
        )
        return any(marker in normalized for marker in correction_markers)

    @staticmethod
    def _extract_additive_order_intent(normalized: str) -> bool:
        additive_markers = (
            "agrega ",
            "agregale ",
            "sumale ",
            "metele ",
            "ponle ",
            "anade ",
            "añade ",
            "tambien ",
            "tambien agrega ",
        )
        return any(marker in normalized for marker in additive_markers)

    def _active_menu_item_names(self) -> list[str]:
        categories = self.menu_service.list_menu()
        names: set[str] = set()
        for category in categories:
            for item in category["items"]:
                if item["is_active"]:
                    names.add(self._normalize(item["name"]))
                    for alias in self.language_dictionary["product_aliases"].get(item["name"], []):
                        names.add(self._normalize(alias))

                    normalized_name = self._normalize(item["name"])
                    words = normalized_name.split()
                    stopwords = {"combo", "combos", "promo", "promocion", "promos", "burger", "hamburguesa"}

                    if len(words) >= 2:
                        names.add(" ".join(words[1:]))

                    for word in words:
                        if len(word) >= 4 and word not in stopwords:
                            names.add(word)
        return list(names)

    def _has_meaningful_data(self, message_text: str, normalized: str) -> bool:
        return any(
            [
                self._extract_name(message_text, normalized),
                self._extract_delivery_type(normalized),
                self._extract_address(message_text, normalized, ""),
                self._extract_observation(message_text, normalized, ""),
                self._extract_order_detail(message_text, normalized),
                self._asks_menu(normalized),
                self._asks_hours(normalized),
                self._asks_delivery_info(normalized),
                self._asks_location_help(normalized),
                self._asks_store_location(normalized),
                self._asks_payment_info(normalized),
                self._asks_photos(normalized),
                self._extract_reference(message_text, normalized, ""),
                self._extract_payment_method(normalized),
            ]
        )
