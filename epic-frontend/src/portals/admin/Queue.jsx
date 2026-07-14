import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client.js";
import {
  Status,
  Priority,
  TicketType,
  WorkflowStatus,
} from "../../components/Badges.jsx";
import { formatUtcDateTime } from "../../utils/time.js";

export default function Queue() {
  const [tickets, setTickets] = useState([]);
  const [filters, setFilters] = useState({
    ticket_number: "",
    status: "",
    ticket_type: "",
    category: "",
    priority: "",
    q: "",
  });
  const [total, setTotal] = useState(0);

  async function load() {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => v && params.set(k, v));
    const r = await api.get("/search/tickets?" + params.toString());
    setTickets(r.results);
    setTotal(r.total);
  }
  useEffect(() => {
    load();
  }, []);

  return (
    <>
      <h2>Ticket queue ({total})</h2>
      <div className="toolbar">
        <input
          placeholder="Ticket #"
          value={filters.ticket_number}
          onChange={(e) =>
            setFilters({ ...filters, ticket_number: e.target.value })
          }
          style={{ width: 140 }}
        />
        <input
          placeholder="Search…"
          value={filters.q}
          onChange={(e) => setFilters({ ...filters, q: e.target.value })}
          style={{ width: 220 }}
        />
        <select
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
        >
          <option value="">All statuses</option>
          {[
            "OPEN",
            "ASSIGNED",
            "IN_PROGRESS",
            "PENDING_USER",
            "RESOLVED",
            "CLOSED",
            "CANCELLED",
          ].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
        <select
          value={filters.ticket_type}
          onChange={(e) =>
            setFilters({ ...filters, ticket_type: e.target.value })
          }
        >
          <option value="">All types</option>
          {["INCIDENT", "SERVICE_REQUEST", "PROBLEM", "CHANGE_REQUEST"].map(
            (t) => (
              <option key={t} value={t}>
                {t.replace("_", " ")}
              </option>
            ),
          )}
        </select>
        <select
          value={filters.category}
          onChange={(e) => setFilters({ ...filters, category: e.target.value })}
        >
          <option value="">All categories</option>
          {[
            "HARDWARE",
            "SOFTWARE",
            "NETWORK",
            "VPN",
            "EMAIL",
            "SECURITY",
            "ACCESS",
            "APPLICATION",
            "OTHER",
          ].map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
        <select
          value={filters.priority}
          onChange={(e) => setFilters({ ...filters, priority: e.target.value })}
        >
          <option value="">All priorities</option>
          {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((p) => (
            <option key={p}>{p}</option>
          ))}
        </select>
        <button className="btn" onClick={load}>
          Apply
        </button>
      </div>

      <table>
        <thead>
          <tr>
            <th>Ticket #</th>
            <th>Title</th>
            <th>Type</th>
            <th>Creator</th>
            <th>Requestor</th>
            <th>Assignee</th>
            <th>Status</th>
            <th>Workflow status</th>
            <th>Priority</th>
            <th>Category</th>
            <th>Created</th>
            <th>Last updated</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((t) => (
            <tr key={t.id}>
              <td>
                <Link to={`/admin/tickets/${t.id}`}>{t.ticket_number}</Link>
              </td>
              <td>{t.title}</td>
              <td>
                <TicketType value={t.ticket_type} />
              </td>
              <td>{t.creator?.display_name || "—"}</td>
              <td>{t.requestor?.display_name || "—"}</td>
              <td>
                {t.assignee?.display_name || (
                  <span className="muted">Unassigned</span>
                )}
              </td>
              <td>
                <Status value={t.status} />
              </td>
              <td>
                {t.workflow_status ? (
                  <WorkflowStatus value={t.workflow_status} />
                ) : (
                  <span className="muted">—</span>
                )}
              </td>
              <td>
                <Priority value={t.priority} />
              </td>
              <td>{t.category}</td>
              <td className="muted">{formatUtcDateTime(t.created_at)}</td>
              <td className="muted">{formatUtcDateTime(t.updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
