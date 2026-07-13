# EPIC — Spec Implementation Progress

Tracks /SPEC.md sections. Status is one of NOT STARTED / IN PROGRESS / DONE.
Each future session should read this file first, then SPEC.md, before writing code.

| §   | Title                         | Status             | Note                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| --- | ----------------------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | Ticket data model             | DONE (foundations) | See "Session 1" below for what's additive-only vs. fully wired.                                                                                                                                                                                                                                                                                                                                                                      |
| 2   | Assignment Groups             | DONE (foundations) | Model + seed data + read endpoints done. Admin CRUD deferred to §5 session.                                                                                                                                                                                                                                                                                                                                                          |
| 3   | Status/workflow               | DONE (backend)     | New `workflow_status` field + ticket-type-specific state machine (INCIDENT / SERVICE_REQUEST) layered on top of the untouched generic `status`/state_machine.py. See "Session 2" below.                                                                                                                                                                                                                                              |
| 4   | SLA model (business-hours)    | NOT STARTED        | Current SLA logic (core/sla.py, sla_scanner.py) is 24/7 wall-clock, keyed by priority only (not ticket_type × priority). Business-hours/timezone-aware calendar not started. `Location.timezone` (added this session) is there to support it. Session 2 added the _pause-clock bookkeeping_ fields (`sla_paused_at`/`sla_paused_total_seconds`) §3 requires, but not business-hours due-date math — that's still this section's job. |
| 5   | Roles & Permissions (dynamic) | NOT STARTED        | Still on the fixed Role enum in core/rbac.py (EMPLOYEE/IT*ENGINEER/IT_MANAGER/SYSTEM_ADMIN). No DB-backed permission registry, no custom roles, no Vendor/FMS Technician \_role* (only the UserProfile.user_type=VENDOR foundation column exists — see §2 note).                                                                                                                                                                     |
| 6   | Routing engine                | NOT STARTED        | No RoutingRule model/table. Tickets can carry an assignment_group_id (nullable) but nothing auto-assigns it yet — assignment_group_id is set to NULL unless a caller passes it explicitly. No monitoring-tool ingestion endpoint.                                                                                                                                                                                                    |
| 7   | Escalation                    | NOT STARTED        | No change beyond existing SLA-scanner _notifications_ (which are informational, not reassignment).                                                                                                                                                                                                                                                                                                                                   |
| 8   | Dashboard — 5 views           | NOT STARTED        | Existing reporting module (app/modules/reporting) predates this spec; not evaluated against the 5-view list yet.                                                                                                                                                                                                                                                                                                                     |
| 9   | Security requirements         | ONGOING            | Applied within scope of what was touched each session (see session notes below); no new gaps knowingly introduced. Full review against §9 should happen again once §5/§6 add real authorization surface.                                                                                                                                                                                                                             |
| 10  | Out of scope                  | N/A                | Reference only — nothing to implement.                                                                                                                                                                                                                                                                                                                                                                                               |

## Session 1 (this session) — what was actually built for §1 and §2

**New module:** `app/modules/catalogue/` — `Location`, `AssignmentGroup`,
`UserAssignmentGroup` (membership), `CatalogueCategory`/`CatalogueSubcategory`/`CatalogueItem`
(the 3-level hierarchy). Seed data in `seed_data.py`, idempotent loader in `seed.py`,
read-only endpoints in `router.py` under `/api/v1/catalogue/*` (locations, assignment-groups,
assignment-groups/mine, tree). Run via `python scripts/seed_catalogue.py`.

**UserProfile** (`app/modules/users/models.py`): added `user_type` (INTERNAL/VENDOR,
foundation column only — no permission logic wired to it yet, see §5) and
`home_location_id` (FK to `locations`, nullable). New endpoint
`PATCH /api/v1/users/{user_id}/home-location` (self or SYSTEM_ADMIN) to set it.

**Ticket** (`app/modules/tickets/models.py`): added, all per SPEC §1 —
`requestor_id` (defaults to `creator_id` in `create_ticket` when omitted), `location_id`
(auto-filled from `creator.home_location_id` at creation, overridable via the
`TicketCreateIn.location_id` field), `category_id`/`subcategory_id`/`item_id` (new hierarchy
FKs — **additive**, the existing flat `category` string column and its `CATEGORIES` enum are
untouched and still required; nothing yet forces a ticket to also carry the new hierarchy),
`channel` (defaults to SELF_SERVICE), `device_name`/`device_ip_address`/`device_site_name`
(only populated when channel == MONITORING_TOOL), `assignment_group_id` (nullable — nothing
assigns it automatically pending §6), `first_response_at`, `response_sla_status` /
`resolution_sla_status` (nullable placeholder columns, no logic — per spec's own
instruction), `breached_reason`, `vendor_ticket_id`, `is_from_email_mgr`.

