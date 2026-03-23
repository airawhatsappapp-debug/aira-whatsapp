import re
import unicodedata

from src.repositories.customer_repository import CustomerRepository
from src.repositories.message_repository import MessageRepository
from src.repositories.session_repository import SessionRepository
from src.services.config_service import ConfigService
from src.services.interaction_service import InteractionService
from src.services.menu_service import MenuService
from src.services.message_understanding_service import MessageUnderstandingService
from src.services.notification_service import NotificationService
from src.services.order_service import OrderService
from src.services.order_parser_service import OrderParserService
from src.services.address_validation_service import AddressValidationService


class ConversationService:
    def __init__(
        self,
        config_service: ConfigService,
        interaction_service: InteractionService,
        message_understanding_service: MessageUnderstandingService,
        menu_service: MenuService,
        order_parser_service: OrderParserService,
        order_service: OrderService,
        notification_service: NotificationService,
        address_validation_service: AddressValidationService,
    ) -> None:
        self.config_service = config_service
        self.interaction_service = interaction_service
        self.message_understanding_service = message_understanding_service
        self.menu_service = menu_service
        self.order_parser_service = order_parser_service
        self.order_service = order_service
        self.notification_service = notification_service
        self.address_validation_service = address_validation_service
        self.order_repository = order_service.repository
        self.customer_repository = CustomerRepository()
        self.message_repository = MessageRepository()
        self.session_repository = SessionRepository()

    async def process_incoming_message(
        self,
        phone: str,
        message_text: str,
        location_data: dict | None = None,
    ) -> list[dict]:
        clean_text = message_text.strip()
        inbound_preview = clean_text or self._preview_location(location_data)
        self.message_repository.log_message("inbound", phone, inbound_preview)

        customer = self.customer_repository.get_customer(phone)
        customer_memory = self._get_customer_memory(phone, customer["name"] if customer else None)
        session = self.session_repository.get_session(phone)

        if self._is_reset_request(clean_text):
            payload = self._build_base_payload(
                customer_name=customer["name"] if customer else None,
                customer_memory=customer_memory,
            )
            stage = "collect_order_detail" if payload["customer_name"] else "collect_name"
            self.session_repository.save_session(phone, stage, payload)
            response = self._text_message(
                self._welcome_message(
                    customer_name=payload["customer_name"],
                    customer_memory=payload.get("customer_memory"),
                )
            )
            self.message_repository.log_message("outbound", phone, self._preview_message(response))
            return [response]

        if not session:
            payload = self._build_base_payload(
                customer_name=customer["name"] if customer else None,
                customer_memory=customer_memory,
            )
            stage = "collect_order_detail" if payload["customer_name"] else "collect_name"

            analysis = self.message_understanding_service.understand(clean_text, stage)
            if analysis["greeting_only"] and not analysis["has_meaningful_data"]:
                self.session_repository.save_session(phone, stage, payload)
                if location_data:
                    self._apply_location_to_payload(payload, location_data)
                response = self._text_message(
                    self._welcome_message(
                        customer_name=payload["customer_name"],
                        customer_memory=payload.get("customer_memory"),
                    )
                )
                self.message_repository.log_message("outbound", phone, self._preview_message(response))
                return [response]

            responses = await self._advance_session(phone, clean_text, stage, payload, location_data=location_data)
            for response in responses:
                self.message_repository.log_message("outbound", phone, self._preview_message(response))
            return responses

        session["payload"] = self._hydrate_payload(session["payload"])
        if not session["payload"].get("customer_memory"):
            session["payload"]["customer_memory"] = customer_memory
        responses = await self._advance_session(
            phone,
            clean_text,
            session["stage"],
            session["payload"],
            location_data=location_data,
        )
        for response in responses:
            self.message_repository.log_message("outbound", phone, self._preview_message(response))
        return responses

    async def _advance_session(
        self,
        phone: str,
        message_text: str,
        stage: str,
        payload: dict,
        location_data: dict | None = None,
    ) -> list[dict]:
        analysis = self.message_understanding_service.understand(message_text, stage)
        interaction = self.interaction_service.analyze(
            analysis["normalized"],
            has_business_intent=any(
                [
                    analysis["asks_menu"],
                    analysis["asks_hours"],
                    analysis["asks_delivery_info"],
                    analysis["asks_location_help"],
                    analysis["asks_store_location"],
                    analysis["asks_payment_info"],
                    analysis["asks_photos"],
                    analysis["order_detail"],
                    analysis["delivery_type"],
                    analysis["address"],
                ]
            ),
        )
        self._apply_analysis_to_payload(payload, analysis, stage)
        if location_data:
            self._apply_location_to_payload(payload, location_data)

        faq_responses = self._build_info_responses(analysis, stage)

        if stage == "confirm_validated_address":
            return self._handle_address_validation_confirmation(phone, payload, analysis, faq_responses)

        if (
            stage == "collect_address"
            and payload.get("delivery_type") == "Delivery"
            and payload.get("address")
            and not payload.get("location")
            and not payload.get("validated_address")
            and not payload.get("address_validation_skipped")
        ):
            validation_response = await self._maybe_validate_address(phone, payload)
            if validation_response:
                return validation_response
        if interaction["matched"] and not interaction["allow_business_flow"]:
            self.session_repository.save_session(phone, stage, payload)
            return [self._text_message(interaction["response"])]

        if self._should_pause_flow(analysis, interaction):
            responses = self._build_pause_flow_responses(stage, payload, faq_responses, interaction)
            self.session_repository.save_session(phone, stage, payload)
            return responses

        if interaction["matched"] and interaction["response"]:
            faq_responses = [interaction["response"]] + faq_responses

        if not payload["customer_name"]:
            if faq_responses and not any(
                [
                    payload["order_detail"],
                    payload["delivery_type"],
                    payload["address"],
                    payload["payment_method"],
                ]
            ):
                self.session_repository.save_session(phone, "collect_name", payload)
                return self._compose_messages(
                    faq_responses + ["Si luego quieres hacer un pedido, me compartes tu nombre y te ayudo al instante."]
                )
            if payload["order_detail"] or payload["delivery_type"] or payload["address"]:
                self.session_repository.save_session(phone, stage, payload)
                prompt = "Antes de confirmar, me compartes tu nombre?"
                if faq_responses:
                    return self._compose_messages(faq_responses + [prompt])
                return [self._text_message(prompt)]
            self.session_repository.save_session(phone, "collect_name", payload)
            if faq_responses:
                return self._compose_messages(faq_responses + ["Antes de continuar, me compartes tu nombre?"])
            return [self._text_message(self._welcome_message(customer_name=None, customer_memory=payload.get("customer_memory")))]

        self.customer_repository.upsert_customer(phone, payload["customer_name"])

        if not payload["order_detail"]:
            self.session_repository.save_session(phone, "collect_order_detail", payload)
            if analysis["asks_menu"]:
                return [
                    self._text_message(self._menu_prompt()),
                    self._menu_list_message(),
                    self._text_message("Cuando quieras, dime que te gustaria pedir."),
                ]
            if self._should_offer_last_order(payload):
                if faq_responses:
                    return self._compose_messages(
                        faq_responses + [self._last_order_prompt(payload)],
                        extra_messages=[self._last_order_buttons_message()],
                    )
                return [
                    self._text_message(self._last_order_prompt(payload)),
                    self._last_order_buttons_message(),
                ]
            if faq_responses:
                return self._compose_messages(
                    faq_responses + ["Cuando quieras, dime que te gustaria pedir y yo lo registro."],
                    extra_messages=[self._menu_list_message()],
                )
            return [
                self._text_message(
                    f"Encantada, {payload['customer_name']}. "
                    "Cuentame que te gustaria pedir y yo lo voy registrando.\n"
                    f"{self._menu_prompt()}"
                ),
                self._menu_list_message(),
            ]

        if not payload["delivery_type"]:
            self.session_repository.save_session(phone, "collect_delivery_type", payload)
            delivery_prompt = self._delivery_prompt(payload)
            suggestion_message = self._build_soft_commercial_suggestion(payload)
            if faq_responses:
                extra_messages = []
                if suggestion_message:
                    extra_messages.append(self._text_message(suggestion_message))
                extra_messages.append(self._delivery_buttons_message(delivery_prompt))
                return self._compose_messages(faq_responses, extra_messages=extra_messages)
            responses = []
            if suggestion_message:
                responses.append(self._text_message(suggestion_message))
            responses.append(self._delivery_buttons_message(delivery_prompt))
            return responses

        if payload["delivery_type"] == "Delivery" and not payload["address"]:
            self.session_repository.save_session(phone, "collect_address", payload)
            if analysis["asks_location_help"]:
                return [self._text_message("Puedes escribirme tu direccion exacta o compartirme tu ubicacion por WhatsApp para seguir con el pedido.")]
            if faq_responses:
                return self._compose_messages(faq_responses + [self._address_prompt(payload)])
            return [self._text_message(self._address_prompt(payload))]

        if payload["delivery_type"] == "Delivery" and not payload["reference_collected"]:
            self.session_repository.save_session(phone, "collect_reference", payload)
            reference_prompt = (
                "Perfecto. Si deseas, agregame una referencia para ubicar mejor la entrega, por ejemplo: "
                "'frente al parque', 'puerta negra' o 'al costado de la farmacia'. Si no tienes, escribe 'no'."
            )
            if faq_responses:
                return self._compose_messages(faq_responses + [reference_prompt])
            return [self._text_message(reference_prompt)]

        if not payload["payment_method"]:
            self.session_repository.save_session(phone, "collect_payment_method", payload)
            payment_prompt = self._payment_prompt(payload)
            if faq_responses:
                return self._compose_messages(
                    faq_responses,
                    extra_messages=[self._payment_buttons_message(payment_prompt)],
                )
            return [self._payment_buttons_message(payment_prompt)]

        if payload["payment_method"] == "Efectivo" and not payload["cash_change_collected"]:
            self.session_repository.save_session(phone, "collect_cash_change", payload)
            if faq_responses:
                return self._compose_messages(faq_responses + ["Si necesitas vuelto, dime con cuanto pagaras. Si tienes sencillo, escribe 'no'."])
            return [self._text_message("Si necesitas vuelto, dime con cuanto pagaras. Si tienes sencillo, escribe 'no'.")]

        if not payload["observations_collected"]:
            self.session_repository.save_session(phone, "collect_observations", payload)
            observations_prompt = self._observations_prompt(payload)
            if faq_responses:
                return self._compose_messages(faq_responses + [observations_prompt])
            return [self._text_message(observations_prompt)]

        if stage == "await_confirmation" or analysis["confirmation"]:
            if analysis["confirmation"] == "confirm":
                order = self.order_service.create_order(phone, payload)
                await self.notification_service.notify_new_order(order)
                self.session_repository.clear_session(phone)
                return [
                    self._text_message(self._build_success_message(order)),
                    self._text_message("Si mas tarde quieres hacer otro pedido, solo escribe 'nuevo pedido'."),
                ]

            if analysis["confirmation"] == "deny":
                payload["order_detail"] = None
                payload["parsed_order"] = {"items": [], "total": None}
                payload["delivery_type"] = None
                payload["address"] = None
                payload["reference_text"] = None
                payload["reference_collected"] = False
                payload["payment_method"] = None
                payload["cash_change_for"] = None
                payload["cash_change_collected"] = False
                payload["observations"] = None
                payload["observations_collected"] = False
                self.session_repository.save_session(phone, "collect_order_detail", payload)
                return [self._text_message("Claro. Escribeme nuevamente el detalle correcto de tu pedido.")]

            self.session_repository.save_session(phone, "await_confirmation", payload)
            if faq_responses:
                return self._compose_messages(
                    faq_responses,
                    extra_messages=[
                        self._text_message(self._build_customer_summary(payload)),
                        self._confirmation_buttons_message(),
                    ],
                )
            return [
                self._text_message(self._build_customer_summary(payload)),
                self._confirmation_buttons_message(),
            ]

        self.session_repository.save_session(phone, "await_confirmation", payload)
        if faq_responses:
            return self._compose_messages(
                faq_responses,
                extra_messages=[
                    self._text_message(self._build_customer_summary(payload)),
                    self._confirmation_buttons_message(),
                ],
            )
        return [
            self._text_message(self._build_customer_summary(payload)),
            self._confirmation_buttons_message(),
        ]

    def _apply_analysis_to_payload(self, payload: dict, analysis: dict, stage: str) -> None:
        if analysis["customer_name"] and not payload.get("customer_name"):
            payload["customer_name"] = analysis["customer_name"]

        should_replace_order = bool(
            analysis["order_detail"]
            and (
                not payload.get("order_detail")
                or analysis.get("correction_intent")
                or stage in {"collect_order_detail", "await_confirmation"}
            )
        )
        should_add_to_order = bool(
            analysis["order_detail"]
            and payload.get("order_detail")
            and analysis.get("additive_order_intent")
            and not analysis.get("correction_intent")
        )

        if should_replace_order:
            previous_detail = payload.get("order_detail")
            payload["order_detail"] = analysis["order_detail"]
            payload["parsed_order"] = self.order_parser_service.parse_order(payload["order_detail"])
            clean_detail = self._clean_detail_from_parsed_order(payload["parsed_order"])
            if clean_detail:
                payload["order_detail"] = clean_detail
            if previous_detail and previous_detail != payload["order_detail"]:
                self._reset_after_order_change(payload)
                payload["order_updated_notice"] = True

        elif should_add_to_order:
            merged_detail = f"{payload['order_detail']}, {analysis['order_detail']}"
            payload["order_detail"] = merged_detail
            payload["parsed_order"] = self.order_parser_service.parse_order(payload["order_detail"])
            clean_detail = self._clean_detail_from_parsed_order(payload["parsed_order"])
            if clean_detail:
                payload["order_detail"] = clean_detail
            payload["order_updated_notice"] = True

        if analysis["delivery_type"]:
            if payload.get("delivery_type") and payload.get("delivery_type") != analysis["delivery_type"]:
                payload["order_updated_notice"] = True
            payload["delivery_type"] = analysis["delivery_type"]

        if analysis["address"]:
            if payload.get("address") and payload.get("address") != analysis["address"]:
                payload["order_updated_notice"] = True
            payload["address"] = analysis["address"]
            if not payload.get("delivery_type"):
                payload["delivery_type"] = "Delivery"

        if analysis["reference_text"]:
            if payload.get("reference_text") and payload.get("reference_text") != analysis["reference_text"]:
                payload["order_updated_notice"] = True
            payload["reference_text"] = analysis["reference_text"]
            payload["reference_collected"] = True

        if analysis["reference_declined"]:
            if payload.get("reference_text"):
                payload["order_updated_notice"] = True
            payload["reference_text"] = None
            payload["reference_collected"] = True

        if analysis["payment_method"]:
            if payload.get("payment_method") and payload.get("payment_method") != analysis["payment_method"]:
                payload["order_updated_notice"] = True
            payload["payment_method"] = analysis["payment_method"]

        customer_memory = payload.get("customer_memory") or {}
        if analysis.get("reuse_last_order"):
            latest_order = self._latest_customer_order(customer_memory)
            if latest_order:
                previous_detail = payload.get("order_detail")
                payload["order_detail"] = latest_order["order_detail"]
                payload["parsed_order"] = self.order_parser_service.parse_order(payload["order_detail"])
                clean_detail = self._clean_detail_from_parsed_order(payload["parsed_order"])
                if clean_detail:
                    payload["order_detail"] = clean_detail
                if latest_order.get("order_type"):
                    payload["delivery_type"] = latest_order["order_type"]
                if latest_order.get("order_type") == "Delivery":
                    payload["address"] = customer_memory.get("last_address")
                    payload["reference_text"] = customer_memory.get("last_reference_text")
                    payload["reference_collected"] = bool(
                        customer_memory.get("last_reference_text")
                    )
                if latest_order.get("payment_method"):
                    payload["payment_method"] = latest_order["payment_method"]
                if previous_detail != payload["order_detail"]:
                    self._reset_after_order_change(payload)
                    payload["order_updated_notice"] = True

        if analysis.get("reuse_last_address") and customer_memory.get("last_address"):
            if payload.get("address") != customer_memory["last_address"]:
                payload["order_updated_notice"] = True
            payload["address"] = customer_memory["last_address"]
            payload["delivery_type"] = payload.get("delivery_type") or "Delivery"
            if customer_memory.get("last_reference_text"):
                payload["reference_text"] = customer_memory["last_reference_text"]
                payload["reference_collected"] = True

        if analysis.get("reuse_last_payment") and customer_memory.get("preferred_payment_method"):
            if payload.get("payment_method") != customer_memory["preferred_payment_method"]:
                payload["order_updated_notice"] = True
            payload["payment_method"] = customer_memory["preferred_payment_method"]

        if analysis.get("reuse_last_observation") and customer_memory.get("preferred_observation"):
            if payload.get("observations") != customer_memory["preferred_observation"]:
                payload["order_updated_notice"] = True
            payload["observations"] = customer_memory["preferred_observation"]
            payload["observations_collected"] = True

        if analysis["cash_change_for"] is not None:
            if payload.get("cash_change_for") is not None and payload.get("cash_change_for") != analysis["cash_change_for"]:
                payload["order_updated_notice"] = True
            payload["cash_change_for"] = analysis["cash_change_for"]
            payload["cash_change_collected"] = True

        if analysis["cash_change_declined"]:
            if payload.get("cash_change_for") is not None:
                payload["order_updated_notice"] = True
            payload["cash_change_for"] = None
            payload["cash_change_collected"] = True

        if analysis["observation"]:
            if payload.get("observations") and payload.get("observations") != analysis["observation"]:
                payload["order_updated_notice"] = True
            payload["observations"] = analysis["observation"]
            payload["observations_collected"] = True

        if analysis["observation_declined"]:
            if payload.get("observations"):
                payload["order_updated_notice"] = True
            payload["observations"] = None
            payload["observations_collected"] = True

    @staticmethod
    def _reset_after_order_change(payload: dict) -> None:
        payload["observations"] = None
        payload["observations_collected"] = False
        payload["cash_change_for"] = None
        payload["cash_change_collected"] = False

    def _build_info_responses(self, analysis: dict, stage: str) -> list[str]:
        business = self.config_service.get_business()
        responses: list[str] = []

        if analysis["asks_menu"]:
            responses.append(self._menu_prompt())

        if analysis["asks_hours"]:
            responses.append(f"Nuestro horario es: {business['business_hours']}.")

        if analysis["asks_delivery_info"] and not (stage == "collect_delivery_type" and analysis["delivery_type"]):
            zone_fees = business.get("delivery_zone_fees", {})
            if zone_fees:
                zones = ", ".join(f"{zone}: S/ {fee:.2f}" for zone, fee in zone_fees.items())
            else:
                zones = ", ".join(business.get("delivery_zones", [])) or "consulta las zonas con el negocio"
            responses.append(f"Trabajamos con delivery y recojo. Zonas de delivery: {zones}.")

        if analysis["asks_location_help"]:
            responses.append("Si tu pedido es delivery, puedes escribirme tu direccion, compartirme tu ubicacion o agregar una referencia como 'frente al parque' o 'puerta negra'.")

        if analysis["asks_store_location"]:
            responses.append(f"Nos ubicamos en {business.get('business_address', 'la direccion del local esta disponible en el negocio')}.")

        if analysis["asks_payment_info"] and not (stage == "collect_payment_method" and analysis["payment_method"]):
            methods = ", ".join(business.get("payment_methods", [])) or "Efectivo"
            payment_details = business.get("payment_details", {})
            extra_details = []
            if payment_details.get("yape"):
                extra_details.append(payment_details["yape"])
            if payment_details.get("transferencia"):
                extra_details.append(payment_details["transferencia"])
            details_line = f" {' '.join(extra_details)}" if extra_details else ""
            responses.append(f"Aceptamos estos metodos de pago: {methods}.{details_line}")

        if analysis["asks_photos"]:
            responses.append("Por ahora puedo ayudarte con el menu, informacion de productos y ubicacion del negocio.")

        return responses

    def _build_base_payload(self, customer_name: str | None, customer_memory: dict | None = None) -> dict:
        return {
            "customer_name": customer_name,
            "customer_memory": customer_memory,
            "order_detail": None,
            "parsed_order": {"items": [], "total": None},
            "order_updated_notice": False,
            "delivery_type": None,
            "address": None,
            "reference_text": None,
            "reference_collected": False,
            "location": None,
            "validated_address": None,
            "address_validation_candidate": None,
            "address_validation_skipped": False,
            "payment_method": None,
            "cash_change_for": None,
            "cash_change_collected": False,
            "observations": None,
            "observations_collected": False,
        }

    def _hydrate_payload(self, payload: dict | None) -> dict:
        hydrated = self._build_base_payload(customer_name=None)
        if payload:
            hydrated.update(payload)
        if not hydrated.get("parsed_order") and hydrated.get("order_detail"):
            hydrated["parsed_order"] = self.order_parser_service.parse_order(hydrated["order_detail"])
        clean_detail = self._clean_detail_from_parsed_order(hydrated["parsed_order"])
        if clean_detail:
            hydrated["order_detail"] = clean_detail
        return hydrated

    def _welcome_message(self, customer_name: str | None, customer_memory: dict | None = None) -> str:
        business = self.config_service.get_business()
        memory_line = self._build_memory_welcome(customer_memory)
        if customer_name:
            return (
                f"Hola {customer_name}, soy {business['assistant_name']}. "
                "Estoy lista para ayudarte con tu pedido. "
                f"{memory_line}"
                "Dime que te gustaria pedir cuando quieras."
            )
        return (
            f"{business['greeting']}\n"
            "Antes de empezar, me compartes tu nombre?"
        )

    def _build_customer_summary(self, payload: dict) -> str:
        address = payload.get("address") or "No aplica"
        reference_text = payload.get("reference_text") or "Sin referencia"
        location = payload.get("location") or {}
        delivery_zone, delivery_fee = self._resolve_delivery_zone_and_fee(payload)
        eta_label = self._estimate_eta_label(payload.get("delivery_type"))
        location_label = location.get("label")
        map_url = self._build_map_url(location.get("latitude"), location.get("longitude"))
        observations = payload.get("observations") or "Sin observaciones"
        payment_method = payload.get("payment_method") or "No especificado"
        cash_change_for = payload.get("cash_change_for")
        parsed_order = payload.get("parsed_order") or {"items": [], "total": None}
        subtotal = parsed_order.get("total")
        total = round((subtotal or 0) + delivery_fee, 2) if subtotal is not None else None
        items_block = self._build_items_summary(parsed_order.get("items", []), parsed_order.get("modifiers", []))
        subtotal_line = f"Subtotal: S/ {subtotal:.2f}\n" if subtotal is not None else ""
        delivery_line = (
            f"Delivery: S/ {delivery_fee:.2f}\n"
            if total is not None and payload.get("delivery_type") == "Delivery"
            else ""
        )
        total_line = f"Total final: S/ {total:.2f}\n" if total is not None else ""
        eta_line = f"{eta_label}\n" if eta_label else ""
        cash_change_line = (
            f"Pago en efectivo con: S/ {cash_change_for:.2f}\n"
            if cash_change_for is not None
            else ""
        )
        updated_line = "Actualice tu pedido con el nuevo detalle.\n" if payload.get("order_updated_notice") else ""
        payload["order_updated_notice"] = False
        return (
            f"{updated_line}Te resumo el pedido para confirmar:\n"
            f"Cliente: {payload['customer_name']}\n"
            f"Detalle: {payload['order_detail']}\n"
            f"{items_block}"
            f"Entrega: {payload['delivery_type']}\n"
            f"Direccion: {address}\n"
            f"{self._build_zone_summary(delivery_zone)}"
            f"Referencia: {reference_text}\n"
            f"{self._build_location_summary(location_label, map_url)}"
            f"Pago: {payment_method}\n"
            f"{cash_change_line}"
            f"Observaciones: {observations}\n"
            f"{eta_line}"
            f"{subtotal_line}"
            f"{delivery_line}"
            f"{total_line}"
            "Responde 'si' para confirmar o 'no' para corregir."
        )

    def _build_success_message(self, order: dict) -> str:
        total_line = f"\nTotal final: S/ {order['total']:.2f}" if order.get("total") is not None else ""
        eta_line = f"\n{order['eta_label']}" if order.get("eta_label") else ""
        return (
            f"Listo, tu pedido fue confirmado. Tu numero de orden es {order['order_number']}.\n"
            f"Detalle: {order['order_detail']}\n"
            f"Entrega: {order['order_type']}"
            f"{eta_line}"
            f"{total_line}"
        )

    def _menu_prompt(self) -> str:
        return f"Menu rapido:\n{self.menu_service.get_menu_summary()}"

    @staticmethod
    def _build_memory_welcome(customer_memory: dict | None) -> str:
        if not customer_memory or customer_memory.get("total_orders", 0) <= 0:
            return ""
        parts = [f"Veo que ya hiciste {customer_memory['total_orders']} pedido(s) con nosotros."]
        if customer_memory.get("preferred_order_type"):
            parts.append(f"Tu entrega mas frecuente es {customer_memory['preferred_order_type'].lower()}.")
        if customer_memory.get("preferred_payment_method"):
            parts.append(f"Tu pago mas frecuente es {customer_memory['preferred_payment_method'].lower()}.")
        favorite_items = customer_memory.get("favorite_items") or []
        if favorite_items:
            parts.append(f"Tus favoritos suelen ser: {', '.join(favorite_items[:2])}.")
        if customer_memory.get("customer_note"):
            parts.append("Ya tengo en cuenta tus indicaciones registradas para atenderte mejor.")
        return " ".join(parts) + " "

    def _estimate_eta_label(self, order_type: str | None) -> str | None:
        business = self.config_service.get_business()
        if order_type == "Delivery":
            minutes = int(business.get("delivery_eta_minutes", 45))
            return f"Entrega estimada: {minutes} min"
        if order_type == "Recojo":
            minutes = int(business.get("pickup_eta_minutes", 20))
            return f"Recojo estimado: {minutes} min"
        return None

    def _build_soft_commercial_suggestion(self, payload: dict) -> str | None:
        parsed_order = payload.get("parsed_order") or {}
        current_items = {item["name"] for item in parsed_order.get("items", [])}
        category_map = self.menu_service.get_item_category_map()
        current_categories = {
            category_map[item_name]
            for item_name in current_items
            if item_name in category_map
        }

        business = self.config_service.get_business()
        for rule in business.get("cross_sell_rules", []):
            trigger_category = (rule.get("trigger_category") or "").strip()
            suggested_item = (rule.get("suggested_item") or "").strip()
            if not trigger_category or not suggested_item:
                continue
            if trigger_category not in current_categories:
                continue
            if suggested_item in current_items:
                continue
            custom_message = (rule.get("message") or "").strip()
            if custom_message:
                return custom_message
            return f"Si quieres, tambien puedo agregarte {suggested_item} para complementar tu pedido."

        customer_memory = payload.get("customer_memory") or {}
        favorites = customer_memory.get("favorite_items") or []
        if not favorites:
            return None

        preferred_candidate = None
        preferred_category_keywords = ("bebida", "acompanamiento", "acompañamiento", "complemento")
        for favorite in favorites:
            if favorite in current_items:
                continue
            category_name = category_map.get(favorite, "")
            normalized_category = self._normalize(category_name)
            if any(keyword in normalized_category for keyword in preferred_category_keywords):
                if category_name not in current_categories:
                    preferred_candidate = favorite
                    break

        if not preferred_candidate:
            for favorite in favorites:
                if favorite not in current_items:
                    preferred_candidate = favorite
                    break

        if not preferred_candidate:
            return None

        return (
            f"Si quieres, tambien puedo agregarte tu favorito {preferred_candidate}. "
            "Solo escribelo ahora y lo sumo al pedido."
        )

    def _delivery_prompt(self, payload: dict) -> str:
        customer_memory = payload.get("customer_memory") or {}
        preferred = customer_memory.get("preferred_order_type")
        if preferred:
            return (
                f"Perfecto. Tu forma de entrega mas frecuente es {preferred.lower()}. "
                "Elige si esta vez sera delivery o recojo."
            )
        return "Perfecto. Tu pedido sera para delivery o prefieres recojo?"

    def _address_prompt(self, payload: dict) -> str:
        customer_memory = payload.get("customer_memory") or {}
        last_address = customer_memory.get("last_address")
        if last_address:
            return (
                "Listo, sera delivery. Comparteme la direccion de entrega, por favor. "
                f"Si quieres usar la ultima direccion registrada, escribe 'usar la misma direccion': {last_address}"
            )
        return "Listo, sera delivery. Comparteme la direccion de entrega, por favor."

    async def _maybe_validate_address(self, phone: str, payload: dict) -> list[dict] | None:
        suggestion = await self.address_validation_service.suggest_address(payload.get("address"))
        if not suggestion:
            payload["address_validation_skipped"] = True
            self.session_repository.save_session(phone, "collect_reference", payload)
            return None

        payload["address_validation_candidate"] = suggestion
        self.session_repository.save_session(phone, "confirm_validated_address", payload)
        body = (
            "Encontre esta direccion sugerida en Google Maps:\n"
            f"{suggestion['formatted_address']}\n"
            "Responde 'si' para usarla o 'no' para mantener la que escribiste."
        )
        return [
            self._text_message(body),
            self._confirmation_buttons_message(),
        ]

    def _handle_address_validation_confirmation(
        self,
        phone: str,
        payload: dict,
        analysis: dict,
        faq_responses: list[str],
    ) -> list[dict]:
        candidate = payload.get("address_validation_candidate") or {}
        if analysis["confirmation"] == "confirm" and candidate.get("formatted_address"):
            payload["address"] = candidate["formatted_address"]
            payload["validated_address"] = candidate["formatted_address"]
            if candidate.get("latitude") is not None and candidate.get("longitude") is not None:
                payload["location"] = {
                    "latitude": candidate.get("latitude"),
                    "longitude": candidate.get("longitude"),
                    "label": candidate.get("formatted_address"),
                }
            payload["address_validation_skipped"] = True
            payload["address_validation_candidate"] = None
            self.session_repository.save_session(phone, "collect_reference", payload)
            responses = faq_responses + [
                "Perfecto. Usare esa direccion validada. Si deseas, ahora agregame una referencia para ubicar mejor la entrega. Si no tienes, escribe 'no'."
            ]
            return self._compose_messages(responses)

        if analysis["confirmation"] == "deny":
            payload["address_validation_skipped"] = True
            payload["address_validation_candidate"] = None
            self.session_repository.save_session(phone, "collect_reference", payload)
            responses = faq_responses + [
                "Perfecto. Mantendre la direccion que escribiste. Si deseas, ahora agregame una referencia para ubicar mejor la entrega. Si no tienes, escribe 'no'."
            ]
            return self._compose_messages(responses)

        self.session_repository.save_session(phone, "confirm_validated_address", payload)
        responses = faq_responses + [
            "Solo necesito confirmar la direccion sugerida. Responde 'si' para usarla o 'no' para mantener la que escribiste."
        ]
        return self._compose_messages(responses, extra_messages=[self._confirmation_buttons_message()])

    def _payment_prompt(self, payload: dict) -> str:
        customer_memory = payload.get("customer_memory") or {}
        preferred = customer_memory.get("preferred_payment_method")
        if preferred:
            return (
                f"Como deseas pagar? Puede ser Efectivo, Yape o Transferencia. "
                f"Tu metodo mas usado es {preferred}."
            )
        return "Como deseas pagar? Puede ser Efectivo, Yape o Transferencia."

    def _observations_prompt(self, payload: dict) -> str:
        customer_memory = payload.get("customer_memory") or {}
        preferred_observation = customer_memory.get("preferred_observation")
        if preferred_observation:
            return (
                "Perfecto. Quieres agregar alguna observacion? Si no, escribe 'no'. "
                f"Tu indicacion mas frecuente es: {preferred_observation}. "
                "Si quieres usarla otra vez, escribe 'misma observacion'."
            )
        return "Perfecto. Quieres agregar alguna observacion? Si no, escribe 'no'."

    def _get_customer_memory(self, phone: str, customer_name: str | None) -> dict | None:
        summary = self.order_repository.get_customer_operational_summary(phone)
        if summary.get("total_orders", 0) <= 0:
            return None
        summary["favorite_items"] = self._build_favorite_items(summary.get("recent_orders", []))
        summary["customer_name"] = customer_name
        return summary

    @staticmethod
    def _latest_customer_order(customer_memory: dict | None) -> dict | None:
        if not customer_memory:
            return None
        recent_orders = customer_memory.get("recent_orders") or []
        return recent_orders[0] if recent_orders else None

    def _should_offer_last_order(self, payload: dict) -> bool:
        latest_order = self._latest_customer_order(payload.get("customer_memory"))
        return bool(latest_order and latest_order.get("order_detail"))

    def _last_order_prompt(self, payload: dict) -> str:
        latest_order = self._latest_customer_order(payload.get("customer_memory"))
        if not latest_order:
            return "Cuando quieras, dime que te gustaria pedir y yo lo registro."
        return (
            f"Si quieres, puedo repetir tu ultimo pedido: {latest_order['order_detail']}. "
            "Tambien puedes elegir otra opcion."
        )

    def _build_favorite_items(self, recent_orders: list[dict]) -> list[str]:
        counts: dict[str, int] = {}
        for order in recent_orders:
            parsed = self.order_parser_service.parse_order(order.get("order_detail"))
            for item in parsed.get("items", []):
                counts[item["name"]] = counts.get(item["name"], 0) + int(item.get("quantity", 0))
        ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
        return [name for name, _ in ranked[:3]]

    @staticmethod
    def _last_order_buttons_message() -> dict:
        return {
            "type": "reply_buttons",
            "body": "Elige una opcion para avanzar con tu pedido.",
            "buttons": [
                {"id": "aira:repeat:last-order", "title": "Repetir ultimo"},
                {"id": "aira:show:menu", "title": "Ver menu"},
            ],
            "fallback_text": "Responde 'repite el ultimo pedido' o 'menu'.",
        }

    def _menu_list_message(self) -> dict:
        categories = self.menu_service.list_menu()
        sections = []
        total_rows = 0
        for category in categories:
            rows = []
            for item in category["items"]:
                if not item["is_active"]:
                    continue
                if total_rows >= 10:
                    break
                rows.append(
                    {
                        "id": f"aira:menu-item:{item['name']}",
                        "title": item["name"],
                        "description": f"S/ {item['price']:.2f}",
                    }
                )
                total_rows += 1
            if rows:
                sections.append({"title": category["name"], "rows": rows})
            if total_rows >= 10:
                break

        if not sections:
            return self._text_message(self._menu_prompt())

        return {
            "type": "list",
            "header": "Menu",
            "body": "Elige un producto para empezar o escribe tu pedido completo si prefieres.",
            "button_text": "Ver opciones",
            "sections": sections,
            "fallback_text": self._menu_prompt(),
        }

    @staticmethod
    def _delivery_buttons_message(body: str) -> dict:
        return {
            "type": "reply_buttons",
            "body": body,
            "buttons": [
                {"id": "aira:delivery:delivery", "title": "Delivery"},
                {"id": "aira:delivery:pickup", "title": "Recojo"},
            ],
            "fallback_text": f"{body} Responde: Delivery o Recojo.",
        }

    @staticmethod
    def _payment_buttons_message(body: str) -> dict:
        return {
            "type": "reply_buttons",
            "body": body,
            "buttons": [
                {"id": "aira:payment:cash", "title": "Efectivo"},
                {"id": "aira:payment:yape", "title": "Yape"},
                {"id": "aira:payment:transfer", "title": "Transferencia"},
            ],
            "fallback_text": f"{body} Responde: Efectivo, Yape o Transferencia.",
        }

    @staticmethod
    def _confirmation_buttons_message() -> dict:
        return {
            "type": "reply_buttons",
            "body": "Confirma si el pedido esta correcto.",
            "buttons": [
                {"id": "aira:confirm:yes", "title": "Confirmar"},
                {"id": "aira:confirm:no", "title": "Corregir"},
            ],
            "fallback_text": "Responde 'si' para confirmar o 'no' para corregir.",
        }

    @staticmethod
    def _text_message(body: str) -> dict:
        return {"type": "text", "body": body, "fallback_text": body}

    def _compose_messages(self, texts: list[str], extra_messages: list[dict] | None = None) -> list[dict]:
        messages = [self._text_message(text) for text in texts]
        if extra_messages:
            messages.extend(extra_messages)
        return messages

    @staticmethod
    def _preview_message(message: dict) -> str:
        message_type = message.get("type", "text")
        if message_type == "text":
            return message.get("body", "")
        if message_type == "reply_buttons":
            buttons = ", ".join(button["title"] for button in message.get("buttons", []))
            return f"{message.get('body', '')} [Opciones: {buttons}]"
        if message_type == "list":
            options = []
            for section in message.get("sections", []):
                for row in section.get("rows", []):
                    options.append(row["title"])
            return f"{message.get('body', '')} [Lista: {', '.join(options)}]"
        return message.get("fallback_text", "")

    def _apply_location_to_payload(self, payload: dict, location_data: dict) -> None:
        latitude = location_data.get("latitude")
        longitude = location_data.get("longitude")
        if latitude is None or longitude is None:
            return

        payload["location"] = {
            "latitude": latitude,
            "longitude": longitude,
            "label": location_data.get("address")
            or location_data.get("name")
            or "Ubicacion compartida por WhatsApp",
        }
        payload["address"] = payload.get("address") or payload["location"]["label"]
        payload["delivery_type"] = payload.get("delivery_type") or "Delivery"

    @staticmethod
    def _build_map_url(latitude: float | None, longitude: float | None) -> str | None:
        if latitude is None or longitude is None:
            return None
        return f"https://maps.google.com/?q={latitude},{longitude}"

    @staticmethod
    def _build_location_summary(location_label: str | None, map_url: str | None) -> str:
        lines = []
        if location_label:
            lines.append(f"Ubicacion compartida: {location_label}")
        if map_url:
            lines.append(f"Mapa: {map_url}")
        if not lines:
            return ""
        return "\n".join(lines) + "\n"

    @staticmethod
    def _preview_location(location_data: dict | None) -> str:
        if not location_data:
            return ""
        label = location_data.get("address") or location_data.get("name") or "Ubicacion compartida"
        latitude = location_data.get("latitude")
        longitude = location_data.get("longitude")
        if latitude is None or longitude is None:
            return label
        return f"{label} ({latitude}, {longitude})"

    @staticmethod
    def _build_zone_summary(delivery_zone: str | None) -> str:
        if not delivery_zone:
            return ""
        return f"Zona delivery: {delivery_zone}\n"

    @staticmethod
    def _normalize(value: str) -> str:
        ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
        cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", ascii_value.lower())
        return " ".join(cleaned.strip().split())

    @staticmethod
    def _clean_detail_from_parsed_order(parsed_order: dict) -> str | None:
        items = parsed_order.get("items", []) if parsed_order else []
        if not items:
            return None
        parts = [f"{item['quantity']} {item['name']}" for item in items]
        detail = ", ".join(parts)
        modifiers = parsed_order.get("modifiers", []) if parsed_order else []
        if modifiers:
            detail = f"{detail} ({'; '.join(modifiers)})"
        return detail

    @staticmethod
    def _build_items_summary(items: list[dict], modifiers: list[str] | None = None) -> str:
        if not items and not modifiers:
            return ""
        lines = ["Items detectados:"]
        for item in items:
            lines.append(f"- {item['quantity']} x {item['name']} (S/ {item['subtotal']:.2f})")
        if modifiers:
            lines.append("Indicaciones detectadas:")
            for modifier in modifiers:
                lines.append(f"- {modifier}")
        return "\n".join(lines) + "\n"

    def _calculate_delivery_fee(self, payload: dict) -> float:
        if payload.get("delivery_type") != "Delivery":
            return 0.0
        business = self.config_service.get_business()
        return float(business.get("default_delivery_fee", 0.0))

    def _resolve_delivery_zone_and_fee(self, payload: dict) -> tuple[str | None, float]:
        if payload.get("delivery_type") != "Delivery":
            return None, 0.0
        business = self.config_service.get_business()
        location_text = payload.get("address") or (payload.get("location") or {}).get("label") or ""
        normalized_location = self._normalize(location_text)
        for zone_name, fee in business.get("delivery_zone_fees", {}).items():
            if self._normalize(zone_name) in normalized_location:
                return zone_name, float(fee)
        return None, self._calculate_delivery_fee(payload)

    @staticmethod
    def _is_reset_request(message_text: str) -> bool:
        normalized = " ".join(message_text.lower().strip().split())
        return normalized in {"nuevo pedido", "reiniciar", "empezar", "start"}

    @staticmethod
    def _analysis_advances_order(analysis: dict) -> bool:
        return any(
            [
                analysis.get("customer_name"),
                analysis.get("order_detail"),
                analysis.get("delivery_type"),
                analysis.get("address"),
                analysis.get("reference_text"),
                analysis.get("reference_declined"),
                analysis.get("payment_method"),
                analysis.get("cash_change_for") is not None,
                analysis.get("cash_change_declined"),
                analysis.get("observation"),
                analysis.get("observation_declined"),
                analysis.get("confirmation"),
            ]
        )

    def _should_pause_flow(self, analysis: dict, interaction: dict) -> bool:
        if self._analysis_advances_order(analysis):
            return False

        if interaction.get("matched") and interaction.get("allow_business_flow"):
            return True

        return any(
            [
                analysis.get("asks_menu"),
                analysis.get("asks_hours"),
                analysis.get("asks_delivery_info"),
                analysis.get("asks_location_help"),
                analysis.get("asks_store_location"),
                analysis.get("asks_payment_info"),
                analysis.get("asks_photos"),
            ]
        )

    def _build_pause_flow_responses(
        self,
        stage: str,
        payload: dict,
        faq_responses: list[str],
        interaction: dict,
    ) -> list[dict]:
        texts: list[str] = []
        interaction_response = interaction.get("response")
        if interaction_response:
            texts.append(interaction_response)

        for response in faq_responses:
            if response and response not in texts:
                texts.append(response)

        reminder = self._build_stage_reminder(stage, payload)
        if reminder:
            texts.append(reminder)

        return self._compose_messages(texts)

    def _build_stage_reminder(self, stage: str, payload: dict) -> str | None:
        reminders = {
            "collect_name": "Cuando quieras seguimos. Antes de confirmar, me compartes tu nombre?",
            "collect_order_detail": "Cuando quieras seguimos. Dime que te gustaria pedir y yo lo registro.",
            "collect_delivery_type": "Cuando quieras seguimos. Solo necesito saber si sera delivery o recojo.",
            "collect_address": "Cuando quieras seguimos. Necesito la direccion de entrega o tu ubicacion compartida.",
            "collect_reference": "Cuando quieras seguimos. Si tienes una referencia, me la compartes; si no, escribe 'no'.",
            "collect_payment_method": "Cuando quieras seguimos. Solo necesito el metodo de pago.",
            "collect_cash_change": "Cuando quieras seguimos. Si necesitas vuelto, dime con cuanto pagaras. Si no, escribe 'no'.",
            "collect_observations": "Cuando quieras seguimos. Si no tienes observaciones, escribe 'no'.",
            "await_confirmation": "Cuando quieras seguimos con la confirmacion del pedido.",
        }

        reminder = reminders.get(stage)
        if stage == "collect_name" and not (
            payload.get("order_detail")
            or payload.get("delivery_type")
            or payload.get("address")
            or payload.get("payment_method")
        ):
            return "Cuando quieras hacer un pedido, me compartes tu nombre y te ayudo al instante."
        return reminder
