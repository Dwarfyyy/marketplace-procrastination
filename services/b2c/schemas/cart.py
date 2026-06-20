import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from schemas.catalog import ImageRef


class CartItemAddRequest(BaseModel):
	sku_id: uuid.UUID
	quantity: int = Field(ge=1)


class CartItemQuantityUpdate(BaseModel):
	quantity: int = Field(ge=1)


class CartItem(BaseModel):
	sku_id: uuid.UUID
	product_id: uuid.UUID
	name: str
	sku_code: str
	quantity: int = Field(ge=1)
	unit_price: int
	unit_price_at_add: Optional[int] = None
	line_total: int
	available_quantity: int = Field(ge=0)
	is_available: bool
	unavailable_reason: Optional[
		Literal["PRODUCT_DELETED", "PRODUCT_BLOCKED", "ON_MODERATION", "OUT_OF_STOCK"]
	] = None
	image: Optional[ImageRef] = None


class CartResponse(BaseModel):
	id: Optional[uuid.UUID] = None
	items: list[CartItem]
	items_count: int
	subtotal: int
	is_valid: bool
	updated_at: Optional[datetime] = None


class CartValidationIssue(BaseModel):
	sku_id: uuid.UUID
	type: Literal[
		"PRICE_CHANGED",
		"OUT_OF_STOCK",
		"QUANTITY_REDUCED",
		"PRODUCT_BLOCKED",
		"PRODUCT_DELETED",
	]
	message: str
	old_value: Optional[str | int] = None
	new_value: Optional[str | int] = None


class CartValidationResponse(BaseModel):
	is_valid: bool
	cart: CartResponse
	issues: list[CartValidationIssue]
