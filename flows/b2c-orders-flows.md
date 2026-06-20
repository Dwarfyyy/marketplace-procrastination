# B2C Orders Flows

Канонические user-flow для блока "Заказы" B2C-приложения.

## B2C-11. Отмена заказа {#b2c-11-cancel-order}

### Контекст

Покупатель передумал — это его право, пока заказ не ушёл в финальный статус.
Отмена освобождает резерв, выставленный на шаге checkout
(`active_quantity += quantity`, `reserved_quantity -= quantity` по каждому
`OrderItem`), через HTTP-вызов к B2B инвентаризации.

Это операция с двумя зависимостями: смена статуса заказа в своей БД (всегда
доступна) и возврат резерва в B2B (`POST /api/v1/inventory/unreserve`, может
быть недоступен). Эти две зависимости **не** должны быть атомарны с точки
зрения ответа покупателю: если откат резерва падает, покупатель всё равно
должен увидеть, что его *намерение отменить* принято — нельзя отвечать
`503`/«попробуйте позже» на отмену, иначе зависший резерв продолжит
блокировать остаток на складе, а покупатель не получит обратной связи.

### Идентификация пользователя и IDOR

`POST /api/v1/orders/{order_id}/cancel` находится под
`Authorization: Bearer <token>`. `buyer_id` — только из
`request.state.user_id`. Без `Authorization` → `401 UNAUTHORIZED`.

Поиск заказа: `select(Order).where(Order.id == order_id, Order.buyer_id ==
buyer_id)`. Если заказ не найден или принадлежит другому покупателю — `404
NOT_FOUND` в обоих случаях (никогда `403`, см. IDOR-принцип).

### Допустимые статусы для отмены

Отмена разрешена из `CREATED`, `PAID`, `ASSEMBLING`. Любой другой статус
(`DELIVERING`, `DELIVERED`, `CANCELLED`, `CANCEL_PENDING`) →
`409 CANCEL_NOT_ALLOWED`.

### Алгоритм (`POST /api/v1/orders/{order_id}/cancel`)

1. Найти заказ по `(order_id, buyer_id)` — если не найден, `404 NOT_FOUND`.
2. Проверить `order.status in (CREATED, PAID, ASSEMBLING)` — иначе
   `409 CANCEL_NOT_ALLOWED`.
3. **Unreserve в B2B**: `POST /api/v1/inventory/unreserve` с `order_id` и
   списком `[{sku_id, quantity}]` из `OrderItem`.
4. **Исход A — unreserve OK**: записать
   `OrderStatusHistory(status=CANCELLED, reason=<body>.reason)`,
   `order.status = CANCELLED`. Вернуть `200` с `OrderResponse`.
5. **Исход B — unreserve упал** (`B2BUnavailableError`, `httpx.RequestError`):
   - Записать `OrderStatusHistory(status=CANCEL_PENDING, reason=...)`,
     `order.status = CANCEL_PENDING`.
   - Залогировать ошибку. Вернуть `200` с `OrderResponse` (статус
     `CANCEL_PENDING`) — намерение отменить принято.
6. Асинхронный retry (вне HTTP-запроса) повторяет unreserve для заказов в
   `CANCEL_PENDING` и переводит их в `CANCELLED` после успешного ответа B2B.

### Edge cases

- **Без `Authorization`** → `401 UNAUTHORIZED`.
- **Чужой заказ / несуществующий** → `404 NOT_FOUND`.
- **Статус `DELIVERED` (или иной не из допустимых)** → `409 CANCEL_NOT_ALLOWED`
  (`test_cancel_delivered_order_returns_409`).
- **B2B недоступен** → `CANCEL_PENDING`, `200 OK`
  (`test_unreserve_failure_transitions_to_cancel_pending`).
- **Happy path** → `200 OK`, статус `CANCELLED`
  (`test_cancel_paid_order_transitions_to_cancelled`).

### Сценарии (тесты)

- `test_cancel_paid_order_transitions_to_cancelled` — happy path.
- `test_unreserve_failure_transitions_to_cancel_pending` — B2B недоступен →
  `CANCEL_PENDING`.
- `test_cancel_assembling_order_transitions_to_cancelled` — заказ в
  `ASSEMBLING` допустим для отмены → `200 CANCELLED`.
- `test_cancel_delivered_order_returns_409` — заказ в `DELIVERED` → `409`.
- `test_other_user_order_returns_404` — IDOR: чужой заказ → `404`.
- `test_cancel_order_not_authorized_returns_401` — без токена → `401`.

### ADR — асинхронный retry unreserve для `CANCEL_PENDING`

Рассмотрены: (1) Celery + exponential backoff, (2) management command по
cron, (3) Django Q. **Выбран вариант 2** (cron).

Критерии: (а) сложность настройки — cron не требует broker'а/воркера; (б)
гарантия при перезапуске — cron каждый тик читает `status = CANCEL_PENDING`
из БД, задачи не теряются при падении. Celery даёт finer backoff, но
требует Redis/RabbitMQ; Django Q — не под этот стек (FastAPI, не Django).

На первой итерации реализован только переход в `CANCEL_PENDING` с
логированием — без retry-воркера (scaffold).

## B2C-12. Реакция на события товаров от B2B {#b2c-12-handle-events}

### Контекст

