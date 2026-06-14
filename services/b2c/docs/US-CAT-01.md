# US-CAT-01: каталог товаров с фильтрацией и фасетами

## Что сделано

Реализован каталог товаров для B2C: получение списка товаров с фильтрацией, сортировкой, поиском и пагинацией, а также получение фасетов (счётчиков товаров по значениям фильтров) для динамического обновления UI фильтров.

### API

Перечень реализованных эндпоинтов:

- `GET /api/v1/catalog/products`
  - **Query/Path params**: `category_id` (опционально, UUID), `limit` (default `20`), `offset` (default `0`), `filter` (JSON-строка, опционально), `sort` (default `popularity`, допустимые значения: `price_asc`, `price_desc`, `popularity`, `new`), `q` (опционально, минимум 4 символа после trim)
  - **Код 200**: `PaginatedCatalogProducts` — список карточек `CatalogProductCard` в `items[]` (поля: `id`, `name`, `min_price`, `old_price`, `slug`, `category`, `has_stock`, `rating`, `reviews_count`, `images[]` (`ImageRef`), `seller`), плюс `total_count`, `limit`, `offset`
  - **Код 400**: `Invalid sort parameter. Allowed: ...` (невалидный параметр сортировки) / `Search query must be at least 4 characters` (поисковый запрос короче 4 символов) / `INVALID_FILTER` (невалидный JSON в `filter`)
  - **Код 502**: `B2B_UNAVAILABLE` (каталог недоступен)

- `GET /api/v1/catalog/facets/`
  - **Query/Path params**: `category_id` (обязательный UUID), `filters` (опционально, JSON-строка применённых фильтров)
  - **Код 200**: `FacetsResponse` — объект с полями `category_id`, `filters[]` (список доступных фильтров с метаданными: id, name, type, value/min/max), `facets[]` (список фасетов с полями name и values[], где каждое value содержит value и count — количество товаров)
  - **Код 404**: `Category with id <id> not found` (категория не найдена)
  - **Код 503**: текст ошибки (прочие сбои)

## Запуск

```bash
make build up migrate
```

По адресу `localhost:8000/docs` можно найти документацию API-эндпоинтов.

## Автотесты

```bash
make test
```

- `tests/integration/test_catalog.py::test_facets_returns_empty_list_for_empty_category` — фасеты возвращают пустой список для категории без товаров
- `tests/integration/test_catalog.py::test_facets_return_counts_per_filter_value` — фасеты возвращают корректные счётчики для каждого значения фильтра
- `tests/integration/test_catalog.py::test_catalog_returns_filtered_sorted_products` — каталог возвращает отфильтрованные и отсортированные товары
- `tests/integration/test_catalog.py::test_invalid_sort_returns_400` — невалидный параметр сортировки возвращает 400
- `tests/integration/test_catalog.py::test_search_description_returns_matching_products` — поиск по описанию возвращает соответствующие товары
- `tests/integration/test_catalog.py::test_search_title_returns_matching_products` — поиск по названию возвращает соответствующие товары
- `tests/integration/test_catalog.py::test_short_query_returns_400` — короткий поисковый запрос (< 4 символов) возвращает 400
- `tests/integration/test_catalog.py::test_empty_results_returns_200` — пустой результат поиска возвращает 200 с пустым списком
- `tests/integration/test_catalog.py::test_special_chars_do_not_break_query` — специальные символы в поиске не ломают запрос
- `tests/integration/test_catalog.py::test_products_list_filters_only_visible_products` — список товаров фильтрует только видимые товары (по статусу и наличию на складе)

Тесты успешно проходят (см. джобу tests).

