import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

import crud.cart as cart_crud
from database.models.cart.item import CartItem as CartItemDB
from database.models.catalog.base import Product, ProductStatusEnum
from database.models.catalog.variants import Image, Sku
from exceptions.cart import (
	CartItemNotFoundError,
	InsufficientStockError,
	SkuUnavailableError,
)
from exceptions.sku import SkuNotFoundError
from schemas.cart import (
	CartItem,
	CartResponse,
	CartValidationIssue,
	CartValidationResponse,
)
from schemas.catalog import ImageRef


def _sku_unavailable(product: Product, sku: Sku) -> Optional[str]:
	if product.deleted:
		return "PRODUCT_DELETED"
	if product.status == ProductStatusEnum.BLOCKED:
		return "PRODUCT_BLOCKED"
	if product.status == ProductStatusEnum.ON_MODERATION:
		return "ON_MODERATION"
	if sku.active_quantity <= 0:
		return "OUT_OF_STOCK"
	return None


def _build_cart_item(
	cart_item: CartItemDB, sku: Sku, product: Product, image: Optional[Image]
) -> CartItem:
	unavailable_reason = _sku_unavailable(product, sku)
	is_available = unavailable_reason is None
	unit_price = sku.price
	line_total = unit_price * cart_item.quantity if is_available else 0
	name = f"{product.title} — {sku.name}"
	image_ref = None
	if image is not None:
		image_ref = ImageRef(
			id=image.id,
			url=image.url,
			alt="",
			ordering=image.ordering,
			is_main=image.ordering == 0,
		)

	return CartItem(
		sku_id=sku.id,
		product_id=product.id,
		name=name,
		sku_code=str(sku.id),
		quantity=cart_item.quantity,
		unit_price=unit_price,
		unit_price_at_add=cart_item.unit_price_at_add,
		line_total=line_total,
		available_quantity=sku.active_quantity,
		is_available=is_available,
		unavailable_reason=unavailable_reason,
		image=image_ref,
	)


def _build_cart_response(
	enriched_items: list[tuple[CartItemDB, Sku, Product, Optional[Image]]],
	user_id: Optional[uuid.UUID],
	session_id: Optional[str],
) -> CartResponse:
	if not enriched_items:
		cart_id = user_id
		if cart_id is None and session_id:
			cart_id = uuid.UUID(session_id)
		return CartResponse(
			id=cart_id,
			items=[],
			items_count=0,
			subtotal=0,
			is_valid=True,
			updated_at=None,
		)

	items: list[CartItem] = []
	items_count = 0
	subtotal = 0
	is_valid = True
	updated_at: Optional[datetime] = None

	for cart_item, sku, product, image in enriched_items:
		item = _build_cart_item(cart_item, sku, product, image)
		items.append(item)
		items_count += cart_item.quantity
		if item.is_available:
			subtotal += item.line_total
			if cart_item.quantity > item.available_quantity:
				is_valid = False
		else:
			is_valid = False

		if updated_at is None or cart_item.updated_at > updated_at:
			updated_at = cart_item.updated_at

	cart_id = user_id
	if cart_id is None and session_id:
		cart_id = uuid.UUID(session_id)

	return CartResponse(
		id=cart_id,
		items=items,
		items_count=items_count,
		subtotal=subtotal,
		is_valid=is_valid,
		updated_at=updated_at,
	)


async def get_cart(
	db: AsyncSession, user_id: Optional[uuid.UUID], session_id: Optional[str]
) -> CartResponse:
	enriched_items = await cart_crud.get_cart_items_with_details(
		db, user_id, session_id
	)
	return _build_cart_response(enriched_items, user_id, session_id)


async def clear_cart(
	db: AsyncSession, user_id: Optional[uuid.UUID], session_id: Optional[str]
) -> None:
	await cart_crud.clear_cart(db, user_id, session_id)


def _ensure_sku_available_for_update(sku: Sku) -> None:
	product = sku.product
	unavailable = _sku_unavailable(product, sku)
	if unavailable is not None:
		raise SkuUnavailableError(unavailable)


