const BASE_KEY = 'agriscan-mobile-service'
export const getServiceBase = () => localStorage.getItem(BASE_KEY) ?? (import.meta.env.VITE_API_BASE_URL || '')
const tokenKey = (base=getServiceBase()) => `agriscan-mobile-token:${base || 'proxy'}`
export const getToken = () => localStorage.getItem(tokenKey())
export const setToken = (token: string | null) => token ? localStorage.setItem(tokenKey(), token) : localStorage.removeItem(tokenKey())
export function normalizeServiceBase(value: string) {
  let base = value.trim().replace(/\/+$/, '').replace(/\/api$/, '')
  if (base) {
    let url:URL
    try {url = new URL(base)} catch {throw new Error('请输入完整的 HTTP 或 HTTPS 服务地址。')}
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error('请输入完整的 HTTP 或 HTTPS 服务地址。')
    base = url.toString().replace(/\/+$/, '')
  }
  return base
}
export function saveServiceBase(value: string) {
  localStorage.setItem(BASE_KEY, normalizeServiceBase(value))
  window.dispatchEvent(new Event('agriscan-mobile-service-changed'))
}
export class ApiError extends Error {constructor(message:string,public status:number){super(message)}}
export const endpoint = (path: string) => `${getServiceBase()}/api${path}`
export function mediaUrl(path: string) {return /^https?:\/\//.test(path) ? path : `${getServiceBase()}${path}`}
export async function api<T>(path: string, options: RequestInit = {}, timeout = 25000): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const base=getServiceBase();const token = localStorage.getItem(tokenKey(base)); if (token) headers.set('Authorization', `Bearer ${token}`)
  let response: Response
  const timeoutSignal = AbortSignal.timeout(timeout)
  const signal = options.signal ? AbortSignal.any([options.signal, timeoutSignal]) : timeoutSignal
  try {response = await fetch(`${base}/api${path}`, {...options, headers, signal})}
  catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw new Error('已停止等待本次请求。')
    if (error instanceof DOMException && error.name === 'TimeoutError') throw new Error('服务响应超时，请稍后重试。')
    throw new Error('暂时连接不上服务，请检查网络和服务地址。')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    if (response.status === 401&&token) {localStorage.removeItem(tokenKey(base));if(getServiceBase()===base)window.dispatchEvent(new Event('agriscan-mobile-auth-expired'))}
    const detail = Array.isArray(body.detail) ? body.detail.map((item: {msg?: string}) => item.msg).filter(Boolean).join('；') : body.detail
    throw new ApiError(typeof detail === 'string' ? detail : `操作未完成（${response.status}），请稍后重试。`,response.status)
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>
}
