import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../../api/client.js";
import { Status, Priority, TicketType } from "../../components/Badges.jsx";
import { formatUtcDateTime } from "../../utils/time.js";

const PRIORITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
const TICKET_TYPES = [
  "INCIDENT",
  "SERVICE_REQUEST",
  "PROBLEM",
  "CHANGE_REQUEST",
];
// Only these roles are valid ticket assignees. The API also enforces this server-side
// (never trust the client), but filtering here stops IT staff from accidentally picking
// an employee from an unfiltered list in the first place.
const SUPPORT_ROLES = ["IT_ENGINEER", "IT_MANAGER", "SYSTEM_ADMIN"];

export default function AdminTicket() {
  const { id } = useParams();
  const [t, setT] = useState(null);
  const [history, setHistory] = useState([]);
  const [engineers, setEngineers] = useState([]);
  const [assigneeId, setAssigneeId] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState(null);

  async function load() {
    setT(await api.get(`/tickets/${id}`));
    setHistory(await api.get(`/audit/tickets/${id}`));
    try {
      // /users/support-staff (not /users) — open to any IT_ENGINEER/IT_MANAGER/SYSTEM_ADMIN,
      // not just SYSTEM_ADMIN, so the assign dropdown actually works for plain engineers too.
      setEngineers(await api.get("/users/support-staff"));
    } catch (_) {
      /* shouldn't happen for any signed-in IT staff member, but fail quiet either way */
    }
  }
  useEffect(() => {
    load();
  }, [id]);

  async function assign() {
    if (!assigneeId) return;
    try {
      await api.post(`/tickets/${id}/assign`, { assignee_id: assigneeId });
      load();
    } catch (e) {
      setError(e.message);
    }
  }
  async function changeStatus(target) {
    try {
      await api.post(`/tickets/${id}/status`, { target_status: target });
      load();
    } catch (e) {
      setError(e.message);
    }
  }
  async function changePriority(p) {
    try {
      await api.post(`/tickets/${id}/priority`, { priority: p });
      load();
    } catch (e) {
      setError(e.message);
    }
  }
  async function reclassify(type) {
    try {
      await api.post(`/tickets/${id}/reclassify`, { ticket_type: type });
      load();
    } catch (e) {
      setError(e.message);
    }
  }
  async function postComment() {
    if (!comment.trim()) return;
    try {
      await api.post(`/tickets/${id}/comments`, { text: comment });
      setComment("");
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  if (!t) return <p>Loading…</p>;
  const isTerminal = (t.allowed_target_states || []).length === 0;
  return (
    <>
      <h2>
        {t.ticket_number} — {t.title}
      </h2>
      <div className="toolbar">
        <TicketType value={t.ticket_type} /> <Status value={t.status} />{" "}
        <Priority value={t.priority} />{" "}
        <span className="muted">{t.category}</span>
      </div>

      <div className="card">
        <h3>Engineer actions</h3>
        <div
          className="form-row"
          style={{ display: "flex", gap: 8, alignItems: "end" }}
        >
          <div style={{ flex: 1 }}>
            <label>Assign to</label>
            <select
              value={assigneeId}
              onChange={(e) => setAssigneeId(e.target.value)}
              disabled={isTerminal}
            >
              <option value="">— Choose user —</option>
              {engineers.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.display_name} ({u.email})
                </option>
              ))}
            </select>
          </div>
          <button className="btn" onClick={assign} disabled={isTerminal}>
            Assign
          </button>
        </div>

        <div
          className="form-row"
          style={{ display: "flex", gap: 8, alignItems: "end" }}
        >
          <div style={{ flex: 1 }}>
            <label>Change priority</label>
            <select
              value={t.priority}
              onChange={(e) => changePriority(e.target.value)}
              disabled={isTerminal}
            >
              {PRIORITIES.map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label>Reclassify type</label>
            <select
              value={t.ticket_type}
              onChange={(e) => reclassify(e.target.value)}
              disabled={isTerminal}
            >
              {TICKET_TYPES.map((ty) => (
                <option key={ty} value={ty}>
                  {ty.replace("_", " ")}
                </option>
              ))}
            </select>
          </div>
        </div>
        {isTerminal && (
          <p className="muted" style={{ marginTop: 8 }}>
            Terminal state — assignment, priority, and type are locked.
          </p>
        )}

        <div className="form-row">
          <label>Move to status</label>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {(t.allowed_target_states || []).map((s) => (
              <button
                key={s}
                className="btn secondary"
                onClick={() => changeStatus(s)}
              >
                {s.replace("_", " ")}
              </button>
            ))}
            {(t.allowed_target_states || []).length === 0 && (
              <span className="muted">
                Terminal state — no further transitions available.
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        <h3>Details</h3>
        <dl className="kv">
          <dt>Creator</dt>
          <dd>
            {t.creator?.display_name} ({t.creator?.email})
          </dd>
          <dt>Assignee</dt>
          <dd>
            {t.assignee?.display_name || (
              <span className="muted">Unassigned</span>
            )}
          </dd>
          <dt>Created</dt>
          <dd>{formatUtcDateTime(t.created_at)}</dd>
          <dt>Updated</dt>
          <dd>{formatUtcDateTime(t.updated_at)}</dd>
        </dl>
        <p style={{ whiteSpace: "pre-wrap", marginTop: 12 }}>{t.description}</p>
      </div>

      <div className="card">
        <h3>Comments</h3>
        {(t.comments || []).map((c) => (
          <div key={c.id} className="comment">
            <div className="muted">
              {c.author?.display_name || "Unknown"} ·{" "}
              {formatUtcDateTime(c.created_at)}
            </div>
            <div>{c.text}</div>
          </div>
        ))}
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Add a comment…"
        />
        <button className="btn" onClick={postComment} style={{ marginTop: 8 }}>
          Post comment
        </button>
      </div>

      <div className="card">
        <h3>Attachments</h3>
        <ul>
          {(t.attachments || []).map((a) => (
            <li key={a.id}>
              <a href={`/api/v1/tickets/${t.id}/attachments/${a.id}/download`}>
                {a.file_name}
              </a>
              <span className="muted">
                {" "}
                · {(a.size_bytes / 1024).toFixed(1)} KB
              </span>
            </li>
          ))}
        </ul>
        {isTerminal && (
          <p className="muted">
            This ticket is {t.status.toLowerCase()} — new attachments can no
            longer be added. Existing attachments remain available above.
          </p>
        )}
      </div>

      <div className="card">
        <h3>Full audit history</h3>
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Who</th>
              <th>Action</th>
              <th>Field</th>
              <th>From → To</th>
            </tr>
          </thead>
          <tbody>
            {history.map((h) => (
              <tr key={h.id}>
                <td className="muted">{formatUtcDateTime(h.created_at)}</td>
                <td>{h.actor_name || "System"}</td>
                <td>{h.action}</td>
                <td>{h.field || ""}</td>
                <td>
                  {h.old_value
                    ? `${h.old_value} → ${h.new_value || ""}`
                    : h.new_value || ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {error && <div className="error">{error}</div>}
    </>
  );
}
