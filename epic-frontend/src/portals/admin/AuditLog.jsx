import React, { useEffect, useState } from "react";
import { api } from "../../api/client.js";
import { formatUtcDateTime } from "../../utils/time.js";

export default function AuditLog() {
  const [entries, setEntries] = useState([]);
  const [error, setError] = useState(null);

  async function load() {
    try {
      setError(null);
      setEntries(await api.get("/audit"));
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  if (error) {
    return <div className="error">Cannot load audit log: {error}</div>;
  }

  return (
    <>
      <h2>Audit log</h2>
      <p className="muted" style={{ marginTop: -8 }}>
        Recent security and ticket history events.
      </p>
      <table>
        <thead>
          <tr>
            <th>When</th>
            <th>Actor</th>
            <th>Action</th>
            <th>Ticket</th>
            <th>Field</th>
            <th>From → To</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.id}>
              <td className="muted">{formatUtcDateTime(entry.created_at)}</td>
              <td>
                {entry.actor_name || "System"}
                {entry.actor_email ? (
                  <div className="muted">{entry.actor_email}</div>
                ) : null}
              </td>
              <td>{entry.action}</td>
              <td>{entry.ticket_id || "—"}</td>
              <td>{entry.field || ""}</td>
              <td>
                {entry.old_value
                  ? `${entry.old_value} → ${entry.new_value || ""}`
                  : entry.new_value || ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {entries.length === 0 && <p className="muted">No audit events found.</p>}
    </>
  );
}
