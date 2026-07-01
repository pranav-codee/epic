// Tiny fetch wrapper that always sends credentials (session cookie).
const BASE = '/api/v1'

async function req(method, path, body, isForm = false) {
  const opts = { method, credentials: 'include', headers: {} }
  if (body !== undefined && body !== null) {
    if (isForm) {
      opts.body = body
    } else {
      opts.headers['Content-Type'] = 'application/json'
      opts.body = JSON.stringify(body)
    }
  }
  const res = await fetch(BASE + path, opts)
  if (!res.ok) {
    const text = await res.text()
    const err = new Error(`${res.status} ${res.statusText}: ${text}`)
    err.status = res.status
    throw err
  }
  if (res.status === 204) return null
  const ct = res.headers.get('content-type') || ''
  return ct.includes('application/json') ? res.json() : res.blob()
}

export const api = {
  get: (p) => req('GET', p),
  post: (p, b) => req('POST', p, b),
  patch: (p, b) => req('PATCH', p, b),
  postForm: (p, fd) => req('POST', p, fd, true),
}
