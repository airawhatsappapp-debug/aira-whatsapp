from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from src.db.database import bootstrap_database
from src.models.schemas import (
    MenuResponse,
    MenuUpdateRequest,
    CustomerNoteUpdateRequest,
    OrderDetailResponse,
    OrderListResponse,
    OrderMemoryResponse,
    OrderNoteUpdateRequest,
    OrderSummaryResponse,
    OrderTimelineEventRecord,
    OrderTimelineResponse,
    OrderStatusUpdateRequest,
    BusinessResponse,
    BusinessUpdateRequest,
    CustomerRecentOrderRecord,
    CustomerSummaryResponse,
    MessageLogRecord,
    SessionMemoryRecord,
    SimulatedMessageRequest,
    SimulatedMessageResponse,
)
from src.repositories.customer_repository import CustomerRepository
from src.repositories.message_repository import MessageRepository
from src.repositories.order_repository import OrderRepository
from src.repositories.session_repository import SessionRepository
from src.services.container import ServiceContainer

health_router = APIRouter(tags=["health"])
webhook_router = APIRouter(prefix="/webhooks/whatsapp", tags=["webhook"])
order_router = APIRouter(prefix="/orders", tags=["orders"])
menu_router = APIRouter(prefix="/menu", tags=["menu"])
business_router = APIRouter(prefix="/business", tags=["business"])
admin_router = APIRouter(tags=["admin"])

bootstrap_database()
container = ServiceContainer()


@health_router.get("/health")
def healthcheck() -> dict:
    return {"status": "ok"}


def require_admin_code(x_admin_code: str | None = Header(default=None)) -> str:
    expected_code = container.config_service.get_business().get("admin_access_code")
    if not expected_code:
        return ""
    if x_admin_code != expected_code:
        raise HTTPException(status_code=401, detail="Admin code required")
    return x_admin_code


def validate_menu_payload(categories: list) -> None:
    if not categories:
        raise HTTPException(status_code=400, detail="At least one category is required")

    seen_categories: set[str] = set()

    for category in categories:
        category_name = category.name.strip()
        if not category_name:
            raise HTTPException(status_code=400, detail="Category name cannot be empty")
        normalized_category = category_name.lower()
        if normalized_category in seen_categories:
            raise HTTPException(status_code=400, detail=f"Duplicate category: {category_name}")
        seen_categories.add(normalized_category)

        if not category.items:
            raise HTTPException(status_code=400, detail=f"Category '{category_name}' must have at least one item")

        seen_items: set[str] = set()
        for item in category.items:
            item_name = item.name.strip()
            if not item_name:
                raise HTTPException(status_code=400, detail=f"Category '{category_name}' has an item without name")
            if item.price < 0:
                raise HTTPException(status_code=400, detail=f"Item '{item_name}' cannot have a negative price")
            normalized_item = item_name.lower()
            if normalized_item in seen_items:
                raise HTTPException(
                    status_code=400,
                    detail=f"Category '{category_name}' has duplicate item '{item_name}'",
                )
            seen_items.add(normalized_item)


@admin_router.get("/admin", response_class=HTMLResponse)
def admin_panel() -> HTMLResponse:
    admin_path = Path(__file__).resolve().parent.parent / "static" / "admin.html"
    return HTMLResponse(content=admin_path.read_text(encoding="utf-8"))


@admin_router.get("/admin/check")
def admin_check(_: str = Header(default=None, alias="x-admin-code")) -> dict:
    require_admin_code(_)
    return {"ok": True}


@webhook_router.get("")
def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> PlainTextResponse:
    if not container.settings.verify_token == hub_verify_token or hub_mode != "subscribe":
        raise HTTPException(status_code=403, detail="Webhook verification failed")
    return PlainTextResponse(content=hub_challenge)


@webhook_router.post("")
async def receive_webhook(request: Request) -> dict:
    payload = await request.json()
    await container.webhook_service.handle_payload(payload)
    return {"received": True}


