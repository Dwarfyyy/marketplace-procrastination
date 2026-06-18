import uuid

from database.models.catalog.inventory import InvoiceStatusEnum
from schemas.invoice import InvoiceItemResponse


def test_invoice_status_enum_matches_contract() -> None:
	assert {status.value for status in InvoiceStatusEnum} == {
		"CREATED",
		"PARTIALLY_ACCEPTED",
		"ACCEPTED",
		"CANCELLED",
	}


def test_invoice_item_response_contains_accepted_quantity() -> None:
	item = InvoiceItemResponse(
		id=uuid.uuid4(),
		sku_id=uuid.uuid4(),
		quantity=12,
	)

	assert item.model_dump()["accepted_quantity"] is None
