import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../../api/client.js";
import { Status, Priority, TicketType } from "../../components/Badges.jsx";
import { useAuth, hasRole } from "../../auth/AuthContext.jsx";
import { formatUtcDateTime } from "../../utils/time.js";

export default function TicketDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const [t, setT] = useState(null);
  const [history, setHistory] = useState([]);
  const [comment, setComment] = useState("");
  const [file, setFile] = useState(null);
  const [error, setError] = useState(null);
  const [forbidden, setForbidden] = useState(false);
  const isEngineer = hasRole(user, "IT_ENGINEER", "IT_MANAGER", "SYSTEM_ADMIN");
  const isTerminal = t
    ? ["CLOSED", "CANCELLED", "RESOLVED"].includes(t.status)
    : false;

  async function load() {
    const ticket = await api.get(`/tickets/${id}`);
    if (
      isEngineer &&
      user?.id &&
      ticket.creator?.id &&
      ticket.creator.id !== user.id
    ) {
      setForbidden(true);
      setT(null);
      setHistory([]);
      return;
    }
    setForbidden(false);
    setT(ticket);
    setHistory(await api.get(`/audit/tickets/${id}`));
  }
  useEffect(() => {
    load();
  }, [id]);

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

  async function uploadFile() {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      await api.postForm(`/tickets/${id}/attachments`, fd);
      setFile(null);
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  async function cancelTicket() {
    if (!confirm("Cancel this ticket?")) return;
    try {
      await api.post(`/tickets/${id}/cancel`, {});
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  if (forbidden) {
    return (
      <div className="content">
        <h2>403 — Not authorized</h2>
        <p>Employee portal tickets are limited to your own submissions.</p>
      </div>
    );
  }

  if (!t) return <p>Loading…</p>;
  return (
    <>
      <h2>
        {t.ticket_number} — {t.title}
      </h2>
      <div className="toolbar">
        <TicketType value={t.ticket_type} /> <Status value={t.status} />{" "}
        <Priority value={t.priority} />
        <span className="muted">{t.category}</span>
        {!isTerminal && (
          <button className="btn danger secondary" onClick={cancelTicket}>
            Cancel ticket
          </button>
        )}
      </div>

      <div className="card">
        <h3>Details</h3>
        <dl className="kv">
          <dt>Created</dt>
          <dd>{formatUtcDateTime(t.created_at)}</dd>
          <dt>Updated</dt>
          <dd>{formatUtcDateTime(t.updated_at)}</dd>
          <dt>Assignee</dt>
          <dd>
            {t.assignee?.display_name || (
              <span className="muted">Unassigned</span>
            )}
          </dd>
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
        <input
          type="file"
          onChange={(e) => setFile(e.target.files[0])}
          disabled={isTerminal}
        />
        <button
          className="btn"
          onClick={uploadFile}
          disabled={!file || isTerminal}
          style={{ marginLeft: 8 }}
        >
          Upload
        </button>
        {isTerminal && (
          <p className="muted" style={{ marginTop: 8 }}>
            This ticket is {t.status.toLowerCase()} — attachments are read-only.
          </p>
        )}
      </div>

      <div className="card">
        <h3>History</h3>
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
