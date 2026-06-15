# Moderation Flows

Канонические user-flow для сервиса Moderation.

## MOD-1. Приём событий о товаре от B2B {#receive-product-events}

### Контекст

Каждый товар продавца перед публикацией в каталоге должен пройти модерацию.
B2B — источник правды о товаре (создание, правка, удаление), Moderation —
очередь карточек на проверку. Связь между сервисами — событийная
(`POST /api/v1/events/product`, как и `POST /api/v1/events/moderation` в
обратном направлении, см. `services/b2b/docs/US-B2B-09.md`).

Если событие потеряется или придёт дважды (ретрай B2B после таймаута/разрыва
сети) — карточка должна остаться в корректном статусе и не получить
дублирующихся побочных эффектов. Это требует **идемпотентности** и
**межсервисной авторизации** на входящем эндпоинте.

### Идентификация запроса

`POST /api/v1/events/product` — service-to-service эндпоинт, защищён
заголовком `X-Service-Key` (формат — как в `flows/auth-flows.md`: общий
секрет, проверяемый middleware'ом до тела запроса, не связан с JWT
покупателя/продавца). Без заголовка или с неверным значением —
`401 UNAUTHORIZED` (`{"code": "UNAUTHORIZED", "message": "..."}`), тело
запроса не обрабатывается.

### Идемпотентность

Каждое событие несёт `idempotency_key` (UUID), **генерируемый B2B** (клиентом
этого эндпоинта) — Moderation только сохраняет его. Хранение —
`moderation.product_events_processed` (PK = `idempotency_key`).

1. Транзакционный advisory-lock (`pg_advisory_xact_lock`) по
   `idempotency_key` сериализует параллельные доставки одного и того же
   события.
2. Если `idempotency_key` уже встречался — событие считается уже обработанным:
   `200 OK`, `processed: false`, состояние карточки и БД не меняются (никаких
   side effects).
3. Иначе — применяется переход состояния (см. ниже), `processed_at`
   записывается в `product_events_processed`, всё — одной транзакцией с
   изменением карточки.

Идемпотентность здесь — свойство **повтор не меняет состояние системы**, а не
"вернуть тот же ответ": повторный вызов с тем же ключом всегда возвращает
`processed: false`, независимо от результата первого вызова.

### Состояния карточки (`moderation.cards`)

```text
            PRODUCT_CREATED
                  │
                  ▼
 ┌──────────► PENDING ◄────────────┐
 │               │                 │
 │     модератор берёт в работу    │ PRODUCT_EDITED
 │               ▼                 │ (из MODERATED/BLOCKED/ARCHIVED)
 │           IN_REVIEW              │
 │               │                 │
 │   решение модератора             │
 │       ┌───────┼────────┐         │
 │       ▼       ▼        ▼         │
 │   MODERATED BLOCKED HARD_BLOCKED │
 │       │       │        │         │
 │       └───────┴────────┴─────────┘
 │
 │ PRODUCT_DELETED (из любого состояния)
 ▼
ARCHIVED
```

- `PENDING` — новая или возвращённая на повторную проверку карточка, ждёт
  модератора.
- `IN_REVIEW` — модератор взял карточку в работу (переход вне scope этого
  эндпоинта — выполняется отдельным API модератора).
- `MODERATED` / `BLOCKED` / `HARD_BLOCKED` — решения модератора (вне scope
  этого эндпоинта, см. `services/b2b/docs/US-B2B-09.md` — обратное
  направление).
- `ARCHIVED` — товар удалён продавцом, карточка не отображается в очереди.

### Алгоритм (`POST /api/v1/events/product`)

Тело запроса — `ProductEventRequest`: `event_type`
(`PRODUCT_CREATED` / `PRODUCT_EDITED` / `PRODUCT_DELETED`), `idempotency_key`,
`occurred_at`, `payload.{product_id, seller_id, snapshot}` (`snapshot` —
текущий слепок полей товара от B2B).

1. **Идемпотентность** — см. выше. При повторе — `200`, `processed: false`,
   без изменений.
2. **Блокировка карточки** (`SELECT ... FOR UPDATE` по `product_id`) — если
   карточки ещё нет, она будет создана для `PRODUCT_CREATED`/`PRODUCT_EDITED`
   (на случай, если `CREATED` потерялся, а `EDITED`/повтор дошёл первым —
   карточка создаётся в `PENDING` тем событием, которое дошло).
