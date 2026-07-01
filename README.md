# EPIC v1 — Enterprise Platform for Intelligent IT Collaboration

EPL Limited's enterprise IT ticketing platform. This is **Version 1** per SRS v2.0.

> **Scope reminder:** Authentication, User Management, Ticket Management, Knowledge Base
> (read-only), Microsoft Teams notifications, Dashboard & Reporting, Search & Filtering, and
> Audit Logging. No AI Assistant, no chatbot, no QRadar / Fortinet / ManageEngine / Check Point
> integrations — those are explicitly v2 (SRS Chapter 7) and are present here only as empty,
> labeled extension points.

## Repository layout

```
epic/
├── epic-backend/          FastAPI backend (8 modules, 1:1 with SRS)
├── epic-frontend/         React (Vite) — Employee + Admin portals in one app
├── epic-teams-app/        Teams app package (manifest + icons + zip)
├── docs/                  TEAMS_TESTING.md, GAP_LIST.md, ARCHITECTURE.md
└── README.md              this file
```

## Prerequisites

| Tool                          | Version                                                     |
| ----------------------------- | ----------------------------------------------------------- |
| Python                        | 3.11+                                                       |
| Node.js                       | 20+                                                         |
| MS SQL Server                 | for production — dev defaults to SQLite (no install needed) |
| ODBC Driver 18 for SQL Server | when switching to MS SQL                                    |

## Local setup — backend

```bash
cd epic-backend
python -m venv .venv && source .venv/bin/activate    # or .venv\Scripts\activate on Windows
pip install -e .
cp .env.example .env                                 # edit if needed
python scripts/seed_demo.py                          # optional: a few demo users + a ticket
uvicorn app.main:app --reload --port 8000cd
```

OpenAPI docs: <http://localhost:8000/docs>

### Switching to MS SQL Server (production)

Edit `.env`:

```
DATABASE_URL=mssql+pyodbc://EPIC_APP:CHANGE_ME@sqlhost:1433/EPIC?driver=ODBC+Driver+18+for+SQL+Server
```

Then run migrations: `alembic upgrade head`.

> **Recommended SQL grant for the app account:**
> `SELECT, INSERT, UPDATE, DELETE` on most tables, but only `SELECT, INSERT` on
> `ticket_audit_logs` — defense in depth for REQ-4.8-8 (immutable audit log).

## Local setup — frontend

```bash
cd epic-frontend
npm install
npm run dev          # serves on http://localhost:5173, proxies /api to backend
```

Open <http://localhost:5173>. With the default mock auth provider, click "Sign in with Microsoft" and the form will let you "sign in" as any email. Seed script creates:

| Email                      | Roles                              |
| -------------------------- | ---------------------------------- |
| `bob.employee@epl.local`   | EMPLOYEE                           |
| `alice.engineer@epl.local` | EMPLOYEE, IT_ENGINEER              |
| `cara.admin@epl.local`     | EMPLOYEE, IT_MANAGER, SYSTEM_ADMIN |

## Switching to Microsoft Entra ID (production auth)

In `epic-backend/.env`:

```
AUTH_PROVIDER=entra
ENTRA_TENANT_ID=<your-tenant>
ENTRA_CLIENT_ID=<your-app>
ENTRA_CLIENT_SECRET=<secret>
ENTRA_REDIRECT_URI=https://epic.epl.local/api/v1/auth/callback
```

MFA via Microsoft Authenticator is enforced at the Entra tenant Conditional Access policy level — the app does not implement a parallel MFA flow.

## Running tests

```bash
cd epic-backend
pip install -e .[dev]
pytest -v
```

Includes a state-machine test that locks in SRS Figure 5 + the agreed Resolved → In Progress reopen transition.

## Teams app

The pre-built Teams app package is at `epic-teams-app/epic-teams-app.zip`. **Full step-by-step testing instructions are in [`docs/TEAMS_TESTING.md`](docs/TEAMS_TESTING.md).**

## Architecture & decisions

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — module map, state machine, data model, and rationale for the future-proofing pattern.

## Known gaps / TODOs

See [`docs/GAP_LIST.md`](docs/GAP_LIST.md).
