# US-MOD-01: приём событий о товаре от B2B

## API

Реализован service-to-service endpoint:

```http
POST /api/v1/b2b/events
X-Service-Key: <B2B_SERVICE_KEY>
```

Принимает `idempotency_key` (генерируется B2B), `occurred_at`, `event_type`
(`PRODUCT_CREATED` / `PRODUCT_EDITED` / `PRODUCT_DELETED`) и
`payload.{product_id, seller_id, json_before?, json_after}`.

- `PRODUCT_CREATED` создаёт карточку `moderation.cards` в `PENDING` с
  `json_after` из payload.
- `PRODUCT_EDITED`:
  - `PENDING` / `IN_REVIEW` — обновляет `json_after` на месте, статус не
    меняется.
  - `MODERATED` / `BLOCKED` / `ARCHIVED` — возвращает карточку в `PENDING`,
    копируя текущую `json_after` в `json_before` перед обновлением.
  - `HARD_BLOCKED` — карточка не изменяется (продавец не может редактировать
    hard-blocked товар).
  - карточки нет — создаёт её в `PENDING` (на случай потери `CREATED`).
- `PRODUCT_DELETED` переводит карточку в `ARCHIVED` (уходит из очереди
  модератора) из любого состояния; если карточки нет — создаёт её сразу в
  `ARCHIVED`.

**Ответы:**
- `202 Accepted` — событие успешно обработано.
- `409 Conflict` — дублирующееся событие (тот же `idempotency_key` уже обработан).
- `401 Unauthorized` — отсутствует или неверен заголовок `X-Service-Key`.
- Все 4xx-ответы используют контракт `{code, message}`.

## Идемпотентность и транзакция

Обработанные события сохраняются в `moderation.product_events_processed`
(PK = `idempotency_key`, генерируется и присылается B2B). Транзакционный
advisory-lock по `idempotency_key` сериализует параллельные доставки
одинакового события. Блокировка карточки через `SELECT ... FOR UPDATE`,
переход статуса и запись processed-event выполняются одной транзакцией.

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
