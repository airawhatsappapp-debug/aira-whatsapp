import json
from functools import lru_cache
from pathlib import Path


class ConfigService:
    def __init__(self) -> None:
        config_dir = Path(__file__).resolve().parent.parent / "config"
        self._business_path = config_dir / "business.json"
        self._menu_path = config_dir / "menu.json"
        self._interaction_dictionary_path = config_dir / "interaction_dictionary.json"
        self._language_dictionary_path = config_dir / "language_dictionary.json"

    @lru_cache(maxsize=1)
    def get_business(self) -> dict:
        return json.loads(self._business_path.read_text(encoding="utf-8"))

    @lru_cache(maxsize=1)
    def get_menu(self) -> dict:
        return json.loads(self._menu_path.read_text(encoding="utf-8"))

    @lru_cache(maxsize=1)
    def get_interaction_dictionary(self) -> dict:
        return json.loads(self._interaction_dictionary_path.read_text(encoding="utf-8"))

    @lru_cache(maxsize=1)
    def get_language_dictionary(self) -> dict:
        return json.loads(self._language_dictionary_path.read_text(encoding="utf-8"))

    def update_business(self, business_data: dict) -> dict:
        current = self.get_business().copy()
        current.update(business_data)
        self._business_path.write_text(
            json.dumps(current, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.get_business.cache_clear()
        return self.get_business()

    def get_menu_summary(self) -> str:
        menu = self.get_menu()
        lines: list[str] = []
        for category in menu["categories"]:
            item_lines = ", ".join(
                f'{item["name"]} (S/ {item["price"]:.2f})'
                for item in category["items"]
            )
            lines.append(f'{category["name"]}: {item_lines}')
        return "\n".join(lines)
