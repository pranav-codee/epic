import React from 'react'
import { Routes, Route, Navigate, NavLink, useNavigate } from 'react-router-dom'
import { AuthProvider, useAuth, hasRole } from './auth/AuthContext.jsx'

import EmployeeHome from './portals/employee/Home.jsx'
import NewTicket from './portals/employee/NewTicket.jsx'
import MyTickets from './portals/employee/MyTickets.jsx'
import TicketDetail from './portals/employee/TicketDetail.jsx'
import KBList from './portals/employee/KBList.jsx'
import KBView from './portals/employee/KBView.jsx'

import AdminQueue from './portals/admin/Queue.jsx'
import AdminTicket from './portals/admin/AdminTicket.jsx'
import AdminDashboard from './portals/admin/Dashboard.jsx'
import AdminUsers from './portals/admin/Users.jsx'

function Shell({ children, area }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const isEngineer = hasRole(user, 'IT_ENGINEER', 'IT_MANAGER', 'SYSTEM_ADMIN')
  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>EPIC</h1>
        <div className="role-tag">{user?.display_name} · {(user?.roles || []).join(', ')}</div>
        {area === 'employee' && (
          <nav>
            <NavLink to="/employee" end>Home</NavLink>
            <NavLink to="/employee/new">New Ticket</NavLink>
            <NavLink to="/employee/tickets">My Tickets</NavLink>
            <NavLink to="/employee/kb">Knowledge Base</NavLink>
            {isEngineer && <NavLink to="/admin">→ Admin Portal</NavLink>}
          </nav>
        )}
        {area === 'admin' && (
          <nav>
            <NavLink to="/admin" end>Dashboard</NavLink>
            <NavLink to="/admin/queue">Ticket Queue</NavLink>
            <NavLink to="/admin/users">Users</NavLink>
            <NavLink to="/employee">→ Employee Portal</NavLink>
          </nav>
        )}
        <div style={{ marginTop: 24 }}>
          <button className="btn secondary" onClick={async () => { await logout(); navigate('/login') }}>Sign out</button>
        </div>
      </aside>
      <main className="content">{children}</main>
    </div>
  )
}

function RequireAuth({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div style={{ padding: 40 }}>Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  return children
}

function RequireRole({ roles, children }) {
  const { user } = useAuth()
  if (!hasRole(user, ...roles)) return <div className="content"><h2>403 — Not authorized</h2><p>Your account doesn't have access to this area.</p></div>
  return children
}

function Login() {
  const { login } = useAuth()
  return (
    <div style={{ maxWidth: 420, margin: '6rem auto', textAlign: 'center' }}>
      <h1>EPIC</h1>
      <p className="muted">Enterprise Platform for Intelligent IT Collaboration</p>
      <button className="btn" onClick={login}>Sign in with Microsoft</button>
      <p className="muted" style={{ marginTop: 24 }}>You will authenticate via Microsoft Authenticator.</p>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />

        <Route path="/" element={<Navigate to="/employee" replace />} />

        <Route path="/employee/*" element={
          <RequireAuth>
            <Shell area="employee">
              <Routes>
                <Route index element={<EmployeeHome />} />
                <Route path="new" element={<NewTicket />} />
                <Route path="tickets" element={<MyTickets />} />
                <Route path="tickets/:id" element={<TicketDetail />} />
                <Route path="kb" element={<KBList />} />
                <Route path="kb/:slug" element={<KBView />} />
              </Routes>
            </Shell>
          </RequireAuth>
        } />

        <Route path="/admin/*" element={
          <RequireAuth>
            <RequireRole roles={['IT_ENGINEER', 'IT_MANAGER', 'SYSTEM_ADMIN']}>
              <Shell area="admin">
                <Routes>
                  <Route index element={<AdminDashboard />} />
                  <Route path="queue" element={<AdminQueue />} />
                  <Route path="tickets/:id" element={<AdminTicket />} />
                  <Route path="users" element={<AdminUsers />} />
                </Routes>
              </Shell>
            </RequireRole>
          </RequireAuth>
        } />
      </Routes>
    </AuthProvider>
  )
}
