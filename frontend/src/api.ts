// Shared components use the session for the independently built application surface.
const TOKEN_KEY = import.meta.env.VITE_APP_SURFACE === 'admin' ? 'agriscan-admin-token' : 'agriscan-token'
export const API_PREFIX = (import.meta.env.VITE_API_PREFIX || '').replace(/\/+$/, '')
export const apiUrl = (path: string) => `${API_PREFIX}/api${path}`
export function apiResourceUrl(path: string) {
  return path.startsWith('/api/') ? `${API_PREFIX}${path}` : path
}
export const getToken = () => sessionStorage.getItem(TOKEN_KEY)
export const setToken = (token: string | null) => token ? sessionStorage.setItem(TOKEN_KEY, token) : sessionStorage.removeItem(TOKEN_KEY)
const publicAuthPaths = new Set(['/auth/login', '/auth/register', '/auth/email-code', '/auth/config'])

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let response: Response
  try { response = await fetch(apiUrl(path), {...options, headers, cache: 'no-store', signal: options.signal ?? AbortSignal.timeout(20000)}) }
  catch (error) {
    if (error instanceof DOMException && error.name === 'TimeoutError') throw new Error('请求等待超时，请稍后重试。')
    if (error instanceof DOMException && error.name === 'AbortError') throw new Error('请求已取消。')
    throw new Error('暂时无法连接服务，请检查网络与后端连接后重试。')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const authPath = path.split(/[?#]/, 1)[0].replace(/\/+$/, '')
    // A failed sign-in is local to its form; an older request cannot expire a newer session.
    if (response.status === 401 && !publicAuthPaths.has(authPath) && getToken() === token) {
      setToken(null)
      window.dispatchEvent(new Event('agriscan-auth-expired'))
    }
    const validation = Array.isArray(body.detail) ? body.detail.map((item: {msg?: string}) => item.msg).filter(Boolean).slice(0, 3).join('；') : ''
    const message = typeof body.detail === 'string' ? body.detail : validation || (response.status === 401 ? '请先登录，或重新登录后再试。' : `操作未完成（${response.status}），请检查输入后重试。`)
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function downloadCsv(rows: (string | number | null)[][], name: string) {
  const csv = rows.map(row => row.map(value => {
    let text = String(value ?? '')
    if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`
    return `"${text.replace(/"/g, '""')}"`
  }).join(',')).join('\r\n')
  const url = URL.createObjectURL(new Blob(['\ufeff' + csv], {type: 'text/csv;charset=utf-8;'}))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = name
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
