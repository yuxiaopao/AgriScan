import {useEffect, useRef, useState, type FormEvent} from 'react'
import {ArrowLeft, ArrowRight, Eye, EyeOff, Leaf, Settings2} from 'lucide-react'
import {api, getServiceBase, setToken} from './api'
import {Art, ErrorNote} from './components'
import {navigate} from './hooks'
import type {AuthConfig, User} from './types'
import {useClientConfig} from './ClientConfig'

const slides = [
  {eyebrow: 'HELLO, FIELD FRIEND', title: <>把田野，<br/>装进口袋里。</>, text: '你好，我是小禾。一起看见叶片的变化，照顾每一份生长。', image: 'app-hero.webp'},
  {eyebrow: 'A CLOSER LOOK', title: <>一片叶子，<br/>藏着生长的线索。</>, text: '拍照、选图或上传视频，记录作物健康，让每次观察都有迹可循。', image: 'feature-image.webp'},
  {eyebrow: 'GROW WITH CARE', title: <>和小禾一起，<br/>走进下一片绿意。</>, text: '开启实时相机，随手巡田；把观察交给模型，把疑问交给小禾。', image: 'feature-camera.webp'},
]
export default function Access({page, onLogin, onSettings}: {page: string; onLogin: (user: User) => void; onSettings: () => void}) {
  const {config:client}=useClientConfig();const mounted=useRef(true)
  const [step, setStep] = useState(0); const [config, setConfig] = useState<AuthConfig | null>(null)
  const [error, setError] = useState(''); const [message, setMessage] = useState(''); const [busy, setBusy] = useState(false)
  const [showPassword, setShowPassword] = useState(false); const [email, setEmail] = useState(''); const [cooldown, setCooldown] = useState(0); const [sending, setSending] = useState(false)
  const register = page === 'register'
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[])
  useEffect(() => {let alive = true; api<AuthConfig>('/auth/config').then(value => {if (alive) setConfig(value)}).catch(e => {if (alive) setError(e.message)}); return () => {alive = false}}, [client.version])
  useEffect(() => {setError(''); setMessage('')}, [page])
  useEffect(() => {if (!cooldown) return; const timer = window.setTimeout(() => setCooldown(value => value - 1), 1000); return () => window.clearTimeout(timer)}, [cooldown])
  function finish() {localStorage.setItem('agriscan-mobile-welcomed', 'true'); navigate('login')}
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return
    const form = new FormData(event.currentTarget); const username = String(form.get('username')); const password = String(form.get('password'))
    if (register && password !== form.get('confirm')) {setError('两次输入的密码不一致，请重新检查。'); return}
    setBusy(true); setError(''); setMessage('');const service=getServiceBase()
    try {
      if (register) {
        await api('/auth/register', {method:'POST', body:JSON.stringify({username,password,name:form.get('name'),email,code:form.get('code') || ''})})
        if(mounted.current&&service===getServiceBase())setMessage('账户创建成功，点击下方“去登录”继续。')
      } else {
        const value = await api<{access_token: string; user: User}>('/auth/login', {method:'POST',body:JSON.stringify({username,password})})
        if(!mounted.current||service!==getServiceBase())return
        setToken(value.access_token); localStorage.setItem('agriscan-mobile-welcomed','true'); onLogin(value.user)
      }
    } catch (e) {if(mounted.current)setError((e as Error).message)} finally {if(mounted.current)setBusy(false)}
  }
  async function sendCode() {
    if (sending || cooldown || !email) return; setSending(true); setError('')
    try {await api('/auth/email-code',{method:'POST',body:JSON.stringify({email})}); setCooldown(60); setMessage('验证码已发送，10 分钟内有效。')}
    catch(e) {setError((e as Error).message)} finally {setSending(false)}
  }
  if (page === 'welcome') {const slide = slides[step]; return <div className="onboarding"><header><span className="wordmark"><img src="/brand/logo.svg" alt="禾观 AgriScan" width="124" height="45" style={{display: 'block', objectFit: 'contain'}}/></span><button className="text-button" onClick={finish}>跳过</button></header>{client.brand.announcement&&<p className="client-announcement">{client.brand.announcement}</p>}<div className="onboarding-art"><div className="art-orbit"/><Art src={`/images/${slide.image}`} alt="小禾陪伴你记录作物生长" key={slide.image}/><span className="floating-label"><Leaf size={13}/>让生长，被看见</span></div><div className="onboarding-copy"><span className="eyebrow">{slide.eyebrow}</span><h1>{slide.title}</h1><p>{slide.text}</p></div><footer><div className="step-dots" aria-label={`引导第 ${step + 1} 页，共 3 页`}>{slides.map((_, index) => <button key={index} aria-label={`查看第 ${index + 1} 页`} aria-current={index === step ? 'step' : undefined} onClick={() => setStep(index)}/>)}</div><button className="button primary round" onClick={() => step === 2 ? finish() : setStep(step + 1)}>{step === 2 ? '开始我的巡田' : '下一步'}<ArrowRight size={19}/></button></footer></div>}
  return <div className="auth-page"><header><button className="icon-button" aria-label="返回欢迎页" onClick={() => navigate('welcome')}><ArrowLeft size={21}/></button><span className="wordmark"><img src="/brand/logo.svg" alt="禾观 AgriScan" width="124" height="45" style={{display: 'block', objectFit: 'contain'}}/></span><button className="icon-button" aria-label="连接服务设置" onClick={onSettings}><Settings2 size={20}/></button></header>{client.brand.announcement&&<p className="client-announcement">{client.brand.announcement}</p>}<div className="auth-intro"><Art src="/images/xiaohe.png" alt="小禾向你问好"/><span className="eyebrow">{register ? 'GROW A LITTLE CLOSER' : 'WELCOME BACK'}</span><h1>{register ? '你好，新朋友。' : '又见面了，田间伙伴。'}</h1><p>{register ? '创建账户，开始记录你的每一次观察。' : '登录禾观，继续照顾你的那一片绿意。'}</p></div><form className="auth-form" onSubmit={submit} key={page}><fieldset disabled={busy}>
    {register && <label>怎么称呼你<input name="name" placeholder="输入昵称" autoComplete="name" required maxLength={80}/></label>}
    <label>用户名<input name="username" placeholder="输入你的用户名" autoComplete="username" required minLength={register ? 3 : 1} maxLength={register ? 40 : 80} pattern={register ? '[a-zA-Z0-9_-]+' : undefined}/></label>
    {register && <label>邮箱 {config?.email_verification_enabled ? '（需要验证）' : '（选填）'}<input name="email" type="email" placeholder="you@example.com" autoComplete="email" required={config?.email_verification_enabled} value={email} onChange={event => setEmail(event.target.value)}/></label>}
    {register && config?.email_verification_enabled && <label>邮箱验证码<div className="code-field"><input name="code" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} placeholder="六位验证码" required/><button type="button" onClick={sendCode} disabled={sending || cooldown > 0 || !email}>{sending ? '发送中' : cooldown ? `${cooldown}秒后重发` : '获取验证码'}</button></div></label>}
    <label>密码<div className="password-field"><input name="password" type={showPassword ? 'text' : 'password'} required minLength={register ? 10 : 1} maxLength={128} autoComplete={register ? 'new-password' : 'current-password'} placeholder={register ? '至少 10 位字符' : '输入密码'}/><button type="button" aria-label={showPassword ? '隐藏密码' : '显示密码'} onClick={() => setShowPassword(!showPassword)}>{showPassword ? <EyeOff size={18}/> : <Eye size={18}/>}</button></div></label>
    {register && <label>确认密码<input name="confirm" type="password" required minLength={10} autoComplete="new-password" placeholder="再次输入密码"/></label>}
    <ErrorNote message={error}/>{message && <p className="success-note" role="status">{message}</p>}
    {register && config && !config.registration_enabled && <p className="error-note">管理员暂未开放注册。</p>}
    <button className="button primary full" disabled={busy || (register && !config?.registration_enabled)}>{busy ? '正在连接…' : register ? '创建我的账户' : '登录禾观'}<ArrowRight size={18}/></button>
  </fieldset></form><p className="auth-switch">{register ? '已经有账户？' : '还没有账户？'}<button onClick={() => navigate(register ? 'login' : 'register')} disabled={!register && !config?.registration_enabled}>{register ? '去登录' : config?.registration_enabled ? '注册新账户' : '暂未开放注册'}</button></p><p className="auth-service">连接遇到问题？<button onClick={onSettings}>设置服务地址</button></p><div className="auth-footer"><Leaf size={13}/>{client.brand.tagline}</div></div>
}
