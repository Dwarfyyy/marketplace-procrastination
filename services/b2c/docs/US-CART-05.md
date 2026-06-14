# US-CART-05: подборки товаров на главной

## Что сделано

Тематические подборки для главной страницы. B2C хранит **только список UUID**
товаров подборки; актуальные данные всегда запрашиваются из B2B
batch-обогащением. Удалённые/заблокированные в B2B товары тихо уходят в
`unavailable_ids`, подборка не ломается.

Контракт разделён на два эндпоинта (ранее был один `GET /catalog/collections`
с товарами внутри) — приведён в соответствие с канон-flow
`flows/b2c-cart-flows.md#b2c-15-collections` и `b2c/cart/openapi.yaml`.

### API

- **`GET /api/v1/catalog/collections`**
  - **200**: массив активных подборок — только метаданные
    (`CollectionSummary`: `id`, `name`, `description`, `cover_image_url`,
    `target_url`), **без товаров**, отсортированный по `priority`. Нет
    подборок → `200` с `[]`.
- **`GET /api/v1/catalog/collections/{collection_id}`**
  - **200**: товары подборки после batch-обогащения
    (`CollectionProducts`: `id`, `name`, `items: CatalogProductCard[]`,
    `unavailable_ids: uuid[]`). Доступны только `MODERATED`-товары с остатком
    `> 0`; остальные UUID — в `unavailable_ids`. Все недоступны → `items: []`,
    `unavailable_ids: [...]` (валидный ответ).
  - **404**: подборка не найдена/неактивна (`{code: NOT_FOUND}`).

## Запуск

```bash
make build up migrate
```

По адресу `localhost:8000/docs` — описание API.

## Автотесты

```bash
make test
```

`tests/integration/cart/test_collections.py` — канон-сценарии US-CART-05:

- `test_collections_list_returns_metadata_without_products` — список подборок
  без товаров внутри;
- `test_collection_products_enriched_from_b2b` — товары обогащены из B2B
  (категория, продавец);
- `test_unavailable_products_in_unavailable_ids` — заблокированные/удалённые в
  B2B → в `unavailable_ids`, не в `items`;
- `test_unknown_collection_returns_404` — несуществующая подборка → `404`.

## ADR

**Связь подборки с товарами**

- **Альтернативы**: массив UUID в поле подборки; отдельная таблица-связка;
  копия данных товара в B2C.
- **Выбор**: таблица-связка `storefront.collection_products`
  (`collection_id`, `product_id`).
- **Критерии**: (1) простота обновления состава — `INSERT`/`DELETE` без
  перезаписи JSON-массива и миграций; (2) консистентность при удалении товара
  в B2B — B2C хранит только UUID и проверяет доступность обогащением на каждый
  запрос, так что удалённый товар автоматически уходит в `unavailable_ids` без
  синхронизации копий.

## Файлы

`/services/b2c/`

### API

- `api/catalog.py` — `GET /collections`, `GET /collections/{collection_id}`

### Сервисы

- `services/collection_service.py` — `get_collection_summaries`,
  `get_collection_products`

### CRUD

- `crud/collection.py`

### Схемы

- `schemas/collection.py` — `CollectionSummary`, `CollectionProducts`
- `schemas/catalog.py` — `CatalogProductCard`, `CategoryRef`, `ImageRef`

### Исключения

- `exceptions/collection.py` — `CollectionNotFoundError`

### Модели

- `database/models/storefront/main.py` — `Collection`, `CollectionProduct`
