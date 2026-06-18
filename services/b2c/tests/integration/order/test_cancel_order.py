import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
import pytest
from exceptions.order import B2BUnavailableError
from tests.integration.order.conftest import OrderData
from tests.integration.cart.conftest import auth_headers

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _noop_unreserve(*args, **kwargs) -> None:
	pass


async def test_cancel_paid_order_transitions_to_cancelled(
	client: AsyncClient,
	db_session: AsyncSession,
	order_data: OrderData,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr("clients.b2b_client.unreserve_inventory", _noop_unreserve)

	response = await client.post(
		f"/api/v1/orders/{order_data.order.id}/cancel",
		headers=await auth_headers(order_data.order.buyer_id, db_session),
	)
	assert response.status_code == 200
	body = response.json()
	assert body["id"] == str(order_data.order.id)
	assert body["status"] == "CANCELLED"
	assert body["status_history"][0]["status"] == "PAID"
	assert body["status_history"][1]["status"] == "CANCELLED"


async def test_unreserve_failure_transitions_to_cancel_pending(
	client: AsyncClient,
	db_session: AsyncSession,
	order_data: OrderData,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	async def _raise_b2b_unavailable(*args, **kwargs):
		raise B2BUnavailableError()

	monkeypatch.setattr(
		"clients.b2b_client.unreserve_inventory",
		_raise_b2b_unavailable,
	)

	response = await client.post(
		f"/api/v1/orders/{order_data.order.id}/cancel",
		headers=await auth_headers(order_data.order.buyer_id, db_session),
	)
	assert response.status_code == 200
	body = response.json()
	assert body["id"] == str(order_data.order.id)
	assert body["status"] == "CANCEL_PENDING"
	assert body["status_history"][0]["status"] == "PAID"
	assert body["status_history"][1]["status"] == "CANCEL_PENDING"


async def test_cancel_assembling_order_transitions_to_cancelled(
	client: AsyncClient,
	db_session: AsyncSession,
	assembling_order_data: OrderData,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr("clients.b2b_client.unreserve_inventory", _noop_unreserve)

	response = await client.post(
		f"/api/v1/orders/{assembling_order_data.order.id}/cancel",
		headers=await auth_headers(
			assembling_order_data.order.buyer_id, db_session
		),
	)
	assert response.status_code == 200
	body = response.json()
	assert body["status"] == "CANCELLED"


async def test_cancel_delivered_order_returns_409(
	client: AsyncClient,
	db_session: AsyncSession,
	delivered_order_data: OrderData,
) -> None:
	response = await client.post(
		f"/api/v1/orders/{delivered_order_data.order.id}/cancel",
		headers=await auth_headers(
			delivered_order_data.order.buyer_id, db_session
		),
	)
	assert response.status_code == 409
	body = response.json()
	assert body["code"] == "CANCEL_NOT_ALLOWED"
	assert body["message"] == "Can't cancel order in this state"


async def test_other_user_order_returns_404(
	client: AsyncClient,
	db_session: AsyncSession,
	order_data: OrderData,
) -> None:
	response = await client.post(
		f"/api/v1/orders/{order_data.order.id}/cancel",
		headers=await auth_headers(uuid.uuid4(), db_session),
	)
	assert response.status_code == 404
	body = response.json()
	assert body["code"] == "NOT_FOUND"
	assert body["message"] == "Order not found"


async def test_cancel_order_not_authorized_returns_401(
	client: AsyncClient,
	order_data: OrderData,
) -> None:
	response = await client.post(
		f"/api/v1/orders/{order_data.order.id}/cancel",
		headers={},
	)
	assert response.status_code == 401
