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
export const Sla = ({ value }) => (
  <span className={`badge sla-${value}`}>{SLA_LABELS[value] || value}</span>
);