@webhook_router.post("/simulate", response_model=SimulatedMessageResponse)
async def simulate_message(data: SimulatedMessageRequest) -> SimulatedMessageResponse:
    responses = await container.conversation_service.process_incoming_message(
        data.phone,
        data.message,
        location_data=(
            {
                "latitude": data.latitude,
                "longitude": data.longitude,
                "address": data.location_address,
                "name": data.location_name,
            }
            if data.latitude is not None and data.longitude is not None
            else None
        ),
    )
    return SimulatedMessageResponse(
        responses=[container.conversation_service._preview_message(response) for response in responses]
    )


@order_router.get("", response_model=OrderListResponse)
def list_orders(limit: int = 20, _: str = Header(default=None, alias="x-admin-code")) -> OrderListResponse:
    require_admin_code(_)
    repository = OrderRepository()
    orders = repository.list_orders(limit=limit)
    return OrderListResponse(orders=orders)


@order_router.get("/summary", response_model=OrderSummaryResponse)
def get_order_summary(_: str = Header(default=None, alias="x-admin-code")) -> OrderSummaryResponse:
    require_admin_code(_)
    repository = OrderRepository()
    return OrderSummaryResponse(**repository.get_order_summary())


@order_router.get("/{order_number}", response_model=OrderDetailResponse)
def get_order(order_number: str, _: str = Header(default=None, alias="x-admin-code")) -> OrderDetailResponse:
    require_admin_code(_)
    repository = OrderRepository()
    order = repository.get_order_by_number(order_number)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderDetailResponse(order=order)


@order_router.get("/{order_number}/memory", response_model=OrderMemoryResponse)
def get_order_memory(
    order_number: str,
    _: str = Header(default=None, alias="x-admin-code"),
) -> OrderMemoryResponse:
    require_admin_code(_)
    order_repository = OrderRepository()
    order = order_repository.get_order_by_number(order_number)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    session_repository = SessionRepository()
    message_repository = MessageRepository()

    session = session_repository.get_session(order.customer_phone)
    recent_messages = message_repository.list_recent_messages(order.customer_phone, limit=12)

    return OrderMemoryResponse(
        order_number=order.order_number,
        customer_phone=order.customer_phone,
        customer_name=order.customer_name,
        active_stage=session["stage"] if session else None,
        has_active_session=session is not None,
        session=SessionMemoryRecord(
            stage=session["stage"],
            payload=session["payload"],
        ) if session else None,
        recent_messages=[MessageLogRecord(**message) for message in recent_messages],
    )


@order_router.get("/{order_number}/timeline", response_model=OrderTimelineResponse)
def get_order_timeline(
    order_number: str,
    _: str = Header(default=None, alias="x-admin-code"),
) -> OrderTimelineResponse:
    require_admin_code(_)
    order_repository = OrderRepository()
    order = order_repository.get_order_by_number(order_number)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    message_repository = MessageRepository()
    events = order_repository.list_order_events(order_number)
    messages = message_repository.list_recent_messages(order.customer_phone, limit=20)

    timeline = [
        OrderTimelineEventRecord(
            source="evento",
            label=event["title"],
            detail=event.get("detail"),
            created_at=event["created_at"],
        )
        for event in events
    ] + [
        OrderTimelineEventRecord(
            source="cliente" if message["direction"] == "inbound" else "aira",
            label="Mensaje",
            detail=message["message_text"],
            created_at=message["created_at"],
        )
        for message in messages
    ]

    timeline.sort(key=lambda item: item.created_at)

    return OrderTimelineResponse(
        order_number=order.order_number,
        customer_phone=order.customer_phone,
        customer_name=order.customer_name,
        timeline=timeline,
    )


