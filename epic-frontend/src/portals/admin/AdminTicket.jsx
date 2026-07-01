import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../../api/client.js";
import { Status, Priority } from "../../components/Badges.jsx";

const PRIORITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

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
      setEngineers(await api.get("/users"));
    } catch (_) {
      /* not admin */
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
  return (
    <>
      <h2>
        {t.ticket_number} — {t.title}
      </h2>
      <div className="toolbar">
        <Status value={t.status} /> <Priority value={t.priority} />{" "}
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
            >
              <option value="">— Choose user —</option>
              {engineers.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.display_name} ({u.email})
                </option>
              ))}
            </select>
          </div>
          <button className="btn" onClick={assign}>
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
            >
              {PRIORITIES.map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </div>
        </div>

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
          <dd>{new Date(t.created_at).toLocaleString()}</dd>
          <dt>Updated</dt>
          <dd>{new Date(t.updated_at).toLocaleString()}</dd>
        </dl>
        <p style={{ whiteSpace: "pre-wrap", marginTop: 12 }}>{t.description}</p>
      </div>

      <div className="card">
        <h3>Comments</h3>
        {(t.comments || []).map((c) => (
          <div key={c.id} className="comment">
            <div className="muted">
              {c.author?.display_name || "Unknown"} ·{" "}
              {new Date(c.created_at).toLocaleString()}
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
      </div>

      <div className="card">
        <h3>Full audit history</h3>
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Action</th>
              <th>Field</th>
              <th>From → To</th>
            </tr>
          </thead>
          <tbody>
            {history.map((h) => (
              <tr key={h.id}>
                <td className="muted">
                  {new Date(h.created_at).toLocaleString()}
                </td>
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
