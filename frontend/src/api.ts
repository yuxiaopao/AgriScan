const TOKEN_KEY = 'agriscan-token'
export const getToken = () => sessionStorage.getItem(TOKEN_KEY)
export const setToken = (token: string | null) => token ? sessionStorage.setItem(TOKEN_KEY, token) : sessionStorage.removeItem(TOKEN_KEY)

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let response: Response
  try { response = await fetch(`/api${path}`, {...options, headers, signal: options.signal ?? AbortSignal.timeout(20000)}) }
  catch { throw new Error('暂时无法连接服务，请确认后端已启动后重试。') }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    if (response.status === 401) {
      setToken(null)
      window.dispatchEvent(new Event('agriscan-auth-expired'))
    }
    const message = typeof body.detail === 'string' ? body.detail : response.status === 401 ? '请先登录，或重新登录后再试。' : `操作未完成（${response.status}），请检查输入后重试。`
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
