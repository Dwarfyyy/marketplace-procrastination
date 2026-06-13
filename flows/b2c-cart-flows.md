# B2C Cart Flows

Канонические user-flow для блока "Корзина и избранное" B2C-приложения.

## B2C-6. Избранное {#b2c-6-favorites}

### Контекст

Покупатель находит товар, который пока не готов купить, и сохраняет его в
"Избранное" — отложенный список, к которому вернётся позже. Список должен
быть строго приватным: ни один покупатель не должен иметь возможность
посмотреть избранное другого пользователя.

### Идентификация пользователя (IDOR-защита)

Все эндпоинты блока находятся под `Authorization: Bearer <token>` и закрыты
middleware (`PRIVATE_PATHS_PREFIXES` в `middlewares/token_verification.py`).

`user_id` **всегда** берётся из `request.state.user_id`, заполненного
middleware после проверки подписи JWT и активной сессии в БД. Любой
`user_id`, переданный в query или body, **игнорируется** — иначе
`GET /favorites?user_id=<чужой>` превращается в IDOR и позволяет читать
чужой список (см. тест `user_id_from_query_is_ignored`).

Рассмотренные альтернативы (см. ADR в `services/b2c/docs/US-CART-01.md`):

- `user_id` в query/body — отклонено, классический IDOR;
- заголовок `X-User-Id` — отклонено, подделывается клиентом без подписи;
- `user_id` из проверенного JWT (middleware) — выбрано: подделать без
  компрометации токена нельзя.

### Хранение

Таблица `favorites` (`user_id`, `product_id`, `added_at`), уникальный
индекс по `(user_id, product_id)` — повторное добавление не создаёт дубль.

### Эндпоинты

`GET /api/v1/favorites`

Параметры:

- `limit` (query, optional, default `20`, `1..100`);
- `offset` (query, optional, default `0`).

Возвращает `PaginatedCatalogProducts` — те же карточки, что и в каталоге
(см. `b2c/catalog/openapi.yaml#CatalogProductCard`).

`PUT /api/v1/favorites/{product_id}`

Добавляет товар в избранное. Идемпотентно: повторный вызов для уже
сохранённого товара возвращает тот же код `204` и не создаёт дубль строки в
`favorites`.

`DELETE /api/v1/favorites/{product_id}`

Удаляет товар из избранного. Идемпотентно: удаление отсутствующей записи
тоже возвращает `204`.

### Batch-обогащение из B2B

Список избранного хранит только `(user_id, product_id)`. Перед отдачей
ответа `GET /favorites`:

1. Из `favorites` выбираются товары пользователя, отфильтрованные по
   доступности (см. ниже);
2. Категории всех товаров батчем подгружаются через
   `category_crud.get_all_categories_map`;
3. Рейтинг и количество отзывов батчем подгружаются через
   `review_crud.get_reviews_stats_by_product_ids` по списку `product_id`;
4. Из этих данных собираются `CatalogProductCard` (как в каталоге).

Батч-подгрузка категорий и отзывов избегает N+1 запросов на список
избранного.

### Алгоритм

1. **`PUT /favorites/{product_id}`**: если запись `(user_id, product_id)`
   уже существует — вернуть `204` без изменений. Иначе проверить, что товар
   существует и доступен (`status == MODERATED` и есть SKU с
   `active_quantity > 0`); если нет — `404 NOT_FOUND`. Иначе создать запись
   и вернуть `204`.
2. **`DELETE /favorites/{product_id}`**: удалить запись `(user_id,
   product_id)`, если она есть. В любом случае — `204`.
3. **`GET /favorites`**: выбрать записи пользователя, у которых товар
   `status == MODERATED` и есть SKU с `active_quantity > 0`
   (заблокированные/удалённые товары — пропускаются), обогатить из B2B и
   вернуть `PaginatedCatalogProducts`.

### Edge cases

