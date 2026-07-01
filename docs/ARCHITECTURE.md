# EPIC v1 — Architecture Notes

## Module map (matches SRS NFR-5.4-4)

| SRS Module | Folder | Key entry point |
|---|---|---|
| Authentication | `epic-backend/app/modules/auth/` | `router.py` — `/api/v1/auth/login`, `/callback`, `/me` |
| User Management | `epic-backend/app/modules/users/` | `service.upsert_from_identity` |
| Ticket Management | `epic-backend/app/modules/tickets/` | `service.create_ticket` etc. — **only legitimate path for mutations** |
| Knowledge Base | `epic-backend/app/modules/knowledge_base/` | Read-only `/kb/articles` |
| Notification Service | `epic-backend/app/modules/notifications/` | `service.dispatch` + `channels/teams.py` |
| Dashboard & Reporting | `epic-backend/app/modules/reporting/` | `/dashboard/overview`, `/reports/tickets` |
| Search & Filtering | `epic-backend/app/modules/search/` | `/search/tickets` (role-scoped) |
| Audit Logging | `epic-backend/app/modules/audit/` | `service.record` (write), `service.list_for_ticket` (read) |

## Why a service layer?

NFR-5.4-7 demands a future AI Orchestrator + integrations be added without major redesign. Every ticket mutation flows through `tickets/service.py`. The HTTP router is a thin adapter. When v2 begins:
- An AI Orchestrator (`app/services/ai/`) can call `TicketService.create_ticket()` directly and inherit identical audit + Teams-notification behaviour with zero duplication.
- A QRadar webhook in `app/services/integrations/qradar/` can create tickets the same way.

The `services/integrations/` and `services/ai/` folders are reserved with READMEs declaring "Not implemented in v1". Do not put code there in this version.

## State machine (SRS Figure 5 + agreed reopen)

```
                    ┌─ cancel ─→ CANCELLED ←─ cancel ─┐
                    │                                 │
OPEN ─assign→ ASSIGNED ─start_work→ IN_PROGRESS ←─ user_responds ─ PENDING_USER
                                          │  ↘                        ↗  │
                                          │   await_user             /   │
                                          │                         /    │
                                          └─ resolve → RESOLVED ←─ resolve
                                                          │  ↘
                                                          │   reopen → (back to IN_PROGRESS)
                                                          ↓
                                                       CLOSED
```

The `reopen` edge (RESOLVED → IN_PROGRESS) is a deliberate extension to the SRS state diagram, confirmed by the product owner on 30-Jun-2026. From CLOSED there is no transition — that's terminal.

## Notifications

- Channel: Microsoft Teams via Incoming Webhook, MessageCard format.
- Triggered events: `TICKET_CREATED`, `TICKET_ASSIGNED`, `TICKET_UPDATED` (status / priority / assignment / **comment**), `TICKET_RESOLVED`, `TICKET_CLOSED`, `TICKET_CANCELLED`.
- **Not** triggered on attachment upload (agreed 30-Jun-2026 to avoid noise).
- Delivery is async (fire-and-forget on a background thread). Every attempt is persisted in `notification_records`. Failures are logged with their HTTP error but never block the ticket action (NFR-5.4-2).

## Identity

- Production: OAuth2/OIDC authorization-code flow against Microsoft Entra ID. MFA is enforced upstream by Conditional Access using Microsoft Authenticator.
- Dev: `AUTH_PROVIDER=mock` swaps in a stand-in provider behind the same `IdentityProvider` ABC. The production code path is *always* OIDC — there is no parallel local-password system.

## Data model integrity

- `ticket_audit_logs` is insert-only at the ORM layer — no model exposes update/delete (REQ-4.8-8). Recommended additional defence: grant the app SQL account only `SELECT, INSERT` on that table.
- Ticket-number generation uses a year-scoped counter table (`ticket_counters`) with `SELECT … FOR UPDATE` on MS SQL Server to prevent duplicates under concurrency.
- Indexes are present on the hot ticket-list paths (`creator_id+status`, `assignee_id+status`, `status+priority`, `category`) to avoid table scans at 2,300-user scale.

## Frontend

- One React app, two route trees (`/employee/*` and `/admin/*`) with server-enforced RBAC on every backend endpoint.
- The Teams Static Tabs in `manifest.json` simply point at those two URLs. Inside Teams the SDK initialises silently (`microsoftTeams.app.initialize()`); outside Teams it's a no-op.
