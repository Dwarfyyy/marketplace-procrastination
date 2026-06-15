import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.catalog.inventory import Invoice
from tests.integration.conftest import CreateInvoiceData, auth_headers

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _invoice_count(db_session: AsyncSession) -> int:
	result = await db_session.execute(select(func.count()).select_from(Invoice))
	return int(result.scalar_one())


async def test_create_invoice_with_moderated_sku_returns_201(
	client: AsyncClient,
	create_invoice_data: CreateInvoiceData,
	db_session: AsyncSession,
) -> None:
	data = create_invoice_data
	headers = await auth_headers(data.owner.id, db_session)

	response = await client.post(
		"/api/v1/invoices",
		headers=headers,
		json={"items": [{"sku_id": str(data.moderated_sku.id), "quantity": 12}]},
	)

	assert response.status_code == 201
	body = response.json()
	assert body["seller_id"] == str(data.owner.id)
	assert body["status"] == "CREATED"
	assert len(body["items"]) == 1
	assert body["items"][0]["sku_id"] == str(data.moderated_sku.id)
	assert body["items"][0]["quantity"] == 12
	assert "accepted_quantity" in body["items"][0]
	assert body["items"][0]["accepted_quantity"] is None


async def test_created_invoice_can_be_accepted(
	client: AsyncClient,
	create_invoice_data: CreateInvoiceData,
	db_session: AsyncSession,
) -> None:
	data = create_invoice_data
	headers = await auth_headers(data.owner.id, db_session)
	create_response = await client.post(
		"/api/v1/invoices",
		headers=headers,
		json={"items": [{"sku_id": str(data.moderated_sku.id), "quantity": 3}]},
	)

	response = await client.post(
		f"/api/v1/invoices/{create_response.json()['id']}/accept",
		headers=headers,
	)

	assert response.status_code == 200
	assert response.json()["status"] == "ACCEPTED"
	assert response.json()["items"][0]["accepted_quantity"] == 3


async def test_get_invoice_does_not_change_created_status(
	client: AsyncClient,
	create_invoice_data: CreateInvoiceData,
	db_session: AsyncSession,
) -> None:
	data = create_invoice_data
	headers = await auth_headers(data.owner.id, db_session)
	create_response = await client.post(
		"/api/v1/invoices",
		headers=headers,
		json={"items": [{"sku_id": str(data.moderated_sku.id), "quantity": 3}]},
	)

	response = await client.get(
		f"/api/v1/invoices/{create_response.json()['id']}",
		headers=headers,
	)

	assert response.status_code == 200
	assert response.json()["status"] == "CREATED"
	assert response.json()["items"][0]["accepted_quantity"] is None


async def test_empty_items_returns_400(
	client: AsyncClient,
	create_invoice_data: CreateInvoiceData,
	db_session: AsyncSession,
) -> None:
	headers = await auth_headers(create_invoice_data.owner.id, db_session)

	response = await client.post("/api/v1/invoices", headers=headers, json={"items": []})

	assert response.status_code == 400
	assert response.json()["code"] == "EMPTY_ITEMS"
	assert await _invoice_count(db_session) == 0


async def test_non_moderated_sku_returns_400(
	client: AsyncClient,
	create_invoice_data: CreateInvoiceData,
	db_session: AsyncSession,
) -> None:
	data = create_invoice_data
	headers = await auth_headers(data.owner.id, db_session)

	response = await client.post(
		"/api/v1/invoices",
		headers=headers,
		json={"items": [{"sku_id": str(data.non_moderated_sku.id), "quantity": 1}]},
	)

	assert response.status_code == 400
	assert response.json()["code"] == "SKU_NOT_MODERATED"
	assert await _invoice_count(db_session) == 0


async def test_others_sku_returns_403(
	client: AsyncClient,
	create_invoice_data: CreateInvoiceData,
	db_session: AsyncSession,
) -> None:
	data = create_invoice_data
	headers = await auth_headers(data.owner.id, db_session)

	response = await client.post(
		"/api/v1/invoices",
		headers=headers,
		json={"items": [{"sku_id": str(data.other_seller_sku.id), "quantity": 1}]},
	)

	assert response.status_code == 403
	assert response.json()["code"] == "NOT_OWNER"
	assert await _invoice_count(db_session) == 0
