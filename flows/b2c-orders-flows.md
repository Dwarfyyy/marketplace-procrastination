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
