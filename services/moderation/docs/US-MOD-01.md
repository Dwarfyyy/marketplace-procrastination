# US-MOD-01: приём событий о товаре от B2B

## API

Реализован service-to-service endpoint:

```http
POST /api/v1/events/product
X-Service-Key: <B2B_SERVICE_KEY>
```

Принимает `idempotency_key` (генерируется B2B), `occurred_at`, `event_type`
(`PRODUCT_CREATED` / `PRODUCT_EDITED` / `PRODUCT_DELETED`) и
`payload.{product_id, seller_id, snapshot}`.

- `PRODUCT_CREATED` создаёт карточку `moderation.cards` в `PENDING` с
  `json_after = snapshot`.
- `PRODUCT_EDITED`:
  - `PENDING` / `IN_REVIEW` — обновляет `json_after` на месте, статус не
    меняется.
  - `MODERATED` / `BLOCKED` / `ARCHIVED` — возвращает карточку в `PENDING`,
    сохраняя предыдущий снимок в `json_before`.
  - `HARD_BLOCKED` — карточка не изменяется (продавец не может редактировать
    hard-blocked товар).
  - карточки нет — создаёт её в `PENDING` (на случай потери `CREATED`).
- `PRODUCT_DELETED` переводит карточку в `ARCHIVED` (уходит из очереди
  модератора) из любого состояния; если карточки нет — создаёт её сразу в
  `ARCHIVED`.

Все 4xx-ответы используют плоский контракт `{code, message}`.

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

Рассматривались три варианта хранения diff'а товара в карточке:
`json_before` + `json_after` (два JSONB-снимка), full snapshot (только
`json_after`) и `delta` (только изменённые поля).

Выбран **`json_before` + `json_after`**. Критерии:

- **Место в БД**: сопоставимо с full snapshot (×2 размера одного снимка);
  `delta` компактнее, но требует накопления цепочки патчей для
  восстановления полного состояния.
- **Диагностика инцидента**: `json_before`/`json_after` даёт прямой ответ
  "что было / что стало" одним запросом — без накопления серии событий
  `PRODUCT_EDITED`. Full snapshot не показывает, что изменилось; `delta`
  восстанавливается дороже.
- **Удобство для модератора**: `json_before`/`json_after` напрямую рендерится
  как side-by-side diff в UI модерации — это и есть причина повторной
  проверки после правки.

`delta` отклонён как более сложный в восстановлении и непригодный для прямого
рендера; full snapshot отклонён, так как не объясняет причину возврата
карточки в очередь.
