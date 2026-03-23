from src.repositories.menu_repository import MenuRepository
from src.services.config_service import ConfigService


class MenuService:
    def __init__(self, config_service: ConfigService) -> None:
        self.config_service = config_service
        self.repository = MenuRepository()

    def bootstrap_menu(self) -> None:
        if self.repository.has_menu_data():
            return
        menu = self.config_service.get_menu()
        self.repository.replace_menu(menu["categories"])

    def list_menu(self) -> list[dict]:
        self.bootstrap_menu()
        return self.repository.list_menu()

    def update_menu(self, categories: list[dict]) -> list[dict]:
        self.repository.replace_menu(categories)
        return self.repository.list_menu()

    def get_menu_summary(self) -> str:
        categories = self.list_menu()
        if not categories:
            return "Aun no hay productos cargados."

        lines: list[str] = []
        for category in categories:
            active_items = [item for item in category["items"] if item["is_active"]]
            if not active_items:
                continue
            item_lines = ", ".join(
                f'{item["name"]} (S/ {item["price"]:.2f})'
                for item in active_items
            )
            lines.append(f'{category["name"]}: {item_lines}')
        return "\n".join(lines) if lines else "Aun no hay productos activos."

    def list_active_items(self) -> list[dict]:
        categories = self.list_menu()
        items: list[dict] = []
        for category in categories:
            for item in category["items"]:
                if item["is_active"]:
                    items.append(item)
        return items

    def get_item_category_map(self) -> dict[str, str]:
        categories = self.list_menu()
        mapping: dict[str, str] = {}
        for category in categories:
            for item in category["items"]:
                if item["is_active"]:
                    mapping[item["name"]] = category["name"]
        return mapping
