import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api/client.js";

const CATEGORIES = [
  "HARDWARE",
  "SOFTWARE",
  "NETWORK",
  "VPN",
  "EMAIL",
  "SECURITY",
  "ACCESS",
  "APPLICATION",
  "OTHER",
];
const PRIORITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

export default function NewTicket() {
  const nav = useNavigate();
  const [form, setForm] = useState({
    title: "",
    description: "",
    category: "HARDWARE",
    priority: "MEDIUM",
  });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const t = await api.post("/tickets", form);
      nav(`/employee/tickets/${t.id}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h2>Create a ticket</h2>
      <form onSubmit={submit} style={{ maxWidth: 640 }}>
        <div className="form-row">
          <label>Title</label>
          <input
            type="text"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            required
          />
        </div>
        <div className="form-row">
          <label>Describe the problem</label>
          <textarea
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            required
          />
        </div>
        <div className="form-row" style={{ display: "flex", gap: 12 }}>
          <div style={{ flex: 1 }}>
            <label>Category</label>
            <select
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
            >
              {CATEGORIES.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label>Priority</label>
            <select
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value })}
            >
              {PRIORITIES.map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </div>
        </div>
        {error && <div className="error">{error}</div>}
        <button className="btn" disabled={busy}>
          {busy ? "Submitting…" : "Submit ticket"}
        </button>
      </form>
    </>
  );
}
