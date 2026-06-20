import uuid

from crud.review import ProductReviewStats
from database.models.catalog.base import Category, Product
from database.models.catalog.variants import Sku
from database.models.orders.order import Order
from schemas.catalog import (
	CatalogProductCard,
	CatalogProductDetail,
	CatalogProductSeller,
	CatalogSku,
	CategoryRef,
	ImageRef,
)
from schemas.characteristic import Characteristic
from schemas.order import OrderResponse


def build_category_ref(
	category_id: uuid.UUID, categories_map: dict[uuid.UUID, Category]
) -> CategoryRef:
	chain: list[Category] = []
	seen: set[uuid.UUID] = set()
	current_id: uuid.UUID | None = category_id

	while current_id is not None and current_id not in seen:
		seen.add(current_id)
		category = categories_map.get(current_id)
		if category is None:
			break
		chain.append(category)
		current_id = category.parent_id

	path_categories = list(reversed(chain))
	if not path_categories:
		return CategoryRef(
			id=category_id,
			name="",
			parent_id=None,
			level=0,
			path=[],
		)

	leaf = path_categories[-1]
	return CategoryRef(
		id=leaf.id,
		name=leaf.name,
		parent_id=leaf.parent_id,
		level=len(path_categories) - 1,
		path=[category.name for category in path_categories],
	)


def image_refs(images: list) -> list[ImageRef]:
	ordered = sorted(images or [], key=lambda image: image.ordering)
	return [
		ImageRef(
			id=image.id,
			url=image.url,
			alt="",
			ordering=image.ordering,
			is_main=index == 0,
		)
		for index, image in enumerate(ordered)
	]


def product_images(product: Product) -> list[ImageRef]:
	return image_refs(product.images)


def build_catalog_sku(sku: Sku) -> CatalogSku:
	return CatalogSku(
		id=sku.id,
		name=sku.name,
		price=sku.price,
		discount=sku.discount,
		available_quantity=sku.active_quantity,
		characteristics=[
			Characteristic.model_validate(characteristic)
			for characteristic in (sku.characteristics or [])
		],
		images=image_refs(sku.images),
	)


def build_catalog_product_detail(product: Product) -> CatalogProductDetail:
	skus = list(product.skus or [])
	min_price, has_stock = sku_stats(skus)
	return CatalogProductDetail(
		id=product.id,
		name=product.title,
		slug=product.slug,
		description=product.description,
		min_price=min_price,
		has_stock=has_stock,
		images=product_images(product),
		characteristics=[
			Characteristic.model_validate(characteristic)
			for characteristic in (product.characteristics or [])
		],
		skus=[build_catalog_sku(sku) for sku in skus],
	)


def sku_stats(skus: list[Sku]) -> tuple[int, bool]:
	available_skus = [sku for sku in skus if sku.active_quantity > 0]
	if not available_skus:
		return 0, False
	return min(sku.price for sku in available_skus), True


def build_catalog_product_card(
	product: Product,
	categories_map: dict[uuid.UUID, Category],
	review_stats: ProductReviewStats | None,
) -> CatalogProductCard:
	skus = list(product.skus or [])
	min_price, has_stock = sku_stats(skus)

	seller = None
	if product.seller is not None:
		seller = CatalogProductSeller(
			id=product.seller_id,
			display_name=product.seller.company_name,
		)

	return CatalogProductCard(
		id=product.id,
		name=product.title,
		slug=product.slug,
		category=build_category_ref(product.category_id, categories_map),
		min_price=min_price,
		old_price=None,
		has_stock=has_stock,
		rating=review_stats.rating if review_stats else None,
		reviews_count=review_stats.reviews_count if review_stats else 0,
		images=product_images(product),
		seller=seller,
	)


def build_catalog_product_cards(
	products: list[Product],
	categories_map: dict[uuid.UUID, Category],
	review_stats_by_product: dict[uuid.UUID, ProductReviewStats],
) -> list[CatalogProductCard]:
	if not products:
		return []

	return [
		build_catalog_product_card(
			product,
			categories_map,
			review_stats_by_product.get(product.id),
		)
		for product in products
	]


def _cancel_reason(order: Order) -> str | None:
	for status in reversed(order.status_history):
		if status.status.value in ("CANCELLED", "CANCEL_PENDING"):
			return status.reason
	return None


def build_order_response(order: Order) -> OrderResponse:
	items = []
	for item in order.items:
		items.append(
			{
				"sku_id": item.sku_id,
				"product_id": item.product_id,
				"name": f"{item.product_title} — {item.sku_name}",
				"sku_code": str(item.sku_id),
				"quantity": item.quantity,
				"unit_price": item.unit_price,
				"line_total": item.line_total,
				"image_url": item.image_url,
			}
		)

	return OrderResponse(
		id=order.id,
		number=order.number,
		buyer_id=order.buyer_id,
		status=order.status.value,
		items=items,
		subtotal=order.subtotal,
		delivery_cost=order.delivery_cost,
		total=order.total,
		address={
			"id": order.address.id,
			"country": order.address.country,
			"region": order.address.region,
			"city": order.address.city,
			"street": order.address.street,
			"building": order.address.building,
			"apartment": order.address.apartment,
			"postal_code": order.address.postal_code,
			"recipient_name": order.address.recipient_name,
			"recipient_phone": order.address.recipient_phone,
			"is_default": order.address.is_default,
			"comment": order.address.comment,
			"created_at": order.address.created_at,
		},
		payment_method={
			"id": order.payment_method.id,
			"type": order.payment_method.type.value,
			"card_last4": order.payment_method.card_last4,
			"card_brand": order.payment_method.card_brand,
			"is_default": order.payment_method.is_default,
			"created_at": order.payment_method.created_at,
		},
		status_history=[
			{
				"status": status.status.value,
				"changed_at": status.changed_at,
				"reason": status.reason,
			}
			for status in order.status_history
		],
		comment=order.comment,
		cancel_reason=_cancel_reason(order),
		created_at=order.created_at,
		paid_at=order.paid_at,
	)
