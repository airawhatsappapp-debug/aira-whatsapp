from src.services.config_service import ConfigService


class InteractionService:
    def __init__(self, config_service: ConfigService) -> None:
        self.config_service = config_service

    def analyze(self, normalized_message: str, has_business_intent: bool) -> dict:
        dictionary = self.config_service.get_interaction_dictionary()
        matched_categories: list[str] = []

        for category_name, category_data in dictionary["categories"].items():
            if any(pattern in normalized_message for pattern in category_data["patterns"]):
                matched_categories.append(category_name)

        primary = self._pick_primary_category(matched_categories)
        if not primary:
            return {"matched": False, "response": None}

        response = dictionary["categories"][primary]["response"]
        if has_business_intent:
            if primary == "photo_request":
                return {"matched": True, "response": response, "allow_business_flow": True}
            if primary in {"flirty_redirect", "abusive_soft", "greeting_slang", "informal_menu_request"}:
                return {"matched": True, "response": response, "allow_business_flow": True}

        return {"matched": True, "response": response, "allow_business_flow": False}

    @staticmethod
    def _pick_primary_category(categories: list[str]) -> str | None:
        if not categories:
            return None

        priority = [
            "sexual_content",
            "abusive_hard",
            "abusive_soft",
            "photo_request",
            "flirty_redirect",
            "informal_menu_request",
            "greeting_slang",
        ]
        for category in priority:
            if category in categories:
                return category
        return categories[0]
