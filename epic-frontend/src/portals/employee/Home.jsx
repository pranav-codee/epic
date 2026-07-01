import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client.js'
import { Status, Priority } from '../../components/Badges.jsx'

export default function Home() {
  const [tickets, setTickets] = useState([])
  useEffect(() => { api.get('/tickets').then(setTickets).catch(() => {}) }, [])
  const open = tickets.filter(t => !['CLOSED', 'CANCELLED'].includes(t.status))
  return (
    <>
      <h2>Welcome</h2>
      <div className="dashboard-grid">
        <div className="stat"><div className="v">{open.length}</div><div className="l">Open tickets</div></div>
        <div className="stat"><div className="v">{tickets.length}</div><div className="l">All my tickets</div></div>
      </div>
      <h3 style={{ marginTop: 32 }}>Recent</h3>
      {tickets.slice(0, 5).map(t => (
        <div key={t.id} className="card">
          <Link to={`/employee/tickets/${t.id}`}><strong>{t.ticket_number}</strong> — {t.title}</Link>
          <div style={{ marginTop: 6 }}><Status value={t.status} /> <Priority value={t.priority} /> <span className="muted">{t.category}</span></div>
        </div>
      ))}
      {tickets.length === 0 && <p className="muted">You have no tickets yet. <Link to="/employee/new">Create one</Link>.</p>}
    </>
  )
}
