import React, { useEffect, useState } from "react";
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
const PRIORITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
const CHANNELS = ["SELF_SERVICE", "EMAIL", "PHONE", "MONITORING_TOOL"];
// The backend's flat `category` field (tickets/models.py CATEGORIES) is still required
// server-side and predates the 3-level catalogue hierarchy below. There's no clean 1:1
// mapping from a Tower (e.g. "Data Center Services") to a flat category (e.g.
// "HARDWARE"), so once the cascading catalogue select is used we submit this generic
// bucket value alongside the richer category_id/subcategory_id/item_id fields, rather
// than asking the user to also pick a flat category that no longer drives the UI.
const LEGACY_CATEGORY_FALLBACK = "OTHER";

export default function NewTicket() {
  const nav = useNavigate();
  const [form, setForm] = useState({
    title: "",
    description: "",
    ticket_type: "INCIDENT",
    category: LEGACY_CATEGORY_FALLBACK,
    priority: "MEDIUM",
    channel: "SELF_SERVICE",
  });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [assignmentGroups, setAssignmentGroups] = useState([]);
  const [catalogueTree, setCatalogueTree] = useState([]);

  useEffect(() => {
    api
      .get("/catalogue/assignment-groups")
      .then((groups) => setAssignmentGroups(groups))
      .catch(() => setAssignmentGroups([]));
    api
      .get("/catalogue/tree")
      .then((tree) => setCatalogueTree(tree))
      .catch(() => setCatalogueTree([]));
  }, []);

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
  const selectedCategory = catalogueTree.find((c) => c.id === form.category_id);
  const selectedSubcategory = selectedCategory?.subcategories.find(
    (s) => s.id === form.subcategory_id,
  );

  function onTowerChange(categoryId) {
    setForm({
      ...form,
      category_id: categoryId || undefined,
      subcategory_id: undefined,
      item_id: undefined,
    });
  }

  function onServiceChange(subcategoryId) {
    setForm({
      ...form,
      subcategory_id: subcategoryId || undefined,
      item_id: undefined,
    });
  }

  function onItemChange(itemId) {
    setForm({ ...form, item_id: itemId || undefined });
  }

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
        <div className="form-row">
          <label>What is this about?</label>
          <div style={{ display: "flex", gap: 12 }}>
            <div style={{ flex: 1 }}>
              <label className="muted" style={{ fontSize: "0.85em" }}>
                Tower
              </label>
              <select
                value={form.category_id || ""}
                onChange={(e) => onTowerChange(e.target.value)}
              >
                <option value="">Select a tower…</option>
                {catalogueTree.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label className="muted" style={{ fontSize: "0.85em" }}>
                Service
              </label>
              <select
                value={form.subcategory_id || ""}
                onChange={(e) => onServiceChange(e.target.value)}
                disabled={!selectedCategory}
              >
                <option value="">
                  {selectedCategory
                    ? "Select a service…"
                    : "Select a tower first"}
                </option>
                {selectedCategory?.subcategories.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label className="muted" style={{ fontSize: "0.85em" }}>
                Item
              </label>
              <select
                value={form.item_id || ""}
                onChange={(e) => onItemChange(e.target.value)}
                disabled={!selectedSubcategory}
              >
                <option value="">
                  {selectedSubcategory
                    ? "Select an item…"
                    : "Select a service first"}
                </option>
                {selectedSubcategory?.items.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
        <div className="form-row" style={{ display: "flex", gap: 12 }}>
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
        <div className="form-row">
          <label>Assignment group (optional)</label>
          <select
            value={form.assignment_group_id || ""}
            onChange={(e) =>
              setForm({
                ...form,
                assignment_group_id: e.target.value || undefined,
              })
            }
          >
            <option value="">No group / auto-assign later</option>
            {assignmentGroups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </div>
        {error && <div className="error">{error}</div>}
        <button className="btn" disabled={busy}>
          {busy ? "Submitting…" : "Submit ticket"}
        </button>
      </form>
    </>
  );
}