**Alembic migrations:** `0008_catalogue_tables.py` (new tables),
`0009_user_ticket_spec1_fields.py` (new columns on `user_profiles`/`tickets`). Both have
working `downgrade()`.

**Verified this session:** all 31 pre-existing backend tests still pass unmodified; full
`create_app()` boots; an authenticated HTTP smoke test (login → set home-location → create
ticket) confirms `ticket.location_id` auto-fills from `home_location_id` and `requestor`
defaults to the creator, exactly as required by §1.

### Deliberate scope decisions (read before continuing §3+)

1. **Flat `category` vs. new hierarchy**: kept both. Cutting the ticket-creation flow, the
   state machine, the frontend cascading select, and existing tests over to _require_ the new
   3-level hierarchy (and retiring the flat enum) was judged too large/risky to bundle into
   this session's "foundations" scope — do it as an explicit early task in whichever session
   picks up §3 or the routing engine (§6), since routing rules key off category anyway.
2. **`location_id` / `assignment_group_id` are nullable at the DB level**, not `NOT NULL` as
   SPEC §1/§2 literally say "required." Given SPEC §10 rules out a historical-data migration
   and there's no routing engine yet to guarantee every new ticket gets a group, enforcing
   `NOT NULL` today would either break ticket creation or require inventing a fake default
   group. Tighten both once §6 (routing engine, which must supply a fallback target) lands.
3. **Vendor user type** is a plain `user_type` column with no enforcement yet — the "restricted
   default permission set" part of §2 is explicitly deferred to §5's dynamic permission
   registry, per the spec's own phasing.
4. **Catalogue item seeding**: seeded a representative 2-4 items per subcategory (140 items
   total across 95 subcategories / 8 towers) rather than exhaustively inventing a full
   production catalogue — the spec frames the towers/subcategory count (~15-25 per tower) as
   the hard requirement, and item-level granularity is naturally something IT admins will
   flesh out via `catalogue.edit` (§5) rather than something to hallucinate wholesale in a
   migration.
5. **No admin CRUD endpoints** for Location/AssignmentGroup/catalogue entries yet — only
   read endpoints. "Admin-configurable" (§2) is being treated as a §5 (permission-gated write
   access) concern, not a §1/§2 one.

### Suggested next task

Either §5 (dynamic permissions — unblocks real enforcement of vendor restrictions and
catalogue/group editing) or §6 (routing engine — unblocks making `location`/`assignment_group`
actually required, since routing is what guarantees every ticket gets one). §4 (business-hours
SLA) is now the natural follow-on to §3 — it can consume `sla_paused_total_seconds` directly
instead of re-deriving pause history from the audit log.

## Session 2 (this session) — what was actually built for §3

