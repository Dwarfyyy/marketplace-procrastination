# US-CART-05: подборки товаров на главной

## Что сделано

Тематические подборки для главной страницы. B2C хранит **только список UUID**
товаров подборки; актуальные данные всегда запрашиваются из B2B
batch-обогащением. Удалённые/заблокированные в B2B товары просто не попадают в
`products`, подборка не ломается.

Контракт — один эндпоинт `GET /catalog/collections`, отдающий подборки с
товарами внутри — в соответствии с канон-flow
`flows/b2c-cart-flows.md#b2c-15-collections`, `b2c/cart/openapi.yaml` и
каноном `b2c/openapi.yaml` (схема `Collection`, `required: [id, name,
products]`).

### API

- **`GET /api/v1/catalog/collections`**
  - **200**: массив активных подборок с товарами внутри
    (`Collection`: `id`, `name`, `description`, `cover_image_url`,
    `target_url`, `products: CatalogProductCard[]`), отсортированный по
    `priority`. В `products` попадают только доступные товары
    (`MODERATED`, не удалён, остаток `> 0`); недоступные в выдачу не
    включаются. Нет доступных товаров → `products: []`. Нет активных
    подборок → `200` с `[]`.

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

- `test_collections_list_returns_metadata_with_products` — список подборок с
  метаданными и `products` внутри;
- `test_collection_products_enriched_from_b2b` — товары обогащены из B2B
  (категория, продавец);
- `test_unavailable_products_excluded_from_products` —
  заблокированные/удалённые в B2B в `products` не попадают;
- `test_no_active_collections_returns_empty_list` — нет активных подборок →
  `200` `[]`.

## ADR

**Связь подборки с товарами**

- **Альтернативы**: массив UUID в поле подборки; отдельная таблица-связка;
  копия данных товара в B2C.
- **Выбор**: таблица-связка `storefront.collection_products`
  (`collection_id`, `product_id`).
- **Критерии**: (1) простота обновления состава — `INSERT`/`DELETE` без
  перезаписи JSON-массива и миграций; (2) консистентность при удалении товара
  в B2B — B2C хранит только UUID и проверяет доступность обогащением на каждый
  запрос, так что удалённый товар автоматически отсеивается из `products` без
  синхронизации копий.

## Файлы

`/services/b2c/`

### API

- `api/catalog.py` — `GET /collections`

### Сервисы

- `services/collection_service.py` — `get_collections`

### CRUD

- `crud/collection.py`

### Схемы

- `schemas/collection.py` — `Collection`
- `schemas/catalog.py` — `CatalogProductCard`, `CategoryRef`, `ImageRef`

### Модели

- `database/models/storefront/main.py` — `Collection`, `CollectionProduct`
