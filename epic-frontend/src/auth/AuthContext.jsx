import React, { createContext, useContext, useEffect, useState } from 'react'
import { api } from '../api/client.js'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  async function refresh() {
    try {
      const me = await api.get('/auth/me')
      setUser(me)
    } catch (e) {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { refresh() }, [])

  function login() { window.location.href = '/api/v1/auth/login' }
  async function logout() {
    await api.post('/auth/logout', {})
    setUser(null)
  }

  return (
    <AuthCtx.Provider value={{ user, loading, login, logout, refresh }}>
      {children}
    </AuthCtx.Provider>
  )
}

export const useAuth = () => useContext(AuthCtx)

export function hasRole(user, ...roles) {
  if (!user) return false
  return roles.some(r => (user.roles || []).includes(r))
}
