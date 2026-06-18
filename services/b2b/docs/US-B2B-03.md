# US-B2B-03: редактирование товара или SKU

## Что сделано

Редактирование карточки товара и SKU с повторной отправкой на модерацию при необходимости.

**Повторная модерация:** если товар в статусе `MODERATED` или `BLOCKED`, после успешного изменения статус меняется на `ON_MODERATION`, в outbox пишется событие `PRODUCT_EDITED` в форме `{event_type, idempotency_key, occurred_at, payload}`. Вложенный `payload` содержит обязательные снимки полной карточки `json_before` и `json_after`. Доставка - transactional outbox (`outbox_events`) + worker - RabbitMQ - сервис Moderation.

### API

- **`PATCH /api/v1/products/{product_id}`**
  - **Auth**: Bearer JWT.
  - **Body**: `ProductUpdate (title, description, category_id, characteristics[])`
  - **Код 200**: `ProductResponse` с актуальным `status` (при re-moderation - `ON_MODERATION`).
  - **Категория и характеристики**: новая категория валидируется, переданный список характеристик атомарно заменяет старый.
  - **Коды ошибок**: `404` `NOT_FOUND` (товар не найден); `403` `NOT_OWNER` (чужой товар); `403` `FORBIDDEN` (товар `HARD_BLOCKED`).

- **`PATCH /api/v1/skus/{sku_id}`**
  - **Auth**: Bearer JWT.
  - **Body**: `SkuUpdate (name, price, discount, cost_price, article, characteristics[])`.
  - **Код 200**: `SkuResponse` (включая неизменённый `reserved_quantity`).
  - **Характеристики**: переданный список атомарно заменяет старые характеристики SKU.
  - **Побочный эффект**: при `MODERATED`/`BLOCKED` у родительского товара - переход в `ON_MODERATION` + outbox-событие `PRODUCT_EDITED`.
  - **Коды ошибок**: `404` `NOT_FOUND` (SKU не найден); `403` `NOT_OWNER` (SKU чужого продавца); `403` `FORBIDDEN` (родительский товар `HARD_BLOCKED`).
## Запуск

```bash
make build up migrate
```
По адресу `localhost:8000/docs` можно найти документацию API-эндпоинтов

## Автотесты

```bash
make test
```

- `test_edit_product.py`

Дополнительно проверяются замена характеристик товара/SKU и единый формат ошибок `{code, message}`.

## ADR

- **Альтернативы IDOR-защите при редактировании**:
  1. **Проверка во view** - явное сравнение `product.seller_id` / `sku.product.seller_id` с `seller_id` из JWT в каждом обработчике или общем хелпере перед изменением.
  2. **Permission-класс** - декларативный `Depends`/middleware, который централизованно решает, может ли текущий продавец мутировать ресурс; для SKU ownership идёт через parent product.
  3. **Queryset-фильтр** - все выборки и update идут только через `WHERE seller_id = jwt.seller_id` (для SKU - join на product); чужой ресурс просто «не находится».
- **Выбор**: проверка ownership в service-слое через общие хелперы `_get_owned_product` и `_get_owned_sku`: загрузка сущности, сравнение с JWT, явный `403 NOT_OWNER` / `403 FORBIDDEN` для `HARD_BLOCKED`.
- **Критерии**: **сложность поддержки** - один хелпер на product и один на SKU проще, чем отдельный permission-слой поверх FastAPI, и нагляднее, чем различие 404 vs 403 у queryset-фильтра; **риск забыть проверку** - выше, чем у queryset-фильтра, но снижается тем, что edit/create/delete обязаны идти через эти хелперы, а не напрямую в CRUD; для SKU цепочка `sku - product - seller_id` зафиксирована в одном месте.

## Файлы

`services/b2b/`

### API эндпоинты

- `api/products.py` - `update_product`
- `api/sku.py` - `update_sku_endpoint`

### Сервисы

- `services/product_service.py` - `update_existing_product`, `_get_owned_product`, `build_product_response`
- `services/sku_service.py` - `update_sku`, `_get_owned_sku`, `build_sku_response`

### CRUD

- `crud/product.py` - `submit_for_moderation`, `update_product`
- `crud/sku.py` - `update`
- `crud/outbox.py`

### Исключения и схемы

- `exceptions/product.py` - `ProductForbiddenError`, `ProductNotOwnerError`
- `schemas/product.py` - `ProductUpdate`, `ProductResponse`
- `schemas/sku.py` - `SkuUpdate`, `SkuResponse`

### Автотесты

- `tests/integration/test_edit_product.py`
- `tests/integration/conftest.py` - `edit_product_data`, `blocked_product`
- `tests/factories/catalog.py` - `SkuFactory`