**New module:** `app/modules/tickets/workflow.py` — ticket-type-specific workflow state
machines for SPEC §3, additive alongside the pre-existing generic `status` field and
`state_machine.py` (both left completely untouched, per Session 1's "don't break what
exists" precedent). Defines:

- `INCIDENT_WORKFLOW_STATUSES` = PROGRESSING, ON_HOLD, PEND_3RDPARTY, PEND_USER, APPROVED, RESOLVED
- `SERVICE_REQUEST_WORKFLOW_STATUSES` = PROGRESSING, ON_HOLD, PEND_3RDPARTY, PEND_USER, IN_APPROVAL, FULFILLED
- A `(from_state, event) -> to_state` transition graph per ticket type (mirrors the existing
  `state_machine.py` convention), plus `next_workflow_state` / `allowed_workflow_target_states_for`
  / `event_for_workflow_target` — same function shapes as the existing `state_machine.py` API.
- `PAUSE_WORKFLOW_STATUSES = {"PEND_USER", "PEND_3RDPARTY"}` and `is_pause_state()`, used to
  drive the SLA pause clock (see below).
- PROBLEM/CHANGE_REQUEST ticket types get no workflow (SPEC §3 only defines state sets for
  Incidents and Service Requests) — `workflow_statuses_for()` returns `[]` for them and any
  attempt to transition raises `DomainError` (fail closed, SPEC §9).

**Ticket model** (`app/modules/tickets/models.py`): added

- `workflow_status` (nullable string) — the §3 field itself. Populated at creation
  (`wf.initial_workflow_status(ticket_type)` → `PROGRESSING` for INCIDENT/SERVICE_REQUEST,
  `NULL` otherwise) and re-derived on `reclassify_ticket` (see below).
- `sla_paused_at` / `sla_paused_total_seconds` — bookkeeping for SPEC §3's literal
  requirement ("Resolution SLA clock pauses during PEND_USER/PEND_3RDPARTY"). This session
  implements the pause/resume mechanics (start the clock entering a pause state, stop +
  accumulate leaving one); it deliberately does **not** implement business-hours due-date
  math — that's still §4's job, and `sla_paused_total_seconds` is exactly the number §4 will
  need to subtract.

**Ticket service** (`app/modules/tickets/service.py`): added

- `change_workflow_status(db, ticket_id, target_workflow_status, actor)` — the §3 mutation.
  Same permission model as the existing `change_status` (IT Engineer/Manager/Admin only,
  `Forbidden` otherwise — SPEC §9 fail-closed), same terminal-legacy-status guard, audit-logs
  every transition (`Action.WORKFLOW_STATUS_CHANGE`), starts/stops the SLA pause clock via new
  `_start_sla_pause`/`_end_sla_pause` helpers, and mirrors reaching a terminal workflow state
  (RESOLVED/FULFILLED) into the existing `resolved_at` column so SLA-status/reporting code
  that already reads `resolved_at` (e.g. `Ticket.sla_status`) keeps working unmodified.
- `reclassify_ticket` now also re-derives `workflow_status` for the new `ticket_type` (its own
  initial state, or `NULL` if the new type has no §3 workflow) and ends any in-progress SLA
  pause first, rather than leaving a stale/type-mismatched value or a dangling pause clock.
- `change_status` and `cancel_ticket` (the pre-existing generic-status mutations) now also
  stop the pause clock if a ticket reaches a terminal legacy status (RESOLVED/CLOSED/CANCELLED)
  while `sla_paused_at` is still set — covers an engineer resolving/cancelling via the old
  endpoint instead of the new workflow-status one.

**API** (`app/modules/tickets/router.py`): `POST /api/v1/tickets/{ticket_id}/workflow-status`
— rate-limited `30/minute` (same limit as every other ticket mutation endpoint, per SPEC §9),
audit-logged (via the service call), fail-closed on missing/invalid permissions. Ticket
detail responses (`GET /{ticket_id}`) now also include `allowed_workflow_target_states`
(mirrors the existing `allowed_target_states` for the legacy `status` field) for UI button
rendering.

**Schemas** (`app/modules/tickets/schemas.py`): new `WorkflowStatusChangeIn`
(`target_workflow_status: str`); `TicketOut` gained `workflow_status`, `sla_paused_at`,
`sla_paused_total_seconds`; `TicketDetailOut` gained `allowed_workflow_target_states`.

**Audit** (`app/modules/audit/service.py`): new `Action.WORKFLOW_STATUS_CHANGE`, kept
distinct from the existing `Action.STATUS_CHANGE` (which still covers the legacy `status`
field) so audit history/reports can tell the two apart.

**Alembic migration:** `0010_ticket_workflow_status.py` — adds `workflow_status`,
`sla_paused_at`, `sla_paused_total_seconds` to `tickets`. Has a working `downgrade()`. Note:
consistent with Session 1's experience, running the full Alembic chain from scratch against
SQLite fails at migration `0009` (SQLite can't `ALTER TABLE ADD COLUMN` with a `ForeignKey`
constraint without Alembic's batch mode — a pre-existing limitation, not something this
session introduced; `0010`'s own columns carry no FK and would apply cleanly on their own).
Dev/test continues to rely on `Base.metadata.create_all` for SQLite, exactly as `app/main.py`
already documents; the migration file itself is what a real (SQL Server/Postgres) deployment
would run.

**Tests:** `tests/test_workflow_state_machine.py` (pure unit tests for `workflow.py` — state
sets match spec exactly, legal/illegal transitions, ticket-type isolation, terminal states,
mirrors `test_state_machine.py`'s coverage style) and `tests/test_workflow_status.py`
(integration — creation-time initialization, legal/illegal transitions through the service
and HTTP layer, permission enforcement incl. an HTTP 403 case, SLA pause-clock start/stop/
accumulate across multiple pauses and across reclassification, audit logging, rate-limit
decorator presence). 36 new tests, all passing.

**Verified this session:** all 67 backend tests pass (31 pre-existing + 36 new, zero
modified); `create_app()` boots; `/openapi.json` confirms
`POST /api/v1/tickets/{ticket_id}/workflow-status` is registered.

### Deliberate scope decisions (read before continuing §4+)

1. **The transition graph is this session's design call, not literally specified.** SPEC §3
   gives the two state _lists_ and the pause-clock rule, but no transition diagram. This
   session's graph (documented in `workflow.py`'s module docstring): `PROGRESSING` is the hub
   state; `ON_HOLD`/`PEND_3RDPARTY`/`PEND_USER` are all resumable back to `PROGRESSING`; the
   approval state (`APPROVED` for Incidents, `IN_APPROVAL` for Service Requests) sits between
   `PROGRESSING` and the terminal state; the terminal state (`RESOLVED`/`FULFILLED`) is
   reachable from `PROGRESSING`, the approval state, and both pause states, but **not**
   directly from `ON_HOLD`(an administrative hold — resume first, deliberately, so a ticket
   can't be silently closed out from an on-hold state without an engineer explicitly resuming
   it). A `RESOLVED`/`FULFILLED` → `PROGRESSING` reopen event exists, mirroring the existing
   `state_machine.py`'s `RESOLVED → IN_PROGRESS` reopen decision (30-Jun-2026). If product
   feedback disagrees with any of this, it's a one-file change (`workflow.py`'s two
   `_..._TRANSITIONS` dicts) with no model/migration impact.
2. **`workflow_status` is additive, not a replacement for `status`.** The two fields serve
   different purposes and both stay: `status` (generic OPEN/ASSIGNED/IN_PROGRESS/
   PENDING_USER/RESOLVED/CLOSED/CANCELLED) still drives ticket visibility rules, attachment
   upload eligibility, cancellation, and the SLA scanner's "is this ticket terminal" check —
   none of that was touched. `workflow_status` is the new, finer-grained, ITIL-flavoured
   status SPEC §3 asks for. Wiring the frontend (Queue/TicketDetail/AdminTicket) to actually
   _show and drive_ `workflow_status`, and deciding whether it should eventually retire
   `status` for INCIDENT/SERVICE_REQUEST tickets, is deferred — same additive-first pattern
   Session 1 used for the category hierarchy vs. the flat `category` enum. No frontend files
   were touched this session.
3. **PROBLEM/CHANGE_REQUEST tickets get no `workflow_status`.** SPEC §3 literally only lists
   state sets for "Incidents" and "Service Requests" — extending a workflow to the other two
   ticket types would be inventing scope the spec doesn't define. `workflow_status` stays
   `NULL` for them; attempting to transition it raises `DomainError`.
4. **SLA pause bookkeeping only, not business-hours SLA computation.** `sla_paused_at`/
   `sla_paused_total_seconds` faithfully implement §3's "clock pauses during PEND_USER/
   PEND_3RDPARTY" as elapsed-wall-clock-seconds bookkeeping. They do **not** feed into
   `sla_due_at`, `Ticket.sla_status`, or the SLA scanner yet — that requires the
   business-hours/timezone engine SPEC §4 explicitly reserves for a later session. §4 can
   consume `sla_paused_total_seconds` directly once it lands.
5. **Reclassification resets `workflow_status` rather than mapping states across types.**
   There's no spec-defined equivalence between e.g. Incident's `APPROVED` and Service
   Request's `IN_APPROVAL` to justify carrying progress over when `reclassify_ticket` changes
   `ticket_type` — it resets to the new type's initial state (`PROGRESSING`, or `NULL` if the
   new type has no §3 workflow) instead. Accumulated `sla_paused_total_seconds` is preserved
   either way, since it's tracked on the ticket record, not the workflow state.
6. **`first_response_at` and the Met/Breached SLA-status fields are untouched.** SPEC §1
   already added these columns; populating them with real logic is explicitly SPEC §4's job,
   not §3's, so this session left them exactly as Session 1 delivered them.
