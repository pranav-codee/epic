# EPIC v1 — Known Gaps & TODOs

Things the SRS asks for that this build cannot fully finalise without information from EPL, plus deliberate omissions called out for transparency.

## Configuration placeholders requiring EPL input

| #   | What                                            | Where                                                                                                       | Action                                                                                                                                                                                                                                                                                            |
| --- | ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| G1  | Microsoft Teams Incoming Webhook URL (TBD-3)    | `epic-backend/.env` → `TEAMS_WEBHOOK_URL`                                                                   | EPL IT to create webhook on the agreed channel and supply URL.                                                                                                                                                                                                                                    |
| G2  | Microsoft Entra ID app registration             | `epic-backend/.env` → `ENTRA_*`                                                                             | EPL IT to register the EPIC app, return tenant/client/secret + redirect URI.                                                                                                                                                                                                                      |
| G3  | Teams App ID GUID                               | `epic-teams-app/manifest.json` → `id`, `webApplicationInfo.id`                                              | Replace generated GUID with the Entra/Teams app registration ID.                                                                                                                                                                                                                                  |
| G4  | Production FQDN                                 | `manifest.json` (`contentUrl`, `websiteUrl`, `validDomains`) + `.env` (`APP_BASE_URL`, `FRONTEND_BASE_URL`) | Currently `epic.epl.local`. Replace with real prod hostname.                                                                                                                                                                                                                                      |
| G5  | On-prem MS SQL Server connection string (TBD-1) | `epic-backend/.env` → `DATABASE_URL`                                                                        | Currently SQLite for dev. Switch to `mssql+pyodbc://…` and run `alembic upgrade head`.                                                                                                                                                                                                            |
| G6  | SLA targets per priority (TBD-8)                | `epic-backend/app/core/sla.py`, `sla_scanner.py`, `Ticket.sla_due_at`                                       | Implemented: `sla_due_at` is populated in `create_ticket`, breaches are detected by `sla_scanner.py`, and status is visualised on the admin dashboard. Confirm the per-priority target durations in `sla.py` match EPL's final agreed SLA policy (currently placeholders pending TBD-8 sign-off). |
| G7  | Attachment storage location & retention (TBD-4) | `epic-backend/storage/attachments`                                                                          | Local disk for v1 behind `AttachmentStorage` ABC. Swap for SMB / Azure Blob / S3 by adding a new `AttachmentStorage` impl.                                                                                                                                                                        |
| G8  | Knowledge Base content (TBD-5)                  | DB table `knowledge_base_articles`                                                                          | Empty by default. `scripts/seed_kb.py` ingests `.md` files; EPL to define authoring process.                                                                                                                                                                                                      |
| G9  | Final dashboard visual design (TBD-6)           | `epic-frontend/src/portals/admin/Dashboard.jsx`                                                             | Functional tables only. Charts can be added with any chart library later.                                                                                                                                                                                                                         |
| G10 | Additional languages (TBD-7)                    | UI strings inline                                                                                           | English only in v1. Defer i18n until language list confirmed.                                                                                                                                                                                                                                     |

## Deliberate v1 omissions (out of scope per SRS)

| What                                                         | SRS reference              |
| ------------------------------------------------------------ | -------------------------- |
| AI Assistant / chatbot / conversational interface            | BR-8, REQ-4.4-4, Chapter 7 |
| Microsoft Teams conversational interface for ticket creation | Chapter 7                  |
| QRadar, Fortinet, ManageEngine, Check Point integrations     | BR-8, Chapter 7            |
| Automatic / intelligent ticket routing                       | REQ-4.3-14                 |
| In-app Knowledge Base authoring UI                           | REQ-4.4-3                  |
| Notification channels other than Microsoft Teams             | BR-6, REQ-4.5-6            |

These are present **only** as labeled empty extension points (`app/services/ai/`, `app/services/integrations/`) per your instruction.

## Decisions captured during build (30-Jun-2026)

| Decision                                                                                     | Source                                         |
| -------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| Reopen transition RESOLVED → IN_PROGRESS allowed                                             | User directive (overrides strict SRS Figure 5) |
| Update notification fires on status / priority / assignment / comment; **not** on attachment | User directive                                 |
| Local dev uses SQLite; production uses on-prem MS SQL Server                                 | User directive                                 |
| Mock identity provider for local dev, real Entra ID in prod, both behind same ABC            | User directive (A4)                            |
| Teams app = Tabs only, one app, scopes `personal/team/groupChat`                             | User directive (A1–A3)                         |
| Auth = Microsoft Authenticator via Entra OIDC (no Teams SSO in v1)                           | User directive (A4)                            |
| Notification mechanism = Incoming Webhook (no Bot Framework)                                 | User directive (C1)                            |
| Icons = generated placeholders                                                               | User directive (E3)                            |
| Random GUID for Teams App ID, replace at registration time                                   | User directive (E4)                            |

## Things to verify before pilot rollout

1. Replace all `epic.epl.local` placeholders with the real FQDN.
2. Replace the Teams App GUID.
3. Provision and configure Entra ID app registration; set `AUTH_PROVIDER=entra`.
4. Provision MS SQL DB + ODBC driver; run `alembic upgrade head`.
5. Create Teams Incoming Webhook; set `TEAMS_WEBHOOK_URL`.
6. Set `SESSION_SECRET` to a real random 32-byte secret.
7. Set `APP_ENV=prod` so the session cookie is marked Secure.
8. Set `BOOTSTRAP_ADMIN_EMAILS` so the first sign-in by an admin user gets `SYSTEM_ADMIN` automatically; subsequent role changes via Admin → Users.
9. Run `pytest` and confirm state-machine tests pass.
10. Walk through `docs/TEAMS_TESTING.md` end-to-end.
