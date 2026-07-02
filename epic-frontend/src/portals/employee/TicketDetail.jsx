import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../../api/client.js";
import { Status, Priority, TicketType } from "../../components/Badges.jsx";

export default function TicketDetail() {
  const { id } = useParams();
  const [t, setT] = useState(null);
  const [history, setHistory] = useState([]);
  const [comment, setComment] = useState("");
  const [file, setFile] = useState(null);
  const [error, setError] = useState(null);

  async function load() {
    setT(await api.get(`/tickets/${id}`));
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
        {!["CLOSED", "CANCELLED", "RESOLVED"].includes(t.status) && (
          <button className="btn danger secondary" onClick={cancelTicket}>
            Cancel ticket
          </button>
        )}
      </div>

      <div className="card">
        <h3>Details</h3>
        <dl className="kv">
          <dt>Created</dt>
          <dd>{new Date(t.created_at).toLocaleString()}</dd>
          <dt>Updated</dt>
          <dd>{new Date(t.updated_at).toLocaleString()}</dd>
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
        <input type="file" onChange={(e) => setFile(e.target.files[0])} />
        <button
          className="btn"
          onClick={uploadFile}
          disabled={!file}
          style={{ marginLeft: 8 }}
        >
          Upload
        </button>
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
                <td className="muted">
                  {new Date(h.created_at).toLocaleString()}
                </td>
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
