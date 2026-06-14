# US-CAT-03: карточка товара для покупателя

## Что сделано

Реализована карточка товара для B2C каталога: `GET /api/v1/products/{id}` возвращает покупателю фото, описание, характеристики и список SKU с ценами, скидкой и наличием. Из ответа исключены внутренние поля продавца (`cost_price`, `reserved_quantity`) — сериализация идёт через отдельную B2C-схему (`schemas/product.py`, `schemas/sku.py`), не пересекающуюся с B2B-схемами.

*Примечание*: в репозитории отсутствуют файлы `flows/b2c-catalog-flows.md` и `b2c/catalog/openapi.yaml`, на которые ссылается задание US-CAT-03 — сверка с ними не выполнена, так как файлов нет.

### API

- `GET /api/v1/products/{id}`
  - **Path params**: `id` — UUID товара
  - **Код 200**: объект `Product`:
    - `id`, `slug`, `title`, `description`, `status`
    - `images: list[str]` — список URL изображений товара
    - `characteristics: list[Characteristic]`
    - `skus: list[Sku]`, где каждый SKU содержит `id`, `name`, `price`, `quantity` (доступный остаток), `discount`, `characteristics`, `images`, `in_stock` (`true`, если `quantity > 0`)
  - **Код 404**: товар не найден, заблокирован (`status = BLOCKED`) или помечен удалённым (`deleted = true`)

Товар считается видимым для покупателя только при `status = MODERATED` и `deleted = false` — те же правила видимости, что и в листинге каталога (US-CAT-01/02).

## Запуск

```bash
make build up migrate
```

По адресу `localhost:8000/docs` можно найти документацию API-эндпоинтов.

## Автотесты

```bash
make test
```

- `tests/integration/catalog/test_product.py::test_product_card_returns_full_data_with_skus` — happy path: фото, описание, SKU с ценами, скидкой и наличием
- `tests/integration/catalog/test_product.py::test_cost_price_absent_in_response` — явная проверка отсутствия `cost_price`/`reserved_quantity` в ответе
- `tests/integration/catalog/test_product.py::test_blocked_product_returns_404` — заблокированный товар → 404
- `tests/integration/catalog/test_product.py::test_sku_without_stock_is_shown_as_unavailable` — SKU без остатка отображается с `in_stock = false`

## ADR: разделение B2B/B2C представления товара

Рассмотрены три варианта: (1) отдельный Pydantic-serializer на каждый bounded context, (2) общий serializer с view-level фильтрацией полей перед отдачей, (3) общий serializer + отдельный endpoint с ручным маппингом полей.

Выбран вариант **(1) — отдельные явные allow-list схемы** (`services/b2c/schemas/*` независимы от `services/b2b/schemas/*`), что уже принятая в репозитории практика. Критерии:

- **Риск утечки нового поля**: при allow-list схеме новое поле ORM-модели (например, будущий `cost_price` в B2C) не попадёт в ответ, пока не будет явно добавлено в Pydantic-схему — в отличие от view-level фильтрации по списку исключений, где забытое исключение сразу приводит к утечке.
- **Сложность поддержки**: B2C-схема лежит в одном файле рядом с остальными схемами сервиса, легко проверяется при code review и не требует синхронизации с B2B-кодовой базой при изменениях модели.
