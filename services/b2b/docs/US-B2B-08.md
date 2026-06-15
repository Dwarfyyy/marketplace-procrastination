# US-B2B-08: резервирование и снятие резерва SKU

## Реализация

Добавлены service-to-service endpoints:

- `POST /api/v1/inventory/reserve`
- `POST /api/v1/inventory/unreserve`

Оба endpoint защищены `X-Service-Key`. Reserve-запрос содержит UUID
`idempotency_key`, `order_id` и непустой список `{sku_id, quantity}`. Unreserve
содержит `order_id` и позиции без `idempotency_key`. Повторяющиеся SKU
агрегируются перед проверкой.

Reserve атомарно уменьшает `active_quantity` и увеличивает
`reserved_quantity`. Unreserve выполняет обратное действие. Если хотя бы одной
позиции недостаточно, возвращается `409 INVENTORY_CONFLICT`, а вся транзакция
откатывается. При переходе `active_quantity` в ноль в той же транзакции
создаётся outbox-событие `SKU_OUT_OF_STOCK` для B2C. Outbox worker публикует
события `b2c.*` с `X-Service-Key` из `B2C_SERVICE_KEY`.

## Идемпотентность

Применённые операции хранятся в `catalog.inventory_operations`. Reserve
идемпотентен по `idempotency_key`, unreserve - по `order_id`. Повтор того же
payload возвращает стабильный контрактный ответ без повторного изменения
остатков. Повтор ключа с другим payload возвращает `409`. Транзакционный
advisory-lock по ключу сериализует одновременные повторы.

Ответ reserve имеет форму `{order_id, status: "RESERVED", reserved_at}`, ответ
unreserve - `{order_id, status: "UNRESERVED", processed_at}`.

## Тесты

- `test_reserve_all_skus_succeeds`
- `test_partial_insufficient_stock_returns_409_all_rollback`
- `test_idempotent_reserve_returns_200_without_double_deduction`
- `test_sku_out_of_stock_event_emitted`
- `test_unreserve_restores_quantities`

Additional contract tests cover:

- stable response snapshots for idempotent reserve retries;
- changed-payload idempotency conflicts;
- idempotent unreserve retries;
- all-or-nothing unreserve rollback;
- the flat `{code, message}` validation-error contract.

## ADR

The first successful response snapshot is stored in `inventory_operations.result`.
An idempotent retry returns that snapshot, so its response does not depend on later
inventory changes and does not need to lock or reload the affected SKU rows.

Рассматривались одна транзакция с `SELECT FOR UPDATE`, оптимистическая
блокировка с версией и retry, а также двухфазная запись по SKU. Выбрана одна
транзакция с пессимистической блокировкой всех SKU в стабильном порядке. Она
проще двухфазного протокола, обеспечивает all-or-nothing и предсказуемо
сериализует конкуренцию за последний остаток. Цена решения - ожидание блокировки
при высокой конкуренции; сортировка UUID снижает риск взаимных блокировок.
