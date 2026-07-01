import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../../api/client.js'

export default function KBView() {
  const { slug } = useParams()
  const [a, setA] = useState(null)
  useEffect(() => { api.get(`/kb/articles/${slug}`).then(setA).catch(() => setA(false)) }, [slug])
  if (a === null) return <p>Loading…</p>
  if (a === false) return <p><Link to="/employee/kb">← Back</Link><br/>Article not found.</p>
  return (
    <>
      <p><Link to="/employee/kb">← Back to Knowledge Base</Link></p>
      <h2>{a.title}</h2>
      <div className="muted">{a.category}</div>
      <article style={{ whiteSpace: 'pre-wrap', marginTop: 16 }}>{a.content}</article>
    </>
  )
}