async def add_cart_item(
	db: AsyncSession,
	user_id: Optional[uuid.UUID],
	session_id: Optional[str],
	sku_id: uuid.UUID,
	quantity: int,
) -> CartResponse:
	sku = await cart_crud.get_sku_by_id(db, sku_id)
	if not sku:
		raise SkuNotFoundError(f"SKU with id {sku_id} not found")

	_ensure_sku_available_for_update(sku)

	existing_item = await cart_crud.get_cart_item_by_sku(
		db, user_id, session_id, sku_id
	)
	new_quantity = quantity if not existing_item else existing_item.quantity + quantity

	if new_quantity > sku.active_quantity:
		raise InsufficientStockError(
			f"Недостаточно остатков: доступно {sku.active_quantity}"
		)

	if existing_item:
		await cart_crud.update_cart_item_quantity(db, existing_item, new_quantity)
	else:
		await cart_crud.create_cart_item(
			db, user_id, session_id, sku_id, quantity, sku.price
		)

	return await get_cart(db, user_id, session_id)


async def update_cart_item_quantity(
	db: AsyncSession,
	user_id: Optional[uuid.UUID],
	session_id: Optional[str],
	sku_id: uuid.UUID,
	quantity: int,
) -> CartResponse:
	cart_item = await cart_crud.get_cart_item_by_sku(db, user_id, session_id, sku_id)
	if not cart_item:
		raise CartItemNotFoundError(f"SKU {sku_id} not in cart")

	sku = await cart_crud.get_sku_by_id(db, sku_id)
	if not sku:
		raise SkuNotFoundError(f"SKU with id {sku_id} not found")

	_ensure_sku_available_for_update(sku)

	if quantity > sku.active_quantity:
		raise InsufficientStockError(
			f"Not enough stock: available {sku.active_quantity}"
		)

	await cart_crud.update_cart_item_quantity(db, cart_item, quantity)
	return await get_cart(db, user_id, session_id)


async def remove_cart_item(
	db: AsyncSession,
	user_id: Optional[uuid.UUID],
	session_id: Optional[str],
	sku_id: uuid.UUID,
) -> CartResponse:
	cart_item = await cart_crud.get_cart_item_by_sku(db, user_id, session_id, sku_id)
	if not cart_item:
		raise CartItemNotFoundError(f"SKU {sku_id} not in cart")

	await cart_crud.delete_cart_item(db, cart_item)
	return await get_cart(db, user_id, session_id)


async def merge_guest_cart(
	db: AsyncSession, user_id: uuid.UUID, session_id: str
) -> CartResponse:
	await cart_crud.merge_guest_cart_into_user(db, user_id, session_id)
	return await get_cart(db, user_id, None)


async def validate_cart(
	db: AsyncSession, user_id: Optional[uuid.UUID], session_id: Optional[str]
) -> CartValidationResponse:
	cart = await get_cart(db, user_id, session_id)
	enriched_items = await cart_crud.get_cart_items_with_details(
		db, user_id, session_id
	)
	issues: list[CartValidationIssue] = []

	for cart_item, sku, product, _ in enriched_items:
		unavailable = _sku_unavailable(product, sku)
		if unavailable == "PRODUCT_DELETED":
			issues.append(
				CartValidationIssue(
					sku_id=sku.id,
					type="PRODUCT_DELETED",
					message="Product deleted",
				)
			)
		elif unavailable == "PRODUCT_BLOCKED":
			issues.append(
				CartValidationIssue(
					sku_id=sku.id,
					type="PRODUCT_BLOCKED",
					message="Product blocked",
				)
			)
		elif unavailable == "OUT_OF_STOCK":
			issues.append(
				CartValidationIssue(
					sku_id=sku.id,
					type="OUT_OF_STOCK",
					message="Product out of stock",
				)
			)
		elif (
			cart_item.unit_price_at_add is not None
			and sku.price != cart_item.unit_price_at_add
		):
			issues.append(
				CartValidationIssue(
					sku_id=sku.id,
					type="PRICE_CHANGED",
					message="Price changed",
					old_value=cart_item.unit_price_at_add,
					new_value=sku.price,
				)
			)
		elif cart_item.quantity > sku.active_quantity:
			issues.append(
				CartValidationIssue(
					sku_id=sku.id,
					type="QUANTITY_REDUCED",
					message="Available less than in cart",
					old_value=cart_item.quantity,
					new_value=sku.active_quantity,
				)
			)

	return CartValidationResponse(
		is_valid=len(issues) == 0,
		cart=cart,
		issues=issues,
	)
