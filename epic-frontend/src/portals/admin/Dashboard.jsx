import React, { useEffect, useState } from "react";
import { api } from "../../api/client.js";

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [me, setMe] = useState(null);
  useEffect(() => {
    api.get("/dashboard/overview").then(setData);
    api
      .get("/dashboard/engineer/me")
      .then(setMe)
      .catch(() => {});
  }, []);
  if (!data) return <p>Loading…</p>;
  return (
    <>
      <h2>Dashboard</h2>
      <div className="dashboard-grid">
        <div className="stat">
          <div className="v">{data.total_tickets}</div>
          <div className="l">Total tickets</div>
        </div>
        <div className="stat">
          <div className="v">{data.open_tickets}</div>
          <div className="l">Currently open</div>
        </div>
        {me && (
          <div className="stat">
            <div className="v">{me.active || 0}</div>
            <div className="l">My active workload</div>
          </div>
        )}
      </div>

      <div className="card" style={{ marginTop: 24 }}>
        <h3>By status</h3>
        <table>
          <tbody>
            {Object.entries(data.by_status).map(([k, v]) => (
              <tr key={k}>
                <td>{k.replace("_", " ")}</td>
                <td>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h3>By type</h3>
        <table>
          <tbody>
            {Object.entries(data.by_ticket_type || {}).map(([k, v]) => (
              <tr key={k}>
                <td>{k.replace("_", " ")}</td>
                <td>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h3>By category</h3>
        <table>
          <tbody>
            {Object.entries(data.by_category).map(([k, v]) => (
              <tr key={k}>
                <td>{k}</td>
                <td>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h3>By priority</h3>
        <table>
          <tbody>
            {Object.entries(data.by_priority).map(([k, v]) => (
              <tr key={k}>
                <td>{k}</td>
                <td>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
