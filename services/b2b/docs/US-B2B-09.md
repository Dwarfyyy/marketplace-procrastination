# US-B2B-09: применение решения модерации

## API

Реализован service-to-service endpoint:

```http
POST /api/v1/moderation/events
X-Service-Key: <MODERATION_SERVICE_KEY>
```

Endpoint принимает `idempotency_key`, `product_id`, решение `event_type` и данные
блокировки. Успешная обработка и идемпотентный повтор возвращают `204 No Content`.

- `MODERATED` переводит товар в `MODERATED` и очищает причины блокировки.
- `BLOCKED` с `hard_block=false` переводит товар в `BLOCKED`.
- `BLOCKED` с `hard_block=true` переводит товар в `HARD_BLOCKED`.
- Любая блокировка создаёт outbox-событие `PRODUCT_BLOCKED` для B2C.
- Повтор обработанного `idempotency_key` возвращает `204` без side effects.

Все 4xx-ответы используют плоский контракт `{code, message}`.

## Идемпотентность и транзакция

Обработанные события сохраняются в `catalog.moderation_processed_events`.
Транзакционный advisory-lock по `idempotency_key` сериализует параллельные
доставки одинакового события. Блокировка товара через `SELECT FOR UPDATE`,
изменение статуса, processed-event и B2C outbox-событие записываются одной
транзакцией.

## Тесты

- `test_moderated_event_clears_blocking_data`
- `test_blocked_soft_saves_field_reports`
- `test_blocked_hard_sets_terminal_status`
- `test_hard_blocked_product_rejects_seller_edits`
- `test_duplicate_event_same_idempotency_key_no_side_effects`
- `test_missing_service_key_returns_401`
- `test_b2c_service_key_cannot_apply_moderation`
- `test_blocked_without_reason_returns_flat_400`

## ADR

Рассматривались отдельная таблица processed events, поле последнего события в
`Product` и conditional upsert. Выбрана отдельная таблица с первичным ключом по
`idempotency_key`: она не смешивает транспортную идемпотентность с доменной
моделью и надёжно закрывает race condition вместе с advisory-lock. В отличие от
поля на товаре подход поддерживает несколько событий и упрощает аудит.
