import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client.js";
import { Status, Priority, TicketType } from "../../components/Badges.jsx";
import { formatUtcDateTime } from "../../utils/time.js";

export default function MyTickets() {
  const [tickets, setTickets] = useState([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");

  async function load() {
    const rows = await api.get("/tickets");
    const filtered = (rows || []).filter((ticket) => {
      if (status && ticket.status !== status) return false;
      if (!q) return true;
      const needle = q.toLowerCase();
      return [
        ticket.ticket_number,
        ticket.title,
        ticket.description,
        ticket.category,
      ]
        .filter(Boolean)
        .some((value) => value.toLowerCase().includes(needle));
    });
    setTickets(filtered);
  }
  useEffect(() => {
    load();
  }, []);

  return (
    <>
      <h2>My tickets</h2>
      <div className="toolbar">
        <input
          type="text"
          placeholder="Search title or description…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ maxWidth: 320 }}
        />
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          style={{ width: 180 }}
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
        <button className="btn" onClick={load}>
          Search
        </button>
      </div>
      <table>
        <thead>
          <tr>
            <th>Ticket #</th>
            <th>Title</th>
            <th>Type</th>
            <th>Status</th>
            <th>Priority</th>
            <th>Category</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((t) => (
            <tr key={t.id}>
              <td>
                <Link to={`/employee/tickets/${t.id}`}>{t.ticket_number}</Link>
              </td>
              <td>{t.title}</td>
              <td>
                <TicketType value={t.ticket_type} />
              </td>
              <td>
                <Status value={t.status} />
              </td>
              <td>
                <Priority value={t.priority} />
              </td>
              <td>{t.category}</td>
              <td className="muted">{formatUtcDateTime(t.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {tickets.length === 0 && <p className="muted">No tickets found.</p>}
    </>
  );
}
