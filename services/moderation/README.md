## US-MOD-03: approve product

`POST /api/v1/tickets/{ticket_id}/approve` moves an assigned moderation ticket
from `IN_REVIEW` to `MODERATED` internally and returns ticket status `APPROVED`.
The current moderator is supplied through the
`X-Moderator-ID` header until the shared identity contract is available.

The decision and a `MODERATED` event are committed in one database transaction.
The background outbox worker retries delivery to B2B and reuses the same
`idempotency_key`, so B2B can safely ignore duplicate attempts.

`POST /api/v1/tickets/{ticket_id}/block` uses the selected blocking
reason IDs and their `hard_block` flags. Hard reasons move the card to terminal
`HARD_BLOCKED` and emit `BLOCKED` with `hard_block=true`; subsequent moderator
mutations and seller `EDITED` events cannot move the card out of that state.

### ADR

Synchronous POST is simple but either loses the event after a local commit or
keeps the moderator waiting while B2B is unavailable. A shared event bus would
also be reliable, but adds infrastructure and contract work to the currently
small Moderation service. This implementation uses a transactional outbox:
it gives reliable retries and a fast approve response while matching the
idempotent B2B moderation endpoint already present in this repository.

For terminal-state protection, the service uses an enum status plus a shared
guard called by every mutating card endpoint. A separate `is_terminal` flag
would duplicate state and could drift, while moving records to an archive table
would complicate lookup and deletion events. The shared guard keeps normal-flow
auditing straightforward and still permits an explicit, audited admin data-fix
outside the public API.
