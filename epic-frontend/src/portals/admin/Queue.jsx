import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client.js";
import { Status, Priority } from "../../components/Badges.jsx";

export default function Queue() {
  const [tickets, setTickets] = useState([]);
  const [filters, setFilters] = useState({
    ticket_number: "",
    status: "",
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
            <th>Creator</th>
            <th>Assignee</th>
            <th>Status</th>
            <th>Priority</th>
            <th>Category</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((t) => (
            <tr key={t.id}>
              <td>
                <Link to={`/admin/tickets/${t.id}`}>{t.ticket_number}</Link>
              </td>
              <td>{t.title}</td>
              <td>{t.creator?.display_name || "—"}</td>
              <td>
                {t.assignee?.display_name || (
                  <span className="muted">Unassigned</span>
                )}
              </td>
              <td>
                <Status value={t.status} />
              </td>
              <td>
                <Priority value={t.priority} />
              </td>
              <td>{t.category}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
