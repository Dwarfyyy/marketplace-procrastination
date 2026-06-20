from dataclasses import dataclass

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.cart.item import CartItem
from database.models.catalog.base import Product, ProductStatusEnum
from database.models.catalog.variants import Sku
from database.models.orders.order import Order, OrderStatusEnum
from database.models.orders.order_item import OrderItem
from database.models.identity.user import User
from tests.factories.catalog import CartItemFactory, CategoryFactory, ProductFactory, SkuFactory
from tests.factories.order import AddressFactory, OrderFactory, OrderItemFactory, PaymentMethodFactory
from tests.factories.user import UserFactory

PRODUCT_EVENT_SERVICE_KEY_HEADERS = {"X-Service-Key": "test-b2b-service-key"}


@dataclass(frozen=True, slots=True)
class ProductEventData:
	user: User
	product: Product
	skus: list[Sku]
	cart_items: list[CartItem]
	order: Order
	order_items: list[OrderItem]


@pytest.fixture()
async def product_event_data(db_session: AsyncSession) -> ProductEventData:
	user = UserFactory.build()
	category = CategoryFactory.build()
	product = ProductFactory.build(
		category_id=category.id,
		status=ProductStatusEnum.BLOCKED,
	)
	skus = [SkuFactory.build(product_id=product.id) for _ in range(2)]
	cart_items = [
		CartItemFactory.build(
			user_id=user.id,
			sku_id=sku.id,
			quantity=1,
			unit_price_at_add=sku.price,
		)
		for sku in skus
	]
	address = AddressFactory.build(user_id=user.id)
	payment_method = PaymentMethodFactory.build(user_id=user.id)
	order = OrderFactory.build(
		buyer_id=user.id,
		address_id=address.id,
		payment_method_id=payment_method.id,
		status=OrderStatusEnum.PAID,
	)
	order_items = [
		OrderItemFactory.build(
			order_id=order.id,
			sku_id=sku.id,
			product_id=product.id,
			unit_price=sku.price,
		)
		for sku in skus
	]

	db_session.add_all(
		[
			user,
			category,
			product,
			*skus,
			*cart_items,
			address,
			payment_method,
			order,
			*order_items,
		]
	)
	await db_session.commit()

	return ProductEventData(
		user=user,
		product=product,
		skus=skus,
		cart_items=cart_items,
		order=order,
		order_items=order_items,
	)
