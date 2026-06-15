import uuid

import pytest
from pydantic import ValidationError

from schemas.fulfill import FulfillResponse
from schemas.inventory import (
	InventoryOrderRequest,
	InventoryOrderResponse,
	ReserveRequest,
	ReserveResponse,
)


def test_reserve_contract_requires_order_and_idempotency_keys() -> None:
	request = ReserveRequest(
		idempotency_key=uuid.uuid4(),
		order_id=uuid.uuid4(),
		items=[{"sku_id": uuid.uuid4(), "quantity": 1}],
	)

	assert request.order_id
	assert request.idempotency_key
	assert set(ReserveResponse.model_fields) == {"order_id", "status", "reserved_at"}


def test_unreserve_contract_uses_order_id_without_idempotency_key() -> None:
	request = InventoryOrderRequest(
		order_id=uuid.uuid4(),
		items=[{"sku_id": uuid.uuid4(), "quantity": 1}],
	)

	assert request.order_id
	assert set(InventoryOrderResponse.model_fields) == {
		"order_id",
		"status",
		"processed_at",
	}
	with pytest.raises(ValidationError):
		InventoryOrderRequest(
			order_id=uuid.uuid4(),
			idempotency_key=uuid.uuid4(),
			items=[{"sku_id": uuid.uuid4(), "quantity": 1}],
		)


def test_fulfill_response_matches_inventory_order_contract() -> None:
	assert set(FulfillResponse.model_fields) == {
		"order_id",
		"status",
		"processed_at",
	}
