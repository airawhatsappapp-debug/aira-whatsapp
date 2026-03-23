from src.services.address_validation_service import AddressValidationService
from src.services.config_service import ConfigService
from src.services.conversation_service import ConversationService
from src.services.interaction_service import InteractionService
from src.services.message_understanding_service import MessageUnderstandingService
from src.services.menu_service import MenuService
from src.services.notification_service import NotificationService
from src.services.order_service import OrderService
from src.services.order_parser_service import OrderParserService
from src.services.settings import get_settings
from src.services.webhook_service import WebhookService
from src.services.whatsapp_service import WhatsAppService


class ServiceContainer:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.config_service = ConfigService()
        self.menu_service = MenuService(config_service=self.config_service)
        self.menu_service.bootstrap_menu()
        self.interaction_service = InteractionService(config_service=self.config_service)
        self.message_understanding_service = MessageUnderstandingService(
            config_service=self.config_service,
            menu_service=self.menu_service,
        )
        self.order_parser_service = OrderParserService(
            menu_service=self.menu_service,
            config_service=self.config_service,
        )
        self.whatsapp_service = WhatsAppService(settings=self.settings)
        self.address_validation_service = AddressValidationService(settings=self.settings)
        self.notification_service = NotificationService(
            settings=self.settings,
            whatsapp_service=self.whatsapp_service,
        )
        self.order_service = OrderService()
        self.conversation_service = ConversationService(
            config_service=self.config_service,
            interaction_service=self.interaction_service,
            message_understanding_service=self.message_understanding_service,
            menu_service=self.menu_service,
            order_parser_service=self.order_parser_service,
            order_service=self.order_service,
            notification_service=self.notification_service,
            address_validation_service=self.address_validation_service,
        )
        self.webhook_service = WebhookService(
            conversation_service=self.conversation_service,
            whatsapp_service=self.whatsapp_service,
        )
