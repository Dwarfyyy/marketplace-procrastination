# Moderation Service

Сервис модерации товаров NeoMarket.

## US-MOD-01: приём событий о товаре от B2B

`POST /api/v1/events/product` — service-to-service эндпоинт (заголовок
`X-Service-Key`), принимает события `PRODUCT_CREATED` / `PRODUCT_EDITED` /
`PRODUCT_DELETED` от B2B и обновляет карточку товара в очереди модерации
(`moderation.cards`).

Канон-flow: [flows/moderation-flows.md#receive-product-events](../../flows/moderation-flows.md#receive-product-events).
OpenAPI: [moderation/openapi.yaml](../../moderation/openapi.yaml).
Подробности реализации и ADR: [docs/US-MOD-01.md](docs/US-MOD-01.md).

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