@order_router.get("/{order_number}/customer-summary", response_model=CustomerSummaryResponse)
def get_customer_summary_for_order(
    order_number: str,
    _: str = Header(default=None, alias="x-admin-code"),
) -> CustomerSummaryResponse:
    require_admin_code(_)
    order_repository = OrderRepository()
    order = order_repository.get_order_by_number(order_number)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    summary = order_repository.get_customer_operational_summary(order.customer_phone)
    return CustomerSummaryResponse(
        customer_phone=order.customer_phone,
        customer_name=order.customer_name,
        total_orders=summary["total_orders"],
        last_order_at=summary["last_order_at"],
        customer_note=summary.get("customer_note"),
        preferred_order_type=summary["preferred_order_type"],
        preferred_payment_method=summary["preferred_payment_method"],
        preferred_observation=summary["preferred_observation"],
        last_address=summary["last_address"],
        last_reference_text=summary["last_reference_text"],
        favorite_items=summary.get("favorite_items", []),
        recent_orders=[
            CustomerRecentOrderRecord(**row)
            for row in summary["recent_orders"]
        ],
    )


@order_router.put("/{order_number}/customer-note", response_model=CustomerSummaryResponse)
def update_customer_note_for_order(
    order_number: str,
    data: CustomerNoteUpdateRequest,
    _: str = Header(default=None, alias="x-admin-code"),
) -> CustomerSummaryResponse:
    require_admin_code(_)
    order_repository = OrderRepository()
    customer_repository = CustomerRepository()
    order = order_repository.get_order_by_number(order_number)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    customer = customer_repository.update_customer_note(order.customer_phone, data.note)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    order_repository.record_order_event(
        order_number,
        "customer_note",
        "Nota del cliente actualizada",
        customer.get("internal_note") or "Sin nota",
    )

    summary = order_repository.get_customer_operational_summary(order.customer_phone)
    return CustomerSummaryResponse(
        customer_phone=order.customer_phone,
        customer_name=order.customer_name,
        total_orders=summary["total_orders"],
        last_order_at=summary["last_order_at"],
        customer_note=summary.get("customer_note"),
        preferred_order_type=summary["preferred_order_type"],
        preferred_payment_method=summary["preferred_payment_method"],
        preferred_observation=summary["preferred_observation"],
        last_address=summary["last_address"],
        last_reference_text=summary["last_reference_text"],
        favorite_items=summary.get("favorite_items", []),
        recent_orders=[
            CustomerRecentOrderRecord(**row)
            for row in summary["recent_orders"]
        ],
    )


@order_router.put("/{order_number}/status", response_model=OrderDetailResponse)
async def update_order_status(
    order_number: str,
    data: OrderStatusUpdateRequest,
    _: str = Header(default=None, alias="x-admin-code"),
) -> OrderDetailResponse:
    require_admin_code(_)
    allowed_statuses = {"nuevo", "preparando", "en camino", "entregado", "cancelado"}
    status = data.status.strip().lower()
    if status not in allowed_statuses:
        raise HTTPException(status_code=400, detail="Invalid status")
    repository = OrderRepository()
    order = repository.update_order_status(order_number, status)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if status in {"preparando", "en camino", "entregado", "cancelado"}:
        await container.notification_service.notify_customer_status_update(order.model_dump())
    return OrderDetailResponse(order=order)


@order_router.put("/{order_number}/note", response_model=OrderDetailResponse)
def update_order_note(
    order_number: str,
    data: OrderNoteUpdateRequest,
    _: str = Header(default=None, alias="x-admin-code"),
) -> OrderDetailResponse:
    require_admin_code(_)
    repository = OrderRepository()
    order = repository.update_order_note(order_number, data.note)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderDetailResponse(order=order)


@menu_router.get("", response_model=MenuResponse)
def get_menu(_: str = Header(default=None, alias="x-admin-code")) -> MenuResponse:
    require_admin_code(_)
    categories = container.menu_service.list_menu()
    return MenuResponse(categories=categories)


@menu_router.put("", response_model=MenuResponse)
def update_menu(data: MenuUpdateRequest, _: str = Header(default=None, alias="x-admin-code")) -> MenuResponse:
    require_admin_code(_)
    validate_menu_payload(data.categories)
    categories = container.menu_service.update_menu(
        [category.model_dump() for category in data.categories]
    )
    return MenuResponse(categories=categories)


