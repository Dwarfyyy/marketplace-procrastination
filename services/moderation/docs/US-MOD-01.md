# US-MOD-01: приём событий о товаре от B2B

## API

Реализован service-to-service endpoint:

```http
POST /api/v1/b2b/events
X-Service-Key: <B2B_SERVICE_KEY>
```

Принимает `idempotency_key` (генерируется B2B), `occurred_at`, `event_type`
(`PRODUCT_CREATED` / `PRODUCT_EDITED` / `PRODUCT_DELETED`) и
`payload.{product_id, seller_id, json_after}`.

- `PRODUCT_CREATED` создаёт карточку `product_moderation` в `PENDING` с
  `json_after` из payload (приватные поля SKU — `cost_price`,
  `reserved_quantity` — вырезаются).
- `PRODUCT_EDITED`:
  - `HARD_BLOCKED` — карточка не изменяется (продавец не может редактировать
    hard-blocked товар).
  - любой другой статус (`PENDING` / `IN_REVIEW` / `MODERATED` / `BLOCKED`) —
    возвращает карточку в `PENDING`, копирует текущую `json_after` в
    `json_before`, очищает `moderator_id`. Это инвалидирует любую
    незавершённую проверку: если модератор уже взял карточку в работу
    (`IN_REVIEW`) и продавец отредактировал товар, попытка `approve`/`block`
    по старым данным получит `409 CONFLICT`.
  - карточки нет — создаёт её в `PENDING` (на случай потери `CREATED`).
- `PRODUCT_DELETED` удаляет карточку из очереди модерации полностью; если
  карточки нет — событие принимается без побочных эффектов.

**Ответы:**
- `202 Accepted` — событие успешно обработано.
- `409 Conflict` — дублирующееся событие (тот же `idempotency_key` уже обработан).
- `401 Unauthorized` — отсутствует или неверен заголовок `X-Service-Key`.
- Все 4xx-ответы используют контракт `{code, message}`.

## Идемпотентность и транзакция

Обработанные события сохраняются в `product_events_processed`
(PK = `idempotency_key`, генерируется и присылается B2B). На Postgres
транзакционный advisory-lock (`pg_advisory_xact_lock`) по `idempotency_key`
сериализует параллельные доставки одинакового события; на других диалектах
(в частности SQLite в тестах) сериализация полагается на уникальность PK.
Блокировка карточки через `SELECT ... FOR UPDATE`, переход статуса и запись
processed-event выполняются в одной транзакции.

## Тесты

- `test_created_pending`
- `test_edited_returns_to_review`
- `test_edited_updates_in_review`
- `test_deleted_archived`
- `test_duplicate_event_no_side_effects`
- `test_missing_service_header_401`

## ADR: хранение "что было / что стало"

Рассматривались три варианта:
1. `json_before` + `json_after` (два полных JSONB-снимка)
2. Full snapshot `json_after` (только текущее состояние)
3. `delta` (только изменённые поля)

**Выбран вариант 1**: `json_before` + `json_after`. Критерии:

- **Место в БД**: два JSONB поля сопоставимы по размеру с одним full snapshot;
  `delta` компактнее, но требует цепочки обновлений для восстановления полного состояния.
- **Диагностика**: `json_before`/`json_after` даёт прямой ответ за один запрос без
  накопления цепочки событий. Full snapshot не объясняет *что* изменилось; `delta`
  требует восстановления.
- **Модератор**: side-by-side diff в UI прямо из двух снимков — быстрая диагностика
  причины возврата в очередь.

Варианты 2-3 отклонены: full snapshot скрывает дельту; `delta` сложнее восстанавливается
и непригоден для прямого рендера.
