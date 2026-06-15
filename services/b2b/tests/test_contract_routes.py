from main import app
from schemas.product import ProductCreate, ProductPaginatedResponse


def test_edit_routes_use_patch_only() -> None:
	paths = app.openapi()["paths"]

	for path in (
		"/api/v1/products/{product_id}",
		"/api/v1/skus/{sku_id}",
	):
		assert "patch" in paths[path]
		assert "put" not in paths[path]


def test_sku_list_route_matches_contract() -> None:
	paths = app.openapi()["paths"]

	assert "/api/v1/products/{product_id}/skus" in paths
	assert "/api/v1/skus/product/{product_id}" not in paths


def test_delete_sku_route_matches_contract() -> None:
	paths = app.openapi()["paths"]

	assert "delete" in paths["/api/v1/skus/{sku_id}"]
	delete_responses = paths["/api/v1/skus/{sku_id}"]["delete"]["responses"]
	assert "204" in delete_responses
	assert "content" not in delete_responses["204"]


def test_product_create_allows_omitting_slug_and_images() -> None:
	assert ProductCreate.model_fields["slug"].is_required() is False
	assert ProductCreate.model_fields["images"].is_required() is False


def test_seller_product_list_uses_pagination_contract() -> None:
	assert set(ProductPaginatedResponse.model_fields) == {
		"items",
		"total_count",
		"limit",
		"offset",
	}
	operation = app.openapi()["paths"]["/api/v1/products"]["get"]
	response_schema = operation["responses"]["200"]["content"]["application/json"][
		"schema"
	]
	assert {"$ref": "#/components/schemas/ProductPaginatedResponse"} in response_schema[
		"anyOf"
	]
	assert {"limit", "offset", "include_deleted"} <= {
		parameter["name"] for parameter in operation["parameters"]
	}


def test_inventory_routes_match_contract() -> None:
	paths = app.openapi()["paths"]

	assert "/api/v1/inventory/reserve" in paths
	assert "/api/v1/inventory/unreserve" in paths
	assert "/api/v1/inventory/fulfill" in paths
	assert "/api/v1/reserve" not in paths
	assert "/api/v1/unreserve" not in paths
	assert "/api/v1/fulfill" not in paths


def test_moderation_event_route_matches_contract() -> None:
	openapi = app.openapi()
	paths = openapi["paths"]

	assert "post" in paths["/api/v1/moderation/events"]
	assert "204" in paths["/api/v1/moderation/events"]["post"]["responses"]
	assert "/api/v1/events/moderation" not in paths
	request_schema = openapi["components"]["schemas"]["ModerationEventRequest"]
	assert "event_type" in request_schema["required"]
	assert "status" not in request_schema["properties"]
