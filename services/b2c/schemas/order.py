import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from schemas.address import AddressResponse
from schemas.payment_method import PaymentMethodResponse


OrderStatus = Literal[
	"CREATED",
	"PAID",
	"ASSEMBLING",
	"DELIVERING",
	"DELIVERED",
	"CANCELLED",
	"CANCEL_PENDING",
]


class OrderItemSnapshot(BaseModel):
	sku_id: uuid.UUID
	quantity: int = Field(ge=1)
	unit_price: int = Field(ge=0)


class OrderCreateRequest(BaseModel):
	address_id: uuid.UUID
	payment_method_id: uuid.UUID
	comment: str | None = Field(default=None, max_length=1000)
	items_snapshot: list[OrderItemSnapshot] | None = None


class OrderCancelRequest(BaseModel):
	reason: str | None = Field(default=None, max_length=500)


class OrderDeliveredEventRequest(BaseModel):
	order_id: uuid.UUID


class OrderItem(BaseModel):
	sku_id: uuid.UUID
	product_id: uuid.UUID
	name: str
	sku_code: str | None = None
	quantity: int = Field(ge=1)
	unit_price: int = Field(ge=0)
	line_total: int = Field(ge=0)
	image_url: str | None = None


class OrderResponse(BaseModel):
	id: uuid.UUID
	number: str | None = None
	buyer_id: uuid.UUID
	status: OrderStatus
	status_history: list[dict] | None = None

	items: list[OrderItem]
	subtotal: int = Field(ge=0)
	delivery_cost: int = Field(default=0, ge=0)
	total: int = Field(ge=0)

	address: AddressResponse
	payment_method: PaymentMethodResponse | None = None
	comment: str | None = None
	cancel_reason: str | None = None

	created_at: datetime
	paid_at: datetime | None = None
	delivered_at: datetime | None = None


class PaginatedOrders(BaseModel):
	items: list[OrderResponse]
	total_count: int
	limit: int
	offset: int
	model_config = ConfigDict(from_attributes=True)