- **Заблокированный/удалённый товар** в избранном не пропадает из таблицы
  `favorites`, но не попадает в ответ `GET /favorites` — пока товар не
  снова станет доступным.
- **Добавление недоступного/несуществующего товара** → `404 NOT_FOUND` с
  телом `{"code": "NOT_FOUND", "message": "..."}`.
- **Повторное добавление** → `204`, без дубля в БД (уникальный индекс
  `(user_id, product_id)`).
- **Удаление отсутствующей записи** → `204` (идемпотентно).
- **Без `Authorization`** → `401 UNAUTHORIZED` на всех трёх эндпоинтах.
- **`user_id` в query/body игнорируется** — используется только `user_id`
  из JWT.

### Сценарии (тесты)

- `add_to_favorites_returns_201` *(в реализации — `204`, см. примечание
  ниже)* — happy path: добавление нового товара в избранное.
- `get_favorites_enriched_from_b2b` *(`test_seller_name_is_returned` /
  `test_blocked_product_excluded_from_list`)* — happy path: список
  обогащён категорией, рейтингом, продавцом.
- `repeat_add_returns_200_not_duplicate` *(в реализации —
  `test_repeat_add_returns_204_not_duplicate`)* — повторное добавление не
  создаёт дубль и возвращает тот же код, что и первое добавление.
- `blocked_product_excluded_from_list` — заблокированный в B2B товар не
  попадает в ответ `GET /favorites`.
- `user_id_from_query_is_ignored` — `user_id` в query игнорируется,
  `user_id` берётся из JWT (IDOR-защита).

### Примечания

- Спецификация в задаче US-CART-01 ожидает коды `201`/`200` для
  добавления/повторного добавления, но OpenAPI-контракт и реализация
  используют `204 No Content` (без тела ответа) для `PUT`/`DELETE` —
  семантически эквивалентно ("операция выполнена, идемпотентно"), и так
  зафиксировано в `services/b2c/docs/US-CART-01.md`. Названия тестов
  адаптированы (`test_add_to_favorites_returns_204`,
  `test_repeat_add_returns_204_not_duplicate`), смысл сценариев сохранён.

## B2C-7. Подписки на изменения товара {#b2c-7-subscriptions}

### Контекст

Товара нет в наличии — покупатель уходит, но хочет вернуться. Подписка
"уведомить когда появится / когда подешевеет" удерживает намерение купить.
В рамках MVP реализуется только инфраструктура: создание и удаление
подписки. Фактическая отправка уведомлений (push/email при
`BACK_IN_STOCK` / `PRICE_DROP`) — отдельный модуль и не входит в scope
этого квеста; на этапе MVP подписка только сохраняется в БД.

### Идентификация пользователя (IDOR-защита)

Эндпоинты находятся под `Authorization: Bearer <token>` и закрыты той же
middleware, что и "Избранное" (`PRIVATE_PATHS_PREFIXES` в
`middlewares/token_verification.py`).

`user_id` **всегда** берётся из `request.state.user_id`, заполненного
middleware после проверки JWT и активной сессии в БД. `user_id`,
переданный в query/body, **игнорируется** — иначе подписку можно было бы
создать/удалить от имени другого пользователя (IDOR).

Рассмотренные альтернативы — те же, что и для "Избранное" (см. ADR в
`services/b2c/docs/US-CART-01.md` и `services/b2c/docs/US-CART-02.md`):

- `user_id` в query/body — отклонено, IDOR;
- заголовок `X-User-Id` — отклонено, подделывается клиентом без подписи;
- `user_id` из проверенного JWT (middleware) — выбрано.

### Хранение

Таблица `subscriptions` (`id`, `user_id`, `product_id`, `notify_in_stock`,
`notify_price_down`, `created_at`), уникальный индекс/constraint по
`(user_id, product_id)` — повторная подписка на тот же товар не создаёт
дубль и приводит к `409 CONFLICT`.