3. **Переход в зависимости от `event_type`**:
   - **`PRODUCT_CREATED`**: карточки нет → создать в `PENDING`,
     `json_after = snapshot`, `json_before = null`. Карточка уже есть (ретрай
     `CREATED`) → обновить `json_after`, статус не трогать.
   - **`PRODUCT_EDITED`**:
     - статус `PENDING` / `IN_REVIEW` — карточка уже в очереди/на проверке:
       обновить `json_after = snapshot` **на месте**, статус не меняется
       (`edited_updates_in_review`).
     - статус `MODERATED` / `BLOCKED` / `ARCHIVED` — товар уже прошёл цикл
       (или был удалён и восстановлен правкой): `json_before = текущий
       json_after`, `json_after = snapshot`, статус → `PENDING`
       (`edited_returns_to_review`).
     - статус `HARD_BLOCKED` — товар заблокирован безвозвратно, продавец не
       может его редактировать (см. `test_hard_blocked_product_rejects_seller_edits`
       в B2B); событие подтверждается (`processed: true`, идемпотентность
       записывается), но карточка не изменяется.
     - карточки нет — создать в `PENDING`, как при `CREATED`.
   - **`PRODUCT_DELETED`**: статус → `ARCHIVED` из любого состояния. Карточки
     нет — создать запись сразу в `ARCHIVED` (на случай, если `CREATED`
     потерялся, а `DELETED` дошёл — очередь не должна "увидеть призрака").
4. Записать `product_events_processed`, закоммитить транзакцию, вернуть
   `200 OK` с `ProductEventResponse` (`idempotency_key`, `processed: true`,
   `card_id`, `status` — итоговый статус карточки).

### Сценарии (тесты)

- `created_pending` (`test_created_pending`) — `PRODUCT_CREATED` создаёт
  карточку в `PENDING` со снапшотом в `json_after`.
- `edited_returns_to_review` (`test_edited_returns_to_review`) —
  `PRODUCT_EDITED` для карточки в `MODERATED`/`BLOCKED` возвращает её в
  `PENDING`, сохраняя предыдущий снапшот в `json_before`.
- `edited_updates_in_review` (`test_edited_updates_in_review`) —
  `PRODUCT_EDITED` для карточки в `IN_REVIEW` обновляет `json_after` на
  месте, статус не меняется.
- `deleted_archived` (`test_deleted_archived`) — `PRODUCT_DELETED` переводит
  карточку в `ARCHIVED`, она уходит из очереди модератора.
- `duplicate_event_no_side_effects` (`test_duplicate_event_no_side_effects`) —
  повтор события с тем же `idempotency_key` → `200`, `processed: false`, ни
  карточка, ни счётчики не меняются.
- `missing_service_header_401` (`test_missing_service_header_401`) — запрос
  без `X-Service-Key` → `401 UNAUTHORIZED`.

### ADR: что хранить в карточке — "что было / что стало"

Рассматривались три варианта хранения diff'а товара в `moderation.cards`:

1. **`json_before` + `json_after`** (выбрано) — два JSONB-снимка: состояние на
   момент последнего решения модератора и текущее состояние от B2B.
2. **Только `json_after`** (full snapshot) — храним только актуальный слепок,
   без истории.
3. **`delta`** — храним только изменённые поля между событиями.

Критерии:

- **Место в БД**: `json_before`/`json_after` — два JSONB-поля, сопоставимо с
  full snapshot (×2 размера одного снимка); `delta` компактнее, но требует
  накопления цепочки delta для восстановления полного состояния.
- **Диагностика инцидента**: `json_before`/`json_after` позволяет модератору
  и инженеру одним запросом увидеть "что было / что стало" без накопления
  серии diff'ов — критично, если карточка прошла несколько циклов
  `EDITED → MODERATED → EDITED`. Full snapshot не даёт ответа "что изменилось"
  без внешнего лога событий. `delta` восстанавливается дороже: нужно
  применить цепочку патчей от некоторого базового снимка.
- **Удобство для модератора**: `json_before`/`json_after` напрямую рендерится
  как side-by-side diff в UI модерации — ключевая причина повторной проверки.
  `delta` требует материализации перед показом; full snapshot не показывает
  причину возврата в очередь.

Выбран **`json_before` + `json_after`**: при незначительном росте хранения
(два снимка вместо одного) даёт прямой ответ на "что изменилось с прошлой
проверки" — без него модератору и инженеру инцидента пришлось бы
восстанавливать историю по логам события `PRODUCT_EDITED`. `delta` отклонён
как более сложный в восстановлении и непригодный для прямого рендера в UI.
