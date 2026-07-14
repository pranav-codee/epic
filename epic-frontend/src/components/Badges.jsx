import React from "react";
export const Status = ({ value }) => (
  <span className={`badge s-${value}`}>{value.replace("_", " ")}</span>
);
export const Priority = ({ value }) => (
  <span className={`badge p-${value}`}>{value}</span>
);
export const TicketType = ({ value }) => (
  <span className={`badge t-${value}`}>{(value || "").replace("_", " ")}</span>
);
// SLA status badge — mirrors the same MET/BREACHED/AT_RISK/ON_TRACK/NONE values that
// app.core.sla.sla_status() computes server-side (see Ticket.sla_status property).
const SLA_LABELS = {
  NONE: "No SLA",
  ON_TRACK: "On track",
  AT_RISK: "At risk",
  BREACHED: "Breached",
  MET: "Met",
};
export const Sla = ({ value, label }) => (
  <span className={`badge sla-${value || "NONE"}`}>
    {label ? `${label}: ` : ""}
    {value ? SLA_LABELS[value] || value : "—"}
  </span>
);
// Workflow-status badge — SPEC §3's ticket-type-specific workflow, distinct from the
// legacy generic `status` field the Status badge above renders. NULL for ticket types
// with no §3 workflow (PROBLEM/CHANGE_REQUEST), so this renders nothing in that case.
export const WorkflowStatus = ({ value }) =>
  value ? (
    <span className={`badge w-${value}`}>{value.replace("_", " ")}</span>
  ) : null;
