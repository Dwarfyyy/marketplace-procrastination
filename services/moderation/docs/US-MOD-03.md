# US-MOD-03: одобрение товара модератором

## API

Реализован модераторский endpoint:

```http
POST /api/v1/cards/{card_id}/approve
Authorization: Bearer <jwt с claim user_id>
```

Предусловия:

- карточка существует — иначе `404 NOT_FOUND`;
- `card.moderator_id == user_id` из токена — иначе `403 FORBIDDEN`;
- карточка в статусе `IN_REVIEW` — иначе `409 CONFLICT` (в т.ч. если правка
  продавца во время проверки вернула карточку в `PENDING`,
  см. `edited_returns_to_review` из US-MOD-01);
- у товара есть хотя бы один SKU (`json_after.skus` непусто) — иначе
  `409 CONFLICT`.

При успехе карточка переходит `IN_REVIEW` → `MODERATED`, в ответе —
`{card_id, status}`. Все 4xx-ответы используют плоский контракт
`{code, message}`.

## Исходящее событие для B2B

Переход и outbox-запись (`moderation.outbox_events`, `event_type =
MODERATED`, собственный `idempotency_key`) коммитятся одной транзакцией.
После коммита — синхронная попытка `POST /api/v1/moderation/events` в B2B
(`X-Service-Key: B2B_MODERATION_SERVICE_KEY`, см.
`services/b2b/docs/US-B2B-09.md`). При успехе outbox-запись помечается
`SENT`; при сбое остаётся `PENDING` для фонового воркера-ретрая — решение
модератора не теряется независимо от доступности B2B.

Идемпотентность: `idempotency_key` генерируется один раз при создании
outbox-записи и переиспользуется при ретраях доставки — B2B дедуплицирует
повтор (`catalog.moderation_processed_events`) без повторной публикации в
каталог.

## Тесты

- `test_approve_transitions_to_moderated_and_emits_event`
- `test_approve_others_card_returns_403`
- `test_approve_after_edited_returns_409`
- `test_approve_without_sku_returns_409`

## ADR: доставка события `MODERATED` в B2B

Рассматривались: (1) синхронный POST в обработчике `approve`, (2)
outbox-таблица с синхронной попыткой доставки сразу после коммита и
фоновым ретраем (выбрано), (3) event-bus (RabbitMQ).

- **Надёжность при отказе B2B**: (1) теряет решение модератора либо смешивает
  ответственность за ошибку B2B с ответом модератору; (2) и (3) сохраняют
  решение независимо от доступности B2B.
- **Время отклика**: (2) не медленнее (1) в happy path — доставка
  fire-and-forget после коммита.
- **Сложность**: (2) проще (3) — переиспользует HTTP-контракт
  `/api/v1/moderation/events` (US-B2B-09) без новой очереди/consumer'а.

Подробнее — `flows/moderation-flows.md#approve-product`.
