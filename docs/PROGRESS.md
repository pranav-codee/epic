# EPIC — Spec Implementation Progress

Tracks /SPEC.md sections. Status is one of NOT STARTED / IN PROGRESS / DONE.
Each future session should read this file first, then SPEC.md, before writing code.

| §   | Title                         | Status             | Note                                                                                                                                                                                                                                                               |
| --- | ----------------------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | Ticket data model             | DONE (foundations) | See "Session 1" below for what's additive-only vs. fully wired.                                                                                                                                                                                                    |
| 2   | Assignment Groups             | DONE (foundations) | Model + seed data + read endpoints done. Admin CRUD deferred to §5 session.                                                                                                                                                                                        |
| 3   | Status/workflow               | NOT STARTED        | Existing STATUSES enum (OPEN/ASSIGNED/IN_PROGRESS/PENDING_USER/RESOLVED/CLOSED/CANCELLED) and state_machine.py are untouched — spec's INCIDENT/SERVICE_REQUEST-specific state sets (PROGRESSING/ON_HOLD/PEND_3RDPARTY/.../APPROVED/FULFILLED) are not yet modeled. |
| 4   | SLA model (business-hours)    | NOT STARTED        | Current SLA logic (core/sla.py, sla_scanner.py) is 24/7 wall-clock, keyed by priority only (not ticket_type × priority). Business-hours/timezone-aware calendar not started. `Location.timezone` (added this session) is there to support it.                      |
| 5   | Roles & Permissions (dynamic) | NOT STARTED        | Still on the fixed Role enum in core/rbac.py (EMPLOYEE/IT_ENGINEER/IT_MANAGER/SYSTEM_ADMIN). No DB-backed permission registry, no custom roles, no Vendor/FMS Technician _role_ (only the UserProfile.user_type=VENDOR foundation column exists — see §2 note).    |
| 6   | Routing engine                | NOT STARTED        | No RoutingRule model/table. Tickets can carry an assignment_group_id (nullable) but nothing auto-assigns it yet — assignment_group_id is set to NULL unless a caller passes it explicitly. No monitoring-tool ingestion endpoint.                                  |
| 7   | Escalation                    | NOT STARTED        | No change beyond existing SLA-scanner _notifications_ (which are informational, not reassignment).                                                                                                                                                                 |
| 8   | Dashboard — 5 views           | NOT STARTED        | Existing reporting module (app/modules/reporting) predates this spec; not evaluated against the 5-view list yet.                                                                                                                                                   |
| 9   | Security requirements         | ONGOING            | Applied within scope of what was touched this session (see notes below); no new gaps knowingly introduced. Full review against §9 should happen again once §5/§6 add real authorization surface.                                                                   |
| 10  | Out of scope                  | N/A                | Reference only — nothing to implement.                                                                                                                                                                                                                             |

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
actually required, since routing is what guarantees every ticket gets one). §3/§4 depend on
neither and could also be picked up independently.
