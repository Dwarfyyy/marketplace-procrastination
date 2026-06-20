# US-CAT-03: карточка товара для покупателя

## Что сделано

Реализована карточка товара для B2C-витрины: `GET /api/v1/catalog/products/{product_id}` возвращает покупателю название, описание, характеристики, изображения и список SKU с ценой, скидкой и наличием. Ответ приведён к контрактной схеме `CatalogProductDetail` (`schemas/catalog.py`) — той же витринной семантике, что и `CatalogProductCard` из US-CAT-01/04. Внутренние поля продавца (`status`, `cost_price`, `reserved_quantity`) в публичный ответ не попадают: сериализация идёт через allow-list B2C-схемы, не пересекающиеся с B2B-представлением.

### API

- `GET /api/v1/catalog/products/{product_id}`
  - **Path params**: `product_id` — UUID товара
  - **Код 200**: объект `CatalogProductDetail`:
    - `id`, `name`, `slug`, `description`
    - `min_price: int` — минимальная цена среди SKU в наличии (`0`, если в наличии нет)
    - `has_stock: bool` — есть ли хотя бы один SKU с остатком
    - `images: list[ImageRef]` — объекты `{ id, url, alt, ordering, is_main }`
    - `characteristics: list[Characteristic]`
    - `skus: list[CatalogSku]`, где каждый SKU содержит `id`, `name`, `price`, `discount`, `available_quantity` (доступный остаток), `characteristics`, `images: list[ImageRef]`, `in_stock` (`true`, если `available_quantity > 0`)
  - **Код 404**: товар не найден, заблокирован (`status = BLOCKED`) или помечен удалённым (`deleted = true`)

Товар считается видимым для покупателя только при `status = MODERATED` и `deleted = false` — те же правила видимости, что и в листинге каталога (US-CAT-01/02).

### Соответствие контракту

Контракт (`b2c/openapi.yaml`: `/catalog/products/{product_id}`) зафиксирован арбитражем. Приведено в соответствие:

- путь перенесён на `/api/v1/catalog/products/{product_id}` (был `/api/v1/products/{id}`);
- поле `title` → `name`, добавлены обязательные `min_price` и `has_stock` (`CatalogProductDetail`);
- `images` отдаются объектами `ImageRef`, а не списком строк;
- в SKU поле `quantity` → `available_quantity` (`CatalogSku`);
- поле продавца `status` убрано из публичного ответа витрины.

## Запуск

```bash
make build up migrate
```

По адресу `localhost:8000/docs` можно найти документацию API-эндпоинтов.

## Автотесты

```bash
make test
```

- `tests/integration/catalog/test_product.py::test_product_card_returns_full_data_with_skus` — happy path: `name`, описание, изображения, SKU с ценой, скидкой и `available_quantity`/`in_stock`, агрегаты `min_price`/`has_stock`
- `tests/integration/catalog/test_product.py::test_seller_internal_fields_absent_in_response` — в ответе нет `status`, в SKU нет `cost_price`/`reserved_quantity`/`quantity`
- `tests/integration/catalog/test_product.py::test_images_serialized_as_image_refs` — `images` сериализуются как объекты `ImageRef`
- `tests/integration/catalog/test_product.py::test_blocked_product_returns_404` — заблокированный товар → 404
- `tests/integration/catalog/test_product.py::test_sku_without_stock_is_shown_as_unavailable` — SKU без остатка: `available_quantity = 0`, `in_stock = false`, `has_stock = false`

## ADR: разделение B2B/B2C представления товара

Рассмотрены три варианта: (1) отдельный Pydantic-serializer на каждый bounded context, (2) общий serializer с view-level фильтрацией полей перед отдачей, (3) общий serializer + отдельный endpoint с ручным маппингом полей.

Выбран вариант **(1) — отдельные явные allow-list схемы** (`services/b2c/schemas/*` независимы от `services/b2b/schemas/*`), что уже принятая в репозитории практика. Критерии:

- **Риск утечки нового поля**: при allow-list схеме новое поле ORM-модели (например, `status`/`cost_price`) не попадёт в ответ, пока не будет явно добавлено в Pydantic-схему — в отличие от view-level фильтрации по списку исключений, где забытое исключение сразу приводит к утечке.
- **Сложность поддержки**: B2C-схема лежит в одном файле рядом с остальными схемами сервиса, легко проверяется при code review и не требует синхронизации с B2B-кодовой базой при изменениях модели.
