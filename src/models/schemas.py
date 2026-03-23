from pydantic import BaseModel, Field


class SimulatedMessageRequest(BaseModel):
    phone: str
    message: str
    latitude: float | None = None
    longitude: float | None = None
    location_address: str | None = None
    location_name: str | None = None


class SimulatedMessageResponse(BaseModel):
    responses: list[str]


class DeliveryZoneFeeInput(BaseModel):
    zone: str
    fee: float


class CrossSellRuleInput(BaseModel):
    trigger_category: str
    suggested_item: str
    message: str | None = None


class BusinessUpdateRequest(BaseModel):
    business_name: str
    assistant_name: str
    admin_access_code: str
    greeting: str
    business_hours: str
    business_address: str
    default_delivery_fee: float
    pickup_eta_minutes: int = 20
    delivery_eta_minutes: int = 45
    delivery_zones: list[str]
    payment_methods: list[str]
    yape_details: str | None = None
    transfer_details: str | None = None
    delivery_zone_fees: list[DeliveryZoneFeeInput] = Field(default_factory=list)
    cross_sell_rules: list[CrossSellRuleInput] = Field(default_factory=list)


class BusinessResponse(BaseModel):
    business_name: str
    assistant_name: str
    admin_access_code: str
    greeting: str
    business_hours: str
    business_address: str
    default_delivery_fee: float
    pickup_eta_minutes: int = 20
    delivery_eta_minutes: int = 45
    delivery_zones: list[str]
    payment_methods: list[str]
    yape_details: str | None = None
    transfer_details: str | None = None
    delivery_zone_fees: list[DeliveryZoneFeeInput]
    cross_sell_rules: list[CrossSellRuleInput] = Field(default_factory=list)


class MenuItemInput(BaseModel):
    name: str
    price: float
    is_active: bool = True


class MenuCategoryInput(BaseModel):
    name: str
    items: list[MenuItemInput]


class MenuUpdateRequest(BaseModel):
    categories: list[MenuCategoryInput]


class MenuItemRecord(BaseModel):
    id: int
    name: str
    price: float
    is_active: bool


class MenuCategoryRecord(BaseModel):
    id: int
    name: str
    items: list[MenuItemRecord]


class MenuResponse(BaseModel):
    categories: list[MenuCategoryRecord]


class OrderRecord(BaseModel):
    order_number: str
    customer_phone: str
    customer_name: str
    customer_total_orders: int = 0
    customer_note: str | None = None
    order_type: str
    order_detail: str
    address: str | None = None
    reference_text: str | None = None
    delivery_zone: str | None = None
    location_label: str | None = None
    location_latitude: float | None = None
    location_longitude: float | None = None
    map_url: str | None = None
    observations: str | None = None
    internal_note: str | None = None
    payment_method: str | None = None
    cash_change_for: float | None = None
    subtotal: float | None = None
    delivery_fee: float | None = None
    total: float | None = None
    status: str
    created_at: str


class OrderListResponse(BaseModel):
    orders: list[OrderRecord]


class OrderDetailResponse(BaseModel):
    order: OrderRecord


class OrderStatusUpdateRequest(BaseModel):
    status: str


class OrderNoteUpdateRequest(BaseModel):
    note: str


class CustomerNoteUpdateRequest(BaseModel):
    note: str


class OrderSummaryResponse(BaseModel):
    total_orders: int
    total_revenue: float
    by_status: dict[str, int]


class MessageLogRecord(BaseModel):
    direction: str
    phone: str
    message_text: str
    created_at: str


class SessionMemoryRecord(BaseModel):
    stage: str | None = None
    payload: dict = Field(default_factory=dict)


class OrderMemoryResponse(BaseModel):
    order_number: str
    customer_phone: str
    customer_name: str
    active_stage: str | None = None
    has_active_session: bool
    session: SessionMemoryRecord | None = None
    recent_messages: list[MessageLogRecord]


class OrderTimelineEventRecord(BaseModel):
    source: str
    label: str
    detail: str | None = None
    created_at: str


class OrderTimelineResponse(BaseModel):
    order_number: str
    customer_phone: str
    customer_name: str
    timeline: list[OrderTimelineEventRecord]


class CustomerRecentOrderRecord(BaseModel):
    order_number: str
    order_detail: str
    order_type: str
    payment_method: str | None = None
    total: float | None = None
    status: str
    created_at: str


class CustomerSummaryResponse(BaseModel):
    customer_phone: str
    customer_name: str
    total_orders: int
    last_order_at: str | None = None
    customer_note: str | None = None
    preferred_order_type: str | None = None
    preferred_payment_method: str | None = None
    preferred_observation: str | None = None
    last_address: str | None = None
    last_reference_text: str | None = None
    favorite_items: list[str] = Field(default_factory=list)
    recent_orders: list[CustomerRecentOrderRecord]
