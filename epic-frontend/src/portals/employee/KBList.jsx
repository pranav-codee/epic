import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client.js'

export default function KBList() {
  const [items, setItems] = useState([])
  const [q, setQ] = useState('')
  async function load() {
    const params = new URLSearchParams(); if (q) params.set('q', q)
    setItems(await api.get('/kb/articles?' + params.toString()))
  }
  useEffect(() => { load() }, [])
  return (
    <>
      <h2>Knowledge Base</h2>
      <div className="toolbar">
        <input type="text" placeholder="Search articles…" value={q} onChange={e => setQ(e.target.value)} style={{ maxWidth: 320 }} />
        <button className="btn" onClick={load}>Search</button>
      </div>
      {items.map(a => (
        <div key={a.id} className="card">
          <h3 style={{ marginTop: 0 }}><Link to={`/employee/kb/${a.slug}`}>{a.title}</Link></h3>
          <div className="muted">{a.category} · updated {new Date(a.updated_at).toLocaleDateString()}</div>
        </div>
      ))}
      {items.length === 0 && <p className="muted">No articles yet. Content is loaded by IT via the seed_kb script.</p>}
    </>
  )
}
