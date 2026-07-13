# EPIC Requirements Spec

## Context

Internal IT ticketing system, not yet in production, replacing an Excel-based process and an
outsourced vendor helpdesk ("Digital Desk"). STRICT UPGRADE required: every capability either
predecessor had must exist here — nothing dropped or simplified away. SECURITY IS
NON-NEGOTIABLE: this holds employee PII across multiple countries (including EU sites).
Every new endpoint must fail closed on permission checks, be rate-limited, and be
audit-logged, consistent with existing patterns in the codebase. No historical data
migration needed.

## 1. Ticket data model

- `location` (required, structured reference) — AUTO-FILLED from the creator's
  `home_location` at creation, but editable/overridable afterward.
- `category`/`subcategory`/`item` — real 3-level hierarchy (not flat enum), seeded from the
  company's IT Service Catalogue (8 towers: Data Center Services, Network, Cyber Security,
  Helpdesk/FMS, Email, Laptop/Desktop, Backup, License Management — each with ~15-25
  services). Cascading select in the UI.
- `channel` (enum: EMAIL, PHONE, MONITORING_TOOL, SELF_SERVICE).
- `device_name`, `device_ip_address`, `device_site_name` — nullable, only for
  MONITORING_TOOL tickets.
- `requestor` vs `created_by` — two distinct people (agent may log on someone's behalf).
- `assignment_group` (required FK, see §2).
- `first_response_at`, `resolved_at` — two independent timestamps.
- `response_sla_status`, `resolution_sla_status` — two independent Met/Breached fields
  (logic implemented in a later phase; just add the fields now).
- `breached_reason` (free text) — required server-side when either SLA status is Breached.
- `vendor_ticket_id`, `is_from_email_mgr` — nullable flags.
- User profile: add `home_location` field.

## 2. Assignment Groups

- First-class `AssignmentGroup` entity, admin-configurable. Seed with: IT Infra - Poland,
  Egypt, Mexico, China, Germany, Philippines, Columbia, Vasind, HO; Network, Wintel, Storage,
  Backup, Unix - Linux, Tools Support, O365, SCCM, Digital Desk Support (18 total).
- Each group is location-bound (regional) or location-independent (global specialist domain).
- Users belong to one or more groups. A ticket belongs to exactly one group.
- Queue view: users see/filter open tickets for their own group(s).
- Vendor user type: distinct from internal employees (legacy pattern: "FMS Egypt" — a queue
  label, not a named person), can belong to a group, gets a restricted default permission set
  (not a hard cap).

## 3. Status/workflow (IMPLEMENT IN A LATER SESSION — fields only if convenient now)

Incidents: PROGRESSING, ON_HOLD, PEND_3RDPARTY, PEND_USER, APPROVED, RESOLVED.
Service Requests: PROGRESSING, ON_HOLD, PEND_3RDPARTY, PEND_USER, IN_APPROVAL, FULFILLED.
Resolution SLA clock pauses during PEND_USER/PEND_3RDPARTY.

## 4. SLA model (IMPLEMENT IN A LATER SESSION)

Independent Response + Resolution clocks, targets by (ticket_type × priority):
P1: 15min/2hr, P2: 30min/4hr, P3: 60min/24hr, P4: 120min/48hr — each with a rolling
adherence-% target (99/98/97/95). MEASURED IN BUSINESS HOURS in the ticket's location's
local timezone (default Mon-Fri 09:00-18:00, no holiday calendar — flagged simplification),
not 24/7 wall-clock. Use a proper timezone library; test DST and weekend boundaries.

## 5. Roles & Permissions (IMPLEMENT IN A LATER SESSION)

Dynamic, DB-backed permission system replacing any fixed-role-enum checks, preserving all
existing authorization behavior. Permission registry (minimum): tickets.view.own,
tickets.view.location, tickets.view.all_locations, tickets.reassign.own_location,
tickets.reassign.any, tickets.escalate, tickets.receive_escalations,
routing.edit_rules.global, roles.create_edit, roles.assign_to_users, audit_log.view,
reports.view.location, reports.view.all_locations, users.manage.location, users.manage.all,
service_requests.approve, catalogue.edit. Built-in roles: Employee, IT Engineer, Regional IT
Lead, Regional IT Manager, HO IT Manager (view+act all locations, NOT role-editing), Global
Head Infra, System Admin (only these two can edit roles — never regional roles, no
exceptions), Vendor/FMS Technician. All roles editable by roles.create_edit holders, custom
roles creatable from the same registry. Self-privilege-escalation must be structurally
impossible — needs automated test proof, not just UI hiding. A Role can be a routing target
(§6) — resolves to a queue of everyone holding it, like the vendor-queue pattern in §2.

## 6. Routing engine (IMPLEMENT IN A LATER SESSION)

`RoutingRule`: ordered, admin-editable, `IF category [+subcategory] [+location] THEN target`
(Assignment Group or Role), first-match-wins, required fallback. Location is primary signal
for general tickets; category-based specialist overrides take precedence for technical
domains (e.g. Windows-server alerts → Wintel regardless of site). Only
routing.edit_rules.global holders may edit rules. Manual reassignment always available as
override. Dedicated monitoring-tool ingestion endpoint (service-token auth, not user
sessions), maps payload to §1 fields, routes through the same engine, rate-limited and
audit-logged.

## 7. Escalation (IMPLEMENT IN A LATER SESSION)

Manual only — no automatic timer-based fallback (deliberate, prevents passive
clock-running-out). tickets.escalate holders escalate to any tickets.receive_escalations
holder, any location/team. Escalating REASSIGNS the ticket (SLA accountability follows
current owner). Response SLA clock not reset by escalation. Notifications reuse the existing
Teams webhook system (sanitize inputs consistent with existing phishing-vector fix).

## 8. Dashboard — 5 views (IMPLEMENT IN A LATER SESSION)

A: Daily Ops Summary (inflow/closure/backlog by group, day-over-day, needs daily snapshot).
B: SLA Compliance (achieved% vs target% by priority × response/resolution, drill-down to
breached tickets + reason).
C: Ageing buckets (<=1/>1/>3/>7/>15/>30 days) by group, split monitoring-tool vs human tickets.
D: Open tickets by group × status.
E: Raw pivot exports (inflow/resolved/open by group, SLA met/breached by priority).
All filterable by group/location/type, respecting location-scoped permissions, backend AND
frontend both required.

## 9. Security requirements (apply throughout every phase)

Preserve all existing hardening (rate limiting, session revocation, attachment validation,
CORS correctness, audit logging, fail-closed auth). New endpoints: rate-limited,
audit-logged, fail-closed on missing/malformed permissions. No cross-location data leakage on
any list/report/export endpoint. PII (requestor, device, location) gated by the same
access-control discipline as existing sensitive fields.

## 10. Out of scope

Technician-availability-aware routing. Automatic timer-based escalation. AI/ML auto-triage.
Historical data migration. Holiday-calendar business hours.
