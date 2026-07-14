import React, { useEffect, useState, useCallback } from "react";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import { api } from "../../api/client.js";

const STATUS_COLORS = {
  OPEN: "#0067b8",
  ASSIGNED: "#b7791f",
  IN_PROGRESS: "#2b6cb0",
  PENDING_USER: "#6941c6",
  RESOLVED: "#067647",
  CLOSED: "#8a94a6",
  CANCELLED: "#b42318",
};
const PRIORITY_COLORS = {
  CRITICAL: "#b42318",
  HIGH: "#b54708",
  MEDIUM: "#6941c6",
  LOW: "#8a94a6",
};
const FALLBACK_PALETTE = [
  "#0067b8",
  "#067647",
  "#b54708",
  "#b42318",
  "#6941c6",
  "#0e7490",
  "#be185d",
  "#4d7c0f",
  "#7c3aed",
];

// Mirrors tickets/workflow.py's INCIDENT_WORKFLOW_STATUSES / SERVICE_REQUEST_WORKFLOW_STATUSES
// — fixed column order for the "Open Tickets by Group × Status" crosstab tables below, so the
// column set stays stable even if a given group currently has zero tickets in some state.
const INCIDENT_WORKFLOW_STATUSES = [
  "PROGRESSING",
  "ON_HOLD",
  "PEND_3RDPARTY",
  "PEND_USER",
  "APPROVED",
  "RESOLVED",
];
const SERVICE_REQUEST_WORKFLOW_STATUSES = [
  "PROGRESSING",
  "ON_HOLD",
  "PEND_3RDPARTY",
  "PEND_USER",
  "IN_APPROVAL",
  "FULFILLED",
];

// Mirrors reporting/service.py's AGEING_BUCKETS — fixed column order (days old) for the
// "Ageing / Backlog" tables below, so the column set stays stable regardless of which
// buckets currently have tickets in them. Keys match the bucket keys the API returns in
// each row's `counts_by_bucket`; labels are the human-readable column headers.
const AGEING_BUCKETS = [
  { key: "<=1", label: "≤1 day" },
  { key: ">1", label: ">1 day" },
  { key: ">3", label: ">3 days" },
  { key: ">7", label: ">7 days" },
  { key: ">15", label: ">15 days" },
  { key: ">30", label: ">30 days" },
];

function colorFor(map, key, index) {
  return map[key] || FALLBACK_PALETTE[index % FALLBACK_PALETTE.length];
}

function toChartData(obj, colorMap) {
  return Object.entries(obj || {}).map(([key, value], i) => ({
    name: key.replace("_", " "),
    key,
    value,
    color: colorFor(colorMap || {}, key, i),
  }));
}

function CustomTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const p = payload[0];
  return (
    <div
      style={{
        background: "#fff",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: "8px 12px",
        fontSize: 13,
        boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
      }}
    >
      <strong>{p.name}</strong>: {p.value}
    </div>
  );
}