Типы уведомлений (`notify_on` в задаче / `events` в реализации:
`BACK_IN_STOCK`, `PRICE_DROP`) хранятся как два булевых флага в той же
строке подписки, а не как отдельная таблица событий или JSON/ArrayField —
см. ADR в `services/b2c/docs/US-CART-02.md`.

Отправка уведомлений (вне scope) предполагается отдельным
воркером/очередью, который читает `subscriptions` по `notify_in_stock` /
`notify_price_down` — заготовка под это не входит в текущую реализацию.

### Эндпоинты

`POST /api/v1/favorites/{product_id}/subscribe`

Создаёт подписку текущего пользователя на товар `{product_id}`. Тело
запроса — список типов уведомлений (`notify_on` / `events`):
`["BACK_IN_STOCK", "PRICE_DROP"]`.

`DELETE /api/v1/favorites/{product_id}/subscribe`

Удаляет подписку текущего пользователя на товар `{product_id}`.

### Алгоритм

1. **`POST /favorites/{product_id}/subscribe`**:
   - если список типов уведомлений пуст или содержит недопустимое
     значение — `400`/`422 INVALID_NOTIFY_ON`;
   - если товар с `{product_id}` не существует — `404 NOT_FOUND`;
   - если подписка `(user_id, product_id)` уже существует — `409
     SUBSCRIPTION_ALREADY_EXISTS`;
   - иначе создать запись в `subscriptions` и вернуть `201`/`204`.
2. **`DELETE /favorites/{product_id}/subscribe`**: удалить запись
   `(user_id, product_id)`, если она есть; вернуть `204`.

### Edge cases

- **Пустой/невалидный `notify_on`** → `400`/`422 INVALID_NOTIFY_ON`.
- **Подписка на несуществующий товар** → `404 NOT_FOUND`.
- **Повторная подписка на тот же товар** → `409
  SUBSCRIPTION_ALREADY_EXISTS`, без дубля в БД.
- **Без `Authorization`** → `401 UNAUTHORIZED`.
- **`user_id` в query/body игнорируется** — используется только `user_id`
  из JWT.
- **Отправка уведомлений** — не реализуется в этом квесте; подписка только
  сохраняется в `subscriptions`.

### Сценарии (тесты)

- `subscribe_returns_201_with_notify_on` *(в реализации —
  `test_subscribe_returns_204`, см. примечание ниже)* — happy path:
  подписка на товар создана.
- `duplicate_subscription_returns_409` *(`test_duplicate_subscription_returns_409`)*
  — повторная подписка на тот же товар → `409`.
- `invalid_notify_on_returns_400` *(в реализации —
  `test_empty_events_returns_400` / `test_invalid_events_returns_422`, см.
  примечание ниже)* — пустой/невалидный `notify_on` → `400`/`422`.
- `subscribe_to_unknown_product_returns_404`
  *(`test_subscribe_to_unknown_product_returns_404`)* — подписка на
  несуществующий товар → `404`.
- `test_unsubscribe_returns_204` — отписка удаляет запись из
  `subscriptions`.
- `test_subscribe_no_auth_returns_401` — без `Authorization` → `401`.

### Примечания

- Поле из задачи называется `notify_on`, в реализации — `events`
  (`SubscriptionEvent`: `BACK_IN_STOCK`, `PRICE_DROP`); смысл сценариев
  сохранён, см. `services/b2c/docs/US-CART-02.md`.
- Код успешного создания подписки в реализации — `204 No Content` (как и
  для "Избранное"), а не `201` — единообразно с остальными мутирующими
  эндпоинтами блока корзины/избранного.
- Невалидный тип в `events` (не входящий в `SubscriptionEvent`) отклоняется
  Pydantic-валидацией FastAPI и возвращает `422` с
  `code: VALIDATION_ERROR`; пустой список `events: []` — кастомная
  валидация в сервисе, `400 INVALID_NOTIFY_ON`. Оба случая соответствуют
  канон-сценарию `invalid_notify_on_returns_400`.