@business_router.get("", response_model=BusinessResponse)
def get_business(_: str = Header(default=None, alias="x-admin-code")) -> BusinessResponse:
    require_admin_code(_)
    business = container.config_service.get_business()
    zone_fees = [
        {"zone": zone, "fee": fee}
        for zone, fee in business.get("delivery_zone_fees", {}).items()
    ]
    cross_sell_rules = business.get("cross_sell_rules", [])
    payment_details = business.get("payment_details", {})
    return BusinessResponse(
        business_name=business["business_name"],
        assistant_name=business["assistant_name"],
        assistant_avatar_url=business.get("assistant_avatar_url"),
        admin_access_code=business.get("admin_access_code", ""),
        whatsapp_business_number=business.get("whatsapp_business_number"),
        whatsapp_channel_status=business.get("whatsapp_channel_status", "no_configurado"),
        whatsapp_channel_note=business.get("whatsapp_channel_note"),
        subscription_plan=business.get("subscription_plan", "aira_start"),
        subscription_status=business.get("subscription_status", "beta_activa"),
        business_type=business.get("business_type", "restaurante"),
        primary_goal=business.get("primary_goal", "tomar_pedidos"),
        tone_style=business.get("tone_style", "cordial"),
        emoji_level=business.get("emoji_level", "moderado"),
        enabled_capabilities=business.get("enabled_capabilities", []),
        greeting=business["greeting"],
        business_hours=business["business_hours"],
        business_address=business["business_address"],
        default_delivery_fee=float(business.get("default_delivery_fee", 0.0)),
        pickup_eta_minutes=int(business.get("pickup_eta_minutes", 20)),
        delivery_eta_minutes=int(business.get("delivery_eta_minutes", 45)),
        delivery_zones=business.get("delivery_zones", []),
        payment_methods=business.get("payment_methods", []),
        yape_details=payment_details.get("yape"),
        transfer_details=payment_details.get("transferencia"),
        delivery_zone_fees=zone_fees,
        cross_sell_rules=cross_sell_rules,
    )


