## US-MOD-03: approve product

`POST /api/v1/products/{product_id}/approve` moves an assigned moderation card
from `IN_REVIEW` to `MODERATED`. The current moderator is supplied through the
`X-Moderator-ID` header until the shared identity contract is available.

The decision and a `MODERATED` event are committed in one database transaction.
The background outbox worker retries delivery to B2B and reuses the same
`idempotency_key`, so B2B can safely ignore duplicate attempts.

### ADR

Synchronous POST is simple but either loses the event after a local commit or
keeps the moderator waiting while B2B is unavailable. A shared event bus would
also be reliable, but adds infrastructure and contract work to the currently
small Moderation service. This implementation uses a transactional outbox:
it gives reliable retries and a fast approve response while matching the
idempotent B2B moderation endpoint already present in this repository.
