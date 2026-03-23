import re
import unicodedata

from src.services.config_service import ConfigService
from src.services.menu_service import MenuService


class OrderParserService:
    def __init__(self, menu_service: MenuService, config_service: ConfigService) -> None:
        self.menu_service = menu_service
        self.config_service = config_service
        self.language_dictionary = self.config_service.get_language_dictionary()

    def parse_order(self, order_detail: str | None) -> dict:
        if not order_detail:
            return {"items": [], "total": None, "modifiers": []}

        normalized_detail = self._normalize_with_dictionary(order_detail)
        normalized_detail = self._compact_whatsapp_style(normalized_detail)
        parsed_items: list[dict] = []
        matched_names: set[str] = set()

        for item in self.menu_service.list_active_items():
            names_to_match = self._names_to_match_for_item(item["name"])
            quantity, matched_name = self._extract_quantity_and_name(normalized_detail, names_to_match)
            if quantity <= 0:
                continue
            if matched_name in matched_names:
                continue
            matched_names.add(matched_name)
            parsed_items.append(
                {
                    "name": item["name"],
                    "quantity": quantity,
                    "unit_price": item["price"],
                    "subtotal": round(quantity * item["price"], 2),
                }
            )

        modifiers = self._extract_modifiers(order_detail, parsed_items)

        if not parsed_items:
            return {"items": [], "total": None, "modifiers": modifiers}

        total = round(sum(item["subtotal"] for item in parsed_items), 2)
        return {"items": parsed_items, "total": total, "modifiers": modifiers}

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
        normalized = re.sub(r"\b(?:oe|bro|mano|causa|amigo|amiga|pe|ps)\b", " ", normalized)
        return " ".join(normalized.split())

    def _names_to_match_for_item(self, item_name: str) -> list[str]:
        names = {self._normalize(item_name)}
        for alias in self.language_dictionary["product_aliases"].get(item_name, []):
            names.add(self._normalize(alias))

        normalized_name = self._normalize(item_name)
        words = normalized_name.split()
        stopwords = {"combo", "combos", "promo", "promocion", "promos", "burger", "hamburguesa"}

        if len(words) >= 2:
            names.add(" ".join(words[1:]))

        for word in words:
            if len(word) >= 4 and word not in stopwords:
                names.add(word)

        return sorted(names, key=len, reverse=True)

    def _extract_quantity_and_name(self, normalized_detail: str, normalized_names: list[str]) -> tuple[int, str | None]:
        sorted_names = sorted(set(normalized_names), key=len, reverse=True)

        quantity_words = {
            "un": 1,
            "una": 1,
            "uno": 1,
            "dos": 2,
            "tres": 3,
            "cuatro": 4,
            "cinco": 5,
            "seis": 6,
            "siete": 7,
            "ocho": 8,
            "nueve": 9,
            "diez": 10,
            "par": 2,
        }

        explicit_patterns = [
            r"\b(\d+)\s+{name}\b",
            r"\b(\d+)\s+de\s+{name}\b",
            r"\b(\d+)x\s+{name}\b",
            r"\bx(\d+)\s+{name}\b",
            r"\b{name}\s+x(\d+)\b",
            r"\b{name}\s+por\s+(\d+)\b",
            r"\b(un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+{name}\b",
            r"\b(un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+de\s+{name}\b",
            r"\bun\s+par\s+de\s+{name}\b",
            r"\bpar\s+de\s+{name}\b",
        ]

        for normalized_name in sorted_names:
            for raw_pattern in explicit_patterns:
                pattern = raw_pattern.format(name=re.escape(normalized_name))
                match = re.search(pattern, normalized_detail)
                if not match:
                    continue
                value = match.group(1) if match.groups() else None
                if value is None:
                    return 2, normalized_name
                if value.isdigit():
                    return int(value), normalized_name
                return quantity_words.get(value, 1), normalized_name

        for normalized_name in sorted_names:
            if normalized_name in normalized_detail:
                return 1, normalized_name

        return 0, None

    def _extract_modifiers(self, order_detail: str, parsed_items: list[dict]) -> list[str]:
        modifiers: list[str] = []
        detected_item_names = {
            self._normalize(item["name"])
            for item in parsed_items
        }
        patterns = [
            r"\bsin\s+([A-Za-zÁÉÍÓÚÑáéíóúñ ]{2,40}?)(?=,| y | con | extra | agrega| aparte |$)",
            r"\bcon\s+([A-Za-zÁÉÍÓÚÑáéíóúñ ]{2,40}?(?:\s+aparte)?)(?=,| y | sin | extra | agrega|$)",
            r"\bextra\s+([A-Za-zÁÉÍÓÚÑáéíóúñ ]{2,40}?)(?=,| y | con | sin | agrega|$)",
            r"\bagrega(?:le|r)?\s+([A-Za-zÁÉÍÓÚÑáéíóúñ ]{2,40}?)(?=,| y | con | sin | extra |$)",
            r"\baparte\s+([A-Za-zÁÉÍÓÚÑáéíóúñ ]{2,40}?)(?=,| y | con | sin | extra |$)",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, order_detail, flags=re.IGNORECASE):
                text = " ".join(match.group(0).strip(" ,.-").split())
                normalized_text = self._normalize(text)
                if any(item_name and item_name in normalized_text for item_name in detected_item_names):
                    continue
                if text and text.lower() not in {modifier.lower() for modifier in modifiers}:
                    modifiers.append(text)

        return modifiers