@business_router.put("", response_model=BusinessResponse)
def update_business(data: BusinessUpdateRequest, _: str = Header(default=None, alias="x-admin-code")) -> BusinessResponse:
    require_admin_code(_)
    delivery_zones = [zone.strip() for zone in data.delivery_zones if zone.strip()]
    payment_methods = [method.strip() for method in data.payment_methods if method.strip()]
    delivery_zone_fees = {
        item.zone.strip(): float(item.fee)
        for item in data.delivery_zone_fees
        if item.zone.strip()
    }
    cross_sell_rules = [
        {
            "trigger_category": rule.trigger_category.strip(),
            "suggested_item": rule.suggested_item.strip(),
            "message": (rule.message or "").strip() or None,
        }
        for rule in data.cross_sell_rules
        if rule.trigger_category.strip() and rule.suggested_item.strip()
    ]
    if not payment_methods:
        raise HTTPException(status_code=400, detail="At least one payment method is required")
    admin_access_code = data.admin_access_code.strip()
    if len(admin_access_code) < 5:
        raise HTTPException(status_code=400, detail="Admin access code must have at least 5 characters")
    if len(admin_access_code) > 9:
        raise HTTPException(status_code=400, detail="Admin access code must have at most 9 characters")
    if data.pickup_eta_minutes < 0 or data.delivery_eta_minutes < 0:
        raise HTTPException(status_code=400, detail="ETA values cannot be negative")
    whatsapp_status = (data.whatsapp_channel_status or "no_configurado").strip().lower()
    allowed_whatsapp_statuses = {"no_configurado", "pendiente", "conectado"}
    if whatsapp_status not in allowed_whatsapp_statuses:
        raise HTTPException(status_code=400, detail="Invalid WhatsApp channel status")
    subscription_plan = (data.subscription_plan or "aira_start").strip().lower()
    allowed_subscription_plans = {"aira_start", "aira_pro", "aira_business"}
    if subscription_plan not in allowed_subscription_plans:
        raise HTTPException(status_code=400, detail="Invalid subscription plan")
    subscription_status = (data.subscription_status or "beta_activa").strip().lower()
    allowed_subscription_statuses = {"beta_activa", "activa", "pendiente", "suspendida"}
    if subscription_status not in allowed_subscription_statuses:
        raise HTTPException(status_code=400, detail="Invalid subscription status")

    business = container.config_service.update_business(
        {
            "business_name": data.business_name.strip(),
            "assistant_name": data.assistant_name.strip(),
            "assistant_avatar_url": (data.assistant_avatar_url or "").strip(),
            "admin_access_code": admin_access_code,
            "whatsapp_business_number": (data.whatsapp_business_number or "").strip(),
            "whatsapp_channel_status": whatsapp_status,
            "whatsapp_channel_note": (data.whatsapp_channel_note or "").strip(),
            "subscription_plan": subscription_plan,
            "subscription_status": subscription_status,
            "business_type": data.business_type.strip() or "restaurante",
            "primary_goal": data.primary_goal.strip() or "tomar_pedidos",
            "tone_style": data.tone_style.strip() or "cordial",
            "emoji_level": data.emoji_level.strip() or "moderado",
            "enabled_capabilities": [item.strip() for item in data.enabled_capabilities if item.strip()],
            "greeting": data.greeting.strip(),
            "business_hours": data.business_hours.strip(),
            "business_address": data.business_address.strip(),
            "default_delivery_fee": float(data.default_delivery_fee),
            "pickup_eta_minutes": int(data.pickup_eta_minutes),
            "delivery_eta_minutes": int(data.delivery_eta_minutes),
            "delivery_zones": delivery_zones,
            "payment_methods": payment_methods,
            "payment_details": {
                "yape": (data.yape_details or "").strip(),
                "transferencia": (data.transfer_details or "").strip(),
            },
            "delivery_zone_fees": delivery_zone_fees,
            "cross_sell_rules": cross_sell_rules,
        }
    )
    zone_fees = [
        {"zone": zone, "fee": fee}
        for zone, fee in business.get("delivery_zone_fees", {}).items()
    ]
    cross_sell_rules = business.get("cross_sell_rules", [])
    payment_details = business.get("payment_details", {})
    return BusinessResponse(
        business_name=business["business_name"],
        assistant_name=business["assistant_name"],
        assistant_avatar_url=business.get("assistant_avatar_url"),
        admin_access_code=business.get("admin_access_code", ""),
        whatsapp_business_number=business.get("whatsapp_business_number"),
        whatsapp_channel_status=business.get("whatsapp_channel_status", "no_configurado"),
        whatsapp_channel_note=business.get("whatsapp_channel_note"),
        subscription_plan=business.get("subscription_plan", "aira_start"),
        subscription_status=business.get("subscription_status", "beta_activa"),
        business_type=business.get("business_type", "restaurante"),
        primary_goal=business.get("primary_goal", "tomar_pedidos"),
        tone_style=business.get("tone_style", "cordial"),
        emoji_level=business.get("emoji_level", "moderado"),
        enabled_capabilities=business.get("enabled_capabilities", []),
        greeting=business["greeting"],
        business_hours=business["business_hours"],
        business_address=business["business_address"],
        default_delivery_fee=float(business.get("default_delivery_fee", 0.0)),
        pickup_eta_minutes=int(business.get("pickup_eta_minutes", 20)),
        delivery_eta_minutes=int(business.get("delivery_eta_minutes", 45)),
        delivery_zones=business.get("delivery_zones", []),
        payment_methods=business.get("payment_methods", []),
        yape_details=payment_details.get("yape"),
        transfer_details=payment_details.get("transferencia"),
        delivery_zone_fees=zone_fees,
        cross_sell_rules=cross_sell_rules,
    )