Продавец (через B2B) может заблокировать, удалить или вывести из остатка товар,
который уже лежит в корзинах покупателей. Покупатель должен увидеть это при
следующем открытии корзины — но **заказы не трогаем**: если заказ уже оплачен
(`PAID`/`ASSEMBLING`/...), продавец принял обязательство и обязан отгрузить по
зафиксированным в `OrderItem` цене и составу (см. [B2C-9](#b2c-9-checkout)).
Событие касается только `cart.items`.

### `POST /api/v1/b2b/events`

Эндпоинт вызывается B2B (через service-to-service вызов, аналогично
`POST /api/v1/events/moderation` на стороне B2B) с заголовком `X-Service-Key`.
Без него или с неверным ключом — `401 UNAUTHORIZED`.

Тело запроса — конверт, который уже используется outbox-событиями B2B
(`crud/outbox.py`, см. `services/b2b`):

```json
{
  "event_type": "PRODUCT_BLOCKED" | "PRODUCT_DELETED" | "SKU_OUT_OF_STOCK",
  "idempotency_key": "uuid",
  "occurred_at": "2026-06-15T00:00:00Z",
  "payload": {
    "product_id": "uuid",
    "sku_ids": ["uuid", ...],
    "hard_block": false
  }
}
```

Для `SKU_OUT_OF_STOCK` `payload` может содержать одиночный `sku_id` вместо
`sku_ids` (формат `b2c.sku.out_of_stock` в B2B) — сервис принимает обе формы.

### Алгоритм

1. **Идемпотентность**: `idempotency_key` события проверяется через
   advisory-lock + таблицу `cart.product_events_processed`. Если ключ уже
   обработан — `200 {"processed": false, "updated_count": 0}`, без побочных
   эффектов (повтор после таймаута retry от B2B не должен ничего менять
   дважды).
2. **Обновление корзин**: по всем `sku_ids` из `payload` выполняется один
   batch `UPDATE cart.items SET unavailable_reason = ... WHERE sku_id IN (...)`
   — один запрос вместо N отдельных `UPDATE` по каждому SKU.
   `unavailable_reason` определяется типом события:
   - `PRODUCT_BLOCKED` → `PRODUCT_BLOCKED`;
   - `PRODUCT_DELETED` → `PRODUCT_DELETED`;
   - `SKU_OUT_OF_STOCK` → `OUT_OF_STOCK`.
3. Ключ идемпотентности записывается в `cart.product_events_processed`, ответ
   — `200 {"processed": true, "updated_count": N}`.

### Заказы не трогаются

Запрос не касается `orders.orders`/`orders.order_items` — у `OrderItem` нет
`sku_id`-индекса, обновляемого этим обработчиком, и сервис не выполняет
никаких запросов к таблицам заказов. Зафиксированные на момент checkout
`unit_price`/`line_total`/`product_title`/`sku_name` остаются неизменными для
уже оформленных заказов с тем же `sku_id`.

### Сценарии (тесты)

- `product_blocked_marks_cart_items_unavailable` — `PRODUCT_BLOCKED` со
  списком `sku_ids` → все `cart.items` с этими `sku_id` получают
  `unavailable_reason = "PRODUCT_BLOCKED"`.
- `orders_not_affected_by_product_blocked` — `OrderItem` с теми же `sku_id`
  не меняются (`unit_price`/`line_total` прежние).
- `idempotent_event_no_side_effects` — повтор того же `idempotency_key` →
  `200 {"processed": false, "updated_count": 0}`, `cart.items` не меняются
  повторно.
- `missing_service_key_returns_401` — запрос без `X-Service-Key` → `401
  UNAUTHORIZED`.

### ADR — хранение идемпотентности входящих событий о товарах

Рассмотрены три варианта хранения ключей идемпотентности для
`POST /api/v1/b2b/events`:

1. **Отдельная таблица `cart.product_events_processed`** (`idempotency_key`
   PK, `event_type`, `processed_at`) — выбрано.
2. **Поле в `cart_items`** (например, `last_event_idempotency_key` на каждой
   позиции корзины).
3. **Redis** (`SET idempotency_key 1 NX EX <ttl>`).

Критерии: (а) риск утечки памяти/диска при большом потоке событий и (б)
сложность очистки старых ключей.

Выбран вариант 1 — он уже используется на стороне B2B
(`ModerationProcessedEvent` в `services/b2b/database/models/moderation_event.py`),
что даёт единообразие. Таблица растёт линейно с количеством входящих событий,
но строки маленькие (UUID + строка + timestamp), и `processed_at` даёт простой
критерий очистки: `DELETE FROM cart.product_events_processed WHERE processed_at
< now() - interval '30 days'` — события одноразовые, хранить их дольше окна
повторных попыток B2B не нужно.

Вариант 2 (поле в `cart_items`) был бы неверным семантически: один и тот же
`sku_id` может встречаться в нескольких `cart_items` (у разных покупателей), а
идемпотентность определена на уровне *события*, а не позиции корзины —
пришлось бы записывать один и тот же `idempotency_key` в N строк, что не
помогает обнаружить дубликат, если на момент повтора корзины уже изменились
(товар убрали из корзины между двумя попытками B2B).

Вариант 3 (Redis) добавил бы внешнюю зависимость ради TTL, который у нас и так
реализуется простым `DELETE` по `processed_at` без отдельного процесса; кроме
того, при потере данных в Redis (если не настроена персистентность) дубликат
события привёл бы к повторному (хоть и идемпотентному по результату — `UPDATE
... SET unavailable_reason = ...` — повторное применение безопасно) проходу по
`cart.items`, что не критично, но не даёт выигрыша по сравнению с таблицей в
основной БД, которая уже есть и транзакционно согласована с обновлением
`cart.items`.
