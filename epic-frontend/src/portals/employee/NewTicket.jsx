import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api/client.js";

const TICKET_TYPES = [
  {
    value: "INCIDENT",
    label: "Incident",
    hint: "An unplanned interruption or degradation of an IT service (e.g. VPN is down, locked out of email, printer offline).",
  },
  {
    value: "SERVICE_REQUEST",
    label: "Service Request",
    hint: "A routine, planned request for new hardware, software, information, or access — nothing is broken (e.g. new laptop, software install, password reset).",
  },
  {
    value: "PROBLEM",
    label: "Problem",
    hint: "Investigation into the root cause behind one or more recurring, related incidents (e.g. the same network drop happening repeatedly).",
  },
  {
    value: "CHANGE_REQUEST",
    label: "Change Request",
    hint: "A formal request for a planned, systemic update to IT infrastructure (e.g. server migration, system upgrade, scheduled patch).",
  },
];
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
const CHANNELS = ["SELF_SERVICE", "EMAIL", "PHONE", "MONITORING_TOOL"];

export default function NewTicket() {
  const nav = useNavigate();
  const [form, setForm] = useState({
    title: "",
    description: "",
    ticket_type: "INCIDENT",
    category: "HARDWARE",
    priority: "MEDIUM",
    channel: "SELF_SERVICE",
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

  const selectedType = TICKET_TYPES.find((t) => t.value === form.ticket_type);

  return (
    <>
      <h2>Create a ticket</h2>
      <form onSubmit={submit} style={{ maxWidth: 640 }}>
        <div className="form-row">
          <label>Ticket type</label>
          <select
            value={form.ticket_type}
            onChange={(e) => setForm({ ...form, ticket_type: e.target.value })}
          >
            {TICKET_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
          {selectedType && (
            <p className="muted" style={{ marginTop: 4, fontSize: "0.9em" }}>
              {selectedType.hint}
            </p>
          )}
        </div>
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
          <div style={{ flex: 1 }}>
            <label>Channel</label>
            <select
              value={form.channel}
              onChange={(e) => setForm({ ...form, channel: e.target.value })}
            >
              {CHANNELS.map((c) => (
                <option key={c}>{c}</option>
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
