# Moderation Service

Сервис модерации товаров NeoMarket.

## US-MOD-01: приём событий о товаре от B2B

`POST /api/v1/b2b/events` — service-to-service эндпоинт (заголовок
`X-Service-Key`), принимает события `PRODUCT_CREATED` / `PRODUCT_EDITED` /
`PRODUCT_DELETED` от B2B и обновляет карточку товара в очереди модерации
(`moderation.cards`).

Канон-flow: [flows/moderation-flows.md#receive-product-events](../../flows/moderation-flows.md#receive-product-events).
OpenAPI: [moderation/openapi.yaml](../../moderation/openapi.yaml).
Подробности реализации и ADR: [docs/US-MOD-01.md](docs/US-MOD-01.md).

## US-MOD-03: approve product

`POST /api/v1/tickets/{ticket_id}/approve` moves an assigned moderation ticket
from `IN_REVIEW` to `MODERATED` internally and returns ticket status `APPROVED`.
The current moderator is supplied through the
`X-Moderator-ID` header until the shared identity contract is available.

The decision and a `MODERATED` event are committed in one database transaction.
The background outbox worker retries delivery to B2B and reuses the same
`idempotency_key`, so B2B can safely ignore duplicate attempts.

`POST /api/v1/tickets/{ticket_id}/block` uses the selected blocking
reason IDs and their `hard_block` flags. Hard reasons move the card to terminal
`HARD_BLOCKED` and emit `BLOCKED` with `hard_block=true`; subsequent moderator
mutations and seller `EDITED` events cannot move the card out of that state.

## Запуск

```powershell
cp .env.example .env
docker-compose up -d
docker-compose exec moderation-backend uv run alembic -c /app/database/alembic.ini upgrade head
```

## Тесты

```powershell
make test
```

Требует Docker (используется `testcontainers.PostgresContainer`).