function PieCard({ title, data, total }) {
  const hasData = data.some((d) => d.value > 0);
  return (
    <div className="chart-card">
      <h3>{title}</h3>
      {!hasData ? (
        <p className="muted">No data yet</p>
      ) : (
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ width: 150, height: 150, flexShrink: 0 }}>
            <ResponsiveContainer>
              <PieChart>
                <Pie
                  data={data}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={42}
                  outerRadius={68}
                  paddingAngle={2}
                  stroke="none"
                >
                  {data.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip content={<CustomTooltip />} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <ul className="pie-legend">
            {data.map((d) => (
              <li key={d.key}>
                <span className="dot" style={{ background: d.color }} />
                <span className="pl-name">{d.name}</span>
                <span className="pl-value">{d.value}</span>
                <span className="pl-pct">
                  {total ? Math.round((d.value / total) * 100) : 0}%
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Kpi({ value, label, tone }) {
  return (
    <div className={`kpi-card${tone ? " " + tone : ""}`}>
      <div className="v">{value}</div>
      <div className="l">{label}</div>
    </div>
  );
}

function CrosstabTable({ title, columns, rows }) {
  return (
    <div className="chart-card">
      <h4 style={{ marginTop: 0 }}>{title}</h4>
      {!rows || rows.length === 0 ? (
        <p className="muted">No open tickets</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Assignment Group</th>
              {columns.map((c) => (
                <th key={c}>{c.replace(/_/g, " ")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.assignment_group_name}>
                <td>{r.assignment_group_name}</td>
                {columns.map((c) => (
                  <td key={c}>{r.counts_by_workflow_status?.[c] ?? 0}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function AgeingTable({ title, rows }) {
  return (
    <div className="chart-card">
      <h4 style={{ marginTop: 0 }}>{title}</h4>
      {!rows || rows.length === 0 ? (
        <p className="muted">No open tickets</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Assignment Group</th>
              {AGEING_BUCKETS.map((b) => (
                <th key={b.key}>{b.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.assignment_group_name}>
                <td>{r.assignment_group_name}</td>
                {AGEING_BUCKETS.map((b) => (
                  <td key={b.key}>{r.counts_by_bucket?.[b.key] ?? 0}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function slaTone(rate) {
  if (rate == null) return "";
  if (rate >= 90) return "ok";
  if (rate >= 75) return "warn";
  return "danger";
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [me, setMe] = useState(null);
  const [exporting, setExporting] = useState(null);
  const [error, setError] = useState(null);
  const [incidentCrosstab, setIncidentCrosstab] = useState(null);
  const [serviceRequestCrosstab, setServiceRequestCrosstab] = useState(null);
  const [monitoringAgeing, setMonitoringAgeing] = useState(null);
  const [humanIncidentAgeing, setHumanIncidentAgeing] = useState(null);
  const [serviceRequestAgeing, setServiceRequestAgeing] = useState(null);

  const load = useCallback(() => {
    api.get("/dashboard/overview").then(setData);
    api
      .get("/dashboard/engineer/me")
      .then(setMe)
      .catch(() => {});
    api
      .get("/dashboard/group-status-crosstab?ticket_type=INCIDENT")
      .then(setIncidentCrosstab)
      .catch(() => setIncidentCrosstab([]));
    api
      .get("/dashboard/group-status-crosstab?ticket_type=SERVICE_REQUEST")
      .then(setServiceRequestCrosstab)
      .catch(() => setServiceRequestCrosstab([]));
    api
      .get("/dashboard/ageing?ticket_type=INCIDENT&channel=monitoring")
      .then(setMonitoringAgeing)
      .catch(() => setMonitoringAgeing([]));
    api
      .get("/dashboard/ageing?ticket_type=INCIDENT&channel=human")
      .then(setHumanIncidentAgeing)
      .catch(() => setHumanIncidentAgeing([]));
    api
      .get("/dashboard/ageing?ticket_type=SERVICE_REQUEST&channel=all")
      .then(setServiceRequestAgeing)
      .catch(() => setServiceRequestAgeing([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleExport(kind) {
    setError(null);
    setExporting(kind);
    try {
      const blob = await api.get(`/dashboard/export/${kind}`);
      const ext = kind === "excel" ? "xlsx" : "pdf";
      const stamp = new Date().toISOString().slice(0, 10);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `epic-dashboard-${stamp}.${ext}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(`Export failed: ${e.message}`);
    } finally {
      setExporting(null);
    }
  }

  if (!data) return <p>Loading…</p>;

  const sla = data.sla || {};
  const trend = data.trend || [];
  const trendMax = Math.max(1, ...trend.map((t) => t.count));

  return (
    <>
      <div className="dashboard-header">
        <h2>Dashboard</h2>
        <div className="export-actions">
          <button
            className="btn secondary"
            disabled={exporting === "excel"}
            onClick={() => handleExport("excel")}
          >
            {exporting === "excel" ? "Exporting…" : "Export Excel"}
          </button>
          <button
            className="btn secondary"
            disabled={exporting === "pdf"}
            onClick={() => handleExport("pdf")}
          >
            {exporting === "pdf" ? "Exporting…" : "Export PDF"}
          </button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}

      {/* --- KPI row --- */}
      <div className="kpi-grid">
        <Kpi value={data.total_tickets} label="Total tickets" />
        <Kpi value={data.open_tickets} label="Currently open" />
        {me && <Kpi value={me.active || 0} label="My active workload" />}
        <Kpi
          value={sla.compliance_rate != null ? `${sla.compliance_rate}%` : "—"}
          label="SLA compliance"
          tone={slaTone(sla.compliance_rate)}
        />
        <Kpi
          value={
            sla.avg_resolution_hours != null
              ? `${sla.avg_resolution_hours}h`
              : "—"
          }
          label="Avg. resolution time"
        />
        <Kpi
          value={sla.breached ?? 0}
          label="SLA breached"
          tone={sla.breached ? "danger" : "ok"}
        />
        <Kpi
          value={sla.at_risk ?? 0}
          label="SLA at risk"
          tone={sla.at_risk ? "warn" : "ok"}
        />
        <Kpi
          value={sla.escalations?.at_risk_notified ?? 0}
          label="At-risk escalations sent"
          tone={sla.escalations?.at_risk_notified ? "warn" : "ok"}
        />
        <Kpi
          value={sla.escalations?.breached_notified ?? 0}
          label="Breach escalations sent"
          tone={sla.escalations?.breached_notified ? "danger" : "ok"}
        />
      </div>

      {/* --- Trend --- */}
      <div className="card" style={{ marginTop: 24 }}>
        <h3>Tickets created — last 14 days</h3>
        {trend.every((t) => t.count === 0) ? (
          <p className="muted">No tickets created in this window</p>
        ) : (
          <div style={{ width: "100%", height: 200 }}>
            <ResponsiveContainer>
              <BarChart
                data={trend}
                margin={{ top: 4, right: 8, left: -20, bottom: 0 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  vertical={false}
                  stroke="#eef0f3"
                />
                <XAxis
                  dataKey="date"
                  tickFormatter={(d) =>
                    new Date(d + "T00:00:00").toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                    })
                  }
                  tick={{ fontSize: 11, fill: "#57606a" }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  allowDecimals={false}
                  domain={[0, Math.max(4, trendMax)]}
                  tick={{ fontSize: 11, fill: "#57606a" }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip content={<CustomTooltip />} />
                <Bar
                  dataKey="count"
                  name="Tickets"
                  fill="#0067b8"
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* --- SLA target reference --- */}
      <div className="card">
        <h3>SLA targets by priority</h3>
        {sla.escalations?.last_escalation_at && (
          <p className="muted" style={{ marginTop: -4, marginBottom: 12 }}>
            Last escalation sent{" "}
            {new Date(
              sla.escalations.last_escalation_at + "Z",
            ).toLocaleString()}
          </p>
        )}
        <table>
          <thead>
            <tr>
              <th>Priority</th>
              <th>Target resolution time</th>
              <th>Avg. actual (resolved tickets)</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(sla.target_hours_by_priority || {}).map(
              ([p, hours]) => (
                <tr key={p}>
                  <td>
                    <span
                      className="dot"
                      style={{ background: PRIORITY_COLORS[p], marginRight: 8 }}
                    />
                    {p}
                  </td>
                  <td>{hours}h</td>
                  <td>
                    {sla.avg_resolution_hours_by_priority?.[p] != null
                      ? `${sla.avg_resolution_hours_by_priority[p]}h`
                      : "—"}
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      </div>

      {/* --- Pie charts --- */}
      <div className="charts-grid">
        <PieCard
          title="By status"
          data={toChartData(data.by_status, STATUS_COLORS)}
          total={data.total_tickets}
        />
        <PieCard
          title="By priority"
          data={toChartData(data.by_priority, PRIORITY_COLORS)}
          total={data.total_tickets}
        />
        <PieCard
          title="By type"
          data={toChartData(data.by_ticket_type)}
          total={data.total_tickets}
        />
        <PieCard
          title="By category"
          data={toChartData(data.by_category)}
          total={data.total_tickets}
        />
      </div>

      {/* --- Group x Status crosstab (production View D) --- */}
      <div className="card" style={{ marginTop: 24 }}>
        <h3>Open Tickets by Group × Status</h3>
        <div className="charts-grid">
          <CrosstabTable
            title="Incidents"
            columns={INCIDENT_WORKFLOW_STATUSES}
            rows={incidentCrosstab}
          />
          <CrosstabTable
            title="Service Requests"
            columns={SERVICE_REQUEST_WORKFLOW_STATUSES}
            rows={serviceRequestCrosstab}
          />
        </div>
      </div>

      {/* --- Ageing / Backlog (production View C) --- */}
      <div className="card" style={{ marginTop: 24 }}>
        <h3>Ageing / Backlog</h3>
        <p className="muted" style={{ marginTop: -4 }}>
          Open tickets by Assignment Group, bucketed by age.
        </p>
        <div className="charts-grid">
          <AgeingTable title="PRTG Alerts" rows={monitoringAgeing} />
          <AgeingTable title="Incidents" rows={humanIncidentAgeing} />
          <AgeingTable title="Service Requests" rows={serviceRequestAgeing} />
        </div>
      </div>
    </>
  );
}
