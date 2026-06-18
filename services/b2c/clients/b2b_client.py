import uuid

import httpx

from exceptions.order import B2BUnavailableError, ReserveFailedError


async def reserve_inventory(
    *,
    order_id: uuid.UUID,
    idempotency_key: uuid.UUID,
    items: list[dict],
    b2b_base_url: str,
    service_key: str,
) -> None:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{b2b_base_url}/api/v1/inventory/reserve",
                json={
                    "order_id": str(order_id),
                    "idempotency_key": str(idempotency_key),
                    "items": items,
                },
                headers={"X-Service-Key": service_key},
                timeout=10.0,
            )
    except httpx.RequestError as exc:
        raise B2BUnavailableError() from exc

    if resp.status_code == 409:
        detail = resp.json()
        raise ReserveFailedError(
            [{"reason": "INVENTORY_CONFLICT", "message": detail.get("message", "")}]
        )
    if resp.status_code not in (200, 201):
        raise B2BUnavailableError()


async def unreserve_inventory(
    *,
    order_id: uuid.UUID,
    items: list[dict],
    b2b_base_url: str,
    service_key: str,
) -> None:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{b2b_base_url}/api/v1/inventory/unreserve",
                json={
                    "order_id": str(order_id),
                    "items": items,
                },
                headers={"X-Service-Key": service_key},
                timeout=10.0,
            )
    except httpx.RequestError as exc:
        raise B2BUnavailableError() from exc

    if resp.status_code not in (200, 204):
        raise B2BUnavailableError()
