# US-B2B-12: удаление SKU

## Реализация

`DELETE /api/v1/skus/{sku_id}` физически удаляет принадлежащий продавцу SKU.
Товар и SKU блокируются на время транзакции. Guardrails выполняются в строгом
порядке: сначала запрещается изменение `HARD_BLOCKED` товара, затем проверяется
`reserved_quantity`. SKU с активными резервами возвращает `409 ACTIVE_RESERVES`.

Если после удаления у товара в статусе `ON_MODERATION` не осталось SKU, товар
возвращается в `CREATED`, а в Moderation отправляется `PRODUCT_DELETED`. При
удалении доступного SKU у `MODERATED` товара в B2C отправляется
`SKU_OUT_OF_STOCK`. Удаление SKU и все side effects фиксируются одной
транзакцией через outbox.

## Тесты

- `test_delete_sku_succeeds`
- `test_delete_sku_with_active_reserves_returns_409`
- `test_last_sku_on_moderation_transitions_product_to_created`
- `test_delete_sku_hard_blocked_product_returns_403`
- `test_delete_other_sellers_sku_returns_403`
- `test_sku_out_of_stock_event_on_moderated_product`

## ADR

Рассматривались проверки в API-обработчике, единый валидатор и последовательные
ранние проверки в сервисе. Выбраны ранние проверки в сервисе: порядок
`HARD_BLOCKED` перед активными резервами виден непосредственно рядом с удалением
и сложнее случайно изменить. Блокировка товара и SKU и одна транзакция снижают
риск гонки с созданием SKU, резервированием и формированием outbox-событий.
