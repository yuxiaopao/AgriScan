import {useEffect, useState, type FormEvent} from 'react'
import {ArrowLeft, ArrowRight, CircleAlert, Eye, EyeOff, LoaderCircle, ShieldCheck} from 'lucide-react'
import Admin from './Admin'
import {api, getToken, setToken} from './api'
import type {User} from '../../frontend/src/types'

const workspaceUrl = import.meta.env.VITE_WORKSPACE_URL || (import.meta.env.DEV ? `${window.location.protocol}//${window.location.hostname}:5173/` : '/')
const memberDenied = '该账户没有管理员权限。请使用管理员账户登录管理控制台。'

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(Boolean(getToken()))
  const [error, setError] = useState('')
  useEffect(() => {
    let current = true
    const controller = new AbortController()
    if (getToken()) api<User>('/auth/me', {signal: controller.signal})
      .then(value => {
        if (!current) return
        if (value.role !== 'admin') {setToken(null); setError(memberDenied); return}
        setUser(value)
      })
      .catch(reason => {if (current) {setToken(null); setError((reason as Error).message)}})
      .finally(() => {if (current) setLoading(false)})
    const expired = () => {setUser(null); setError('管理员会话已过期，请重新登录。')}
    window.addEventListener('agriscan-auth-expired', expired)
    return () => {current = false; controller.abort(); window.removeEventListener('agriscan-auth-expired', expired)}
  }, [])
  async function logout() {
    setLoading(true)
    try {await api('/auth/logout', {method: 'POST'})}
    catch { /* Clear the local admin session even when the server cannot be reached. */ }
    finally {setToken(null); setUser(null); setError(''); setLoading(false); window.location.hash = 'login'}
  }
  if (loading) return <main className="admin-session-loading" role="status"><LoaderCircle className="spin" size={24}/><p>正在验证管理员会话…</p></main>
  if (user) return <Admin user={user} onExit={() => {window.location.href = workspaceUrl}} onLogout={() => {void logout()}} onDataChanged={() => {}}/>
  return <AdminLogin initialError={error} onLogin={value => {setError(''); setUser(value); window.location.hash = 'admin/overview'}}/>
}

function AdminLogin({initialError, onLogin}: {initialError: string; onLogin: (user: User) => void}) {
  const [error, setError] = useState(initialError)
  const [busy, setBusy] = useState(false)
  const [visible, setVisible] = useState(false)
  useEffect(() => {setError(initialError)}, [initialError])
  useEffect(() => {document.title = '管理员登录 · 禾观管理控制台'}, [])
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const values = Object.fromEntries(new FormData(event.currentTarget))
    setBusy(true); setError('')
    try {
      const result = await api<{access_token: string; user: User}>('/auth/login', {method: 'POST', body: JSON.stringify(values)})
      if (result.user.role !== 'admin') {setToken(null); setError(memberDenied); return}
      setToken(result.access_token); onLogin(result.user)
    } catch (reason) {setToken(null); setError((reason as Error).message)}
    finally {setBusy(false)}
  }
  return <main className="admin-login"><section className="admin-login-story"><img className="admin-login-brand" src="/brand/logo.svg" alt="禾观 AgriScan" width="166" height="60"/><div><span className="admin-login-label"><ShieldCheck size={17}/>工作空间管理</span><h1>照顾每一次生长，<br/>从有序的管理开始。</h1><p>连接成员、地块、田间观察与识别服务。<br/>让每一项配置、每一次调整，都有迹可循。</p><img className="admin-login-xiaohe" src="/images/xiaohe.png" alt="小禾农业助手"/></div><footer>AGRISCAN · GROW WITH CARE</footer></section><section className="admin-login-main"><a className="admin-login-back" href={workspaceUrl}><ArrowLeft size={16}/>返回用户工作台</a><div className="admin-login-card"><span className="admin-login-shield"><ShieldCheck size={29}/></span><p className="admin-login-eyebrow">ADMINISTRATOR ACCESS</p><h2>登录管理控制台</h2><p className="admin-login-description">使用管理员账户，维护你的农业工作空间。</p><form onSubmit={submit}><label>管理员用户名<input name="username" required maxLength={80} autoComplete="username" autoFocus placeholder="请输入管理员用户名" disabled={busy}/></label><label>密码<div className="admin-password"><input name="password" type={visible ? 'text' : 'password'} required maxLength={128} autoComplete="current-password" placeholder="请输入登录密码" disabled={busy}/><button type="button" onClick={() => setVisible(value => !value)} aria-label={visible ? '隐藏密码' : '显示密码'} aria-pressed={visible}>{visible ? <EyeOff size={18}/> : <Eye size={18}/>}</button></div></label>{error && <p className="admin-login-error" role="alert"><CircleAlert size={17}/>{error}</p>}<button className="admin-login-submit" disabled={busy}>{busy ? <><LoaderCircle className="spin" size={18}/>正在验证…</> : <>登录管理控制台<ArrowRight size={18}/></>}</button></form><p className="admin-login-note"><ShieldCheck size={15}/>仅限管理员访问 · 会话与用户工作台独立</p></div><footer>禾观管理控制台<span>账户权限由工作空间管理员分配</span></footer></section></main>
}
