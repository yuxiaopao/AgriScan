import {useEffect,useRef,useState,type FormEvent} from 'react'
import {ArrowLeft,Eye,EyeOff,Leaf,Settings2} from 'lucide-react'
import {api} from './api'
import {Art,ErrorNote} from './components'
import {navigate} from './hooks'
import {useClientConfig} from './ClientConfig'
import {FeedbackButton} from './Motion'
import {resetError,useAccountScope,useMailCooldown,validEmail} from './accountSecurity'
import type {AuthConfig} from './types'
import './account-security.css'

export default function PasswordReset({onSettings}:{onSettings:()=>void}){
  const {config:client}=useClientConfig(),scope=useAccountScope(),cooldown=useMailCooldown()
  const [config,setConfig]=useState<AuthConfig|null>(null),[loading,setLoading]=useState(true),[configError,setConfigError]=useState(''),[retry,setRetry]=useState(0)
  const [email,setEmail]=useState(''),[show,setShow]=useState(false),[busy,setBusy]=useState<'code'|'reset'|null>(null),[error,setError]=useState(''),[message,setMessage]=useState(''),[complete,setComplete]=useState(false)
  const form=useRef<HTMLFormElement>(null)
  const enabled=!loading&&!configError&&!!config?.password_reset_enabled
  useEffect(()=>{
    const controller=new AbortController();let alive=true
    setLoading(true);setConfigError('')
    api<AuthConfig>('/auth/config',{signal:controller.signal}).then(value=>{if(alive&&scope.current())setConfig(value)}).catch(reason=>{if(alive&&scope.current())setConfigError((reason as Error).message)}).finally(()=>{if(alive&&scope.current())setLoading(false)})
    return()=>{alive=false;controller.abort()}
  },[client.version,retry])
  async function sendCode(){
    if(!enabled||cooldown.seconds||complete)return
    if(!validEmail(email)){setError('请先填写有效的邮箱地址，再获取验证码。');return}
    const controller=scope.begin();if(!controller)return
    setBusy('code');setError('');setMessage('')
    try{await api('/auth/password-reset-code',{method:'POST',signal:controller.signal,body:JSON.stringify({email:email.trim()})});if(scope.current()&&!controller.signal.aborted){cooldown.start();setMessage('如果该邮箱已验证并关联可用账户，验证码会发送至该邮箱，请稍后查收。')}}
    catch{if(scope.current()&&!controller.signal.aborted)setError('验证码请求暂未完成，请稍后重试。')}
    finally{scope.finish(controller);if(scope.current())setBusy(null)}
  }
  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(!enabled||complete)return
    const values=new FormData(event.currentTarget),code=String(values.get('code')||''),password=String(values.get('new_password')||'')
    const problem=resetError(email,code,password,String(values.get('confirm')||''));if(problem){setError(problem);return}
    const controller=scope.begin();if(!controller)return
    setBusy('reset');setError('');setMessage('')
    try{await api('/auth/password-reset',{method:'POST',signal:controller.signal,body:JSON.stringify({email:email.trim(),code,new_password:password})});if(scope.current()&&!controller.signal.aborted){form.current?.reset();setEmail('');setShow(false);setComplete(true);setMessage('密码已更新，原有登录会话已失效。请使用新密码重新登录。')}}
    catch{if(scope.current()&&!controller.signal.aborted)setError('重置未完成，请检查邮箱、验证码和新密码后重试；验证码可能已过期。')}
    finally{scope.finish(controller);if(scope.current())setBusy(null)}
  }
  if(!scope.valid)return <div className="auth-page"><ErrorNote message="服务或账户已切换，请重新打开密码找回页面。"/><button className="button primary" onClick={()=>navigate('login')}>返回登录</button></div>
  return <div className="auth-page"><header><button className="icon-button" aria-label="返回登录" disabled={!!busy} onClick={()=>navigate('login')}><ArrowLeft size={21}/></button><span className="wordmark"><img src="/brand/logo.svg" alt="禾观 AgriScan" width="124" height="45"/></span><button className="icon-button" aria-label="连接服务设置" disabled={!!busy} onClick={onSettings}><Settings2 size={20}/></button></header>
    <div className="auth-intro"><Art src="/images/xiaohe.png" alt="小禾陪你找回账户"/><h1>找回你的密码</h1><p>通过已验证并绑定的邮箱，为账户设置新密码。</p></div>
    <form ref={form} className="auth-form" onSubmit={submit}><fieldset disabled={!!busy||!enabled||complete}>
      <label>已绑定邮箱<input name="email" type="email" autoComplete="email" autoCapitalize="none" autoCorrect="off" spellCheck={false} required maxLength={254} value={email} onChange={event=>{setEmail(event.target.value);setMessage('')}} placeholder="you@example.com"/></label>
      <label>邮箱验证码<div className="code-field"><input name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} required placeholder="输入 6 位验证码"/><button type="button" onClick={sendCode} disabled={cooldown.seconds>0||!email}>{busy==='code'?'正在发送':cooldown.seconds?`${cooldown.seconds} 秒后重发`:'获取验证码'}</button></div></label>
      <label>新密码<div className="password-field"><input name="new_password" type={show?'text':'password'} minLength={10} maxLength={128} autoComplete="new-password" required placeholder="10 至 128 位字符"/><button type="button" aria-label={show?'隐藏新密码':'显示新密码'} aria-pressed={show} onClick={()=>setShow(value=>!value)}>{show?<EyeOff size={18}/>:<Eye size={18}/>}</button></div></label>
      <label>确认新密码<input name="confirm" type={show?'text':'password'} minLength={10} maxLength={128} autoComplete="new-password" required placeholder="再次输入新密码"/></label>
    </fieldset><ErrorNote message={error}/>{message&&<p className="success-note" role="status">{message}</p>}
      {loading&&<p className="form-hint" role="status">正在确认邮箱找回服务…</p>}{configError&&<ErrorNote message={`暂时无法读取找回设置。${configError}`} retry={()=>setRetry(value=>value+1)}/>}{!loading&&!configError&&!enabled&&<p className="info-note" role="status">邮箱找回暂未开放，请联系管理员或稍后重试。</p>}
      <FeedbackButton type={complete?'button':'submit'} className="primary full" onClick={complete?()=>navigate('login'):undefined} busy={busy==='reset'} busyLabel="正在更新密码" complete={complete} completeLabel="密码已更新，前往登录" disabled={!complete&&(!enabled||!!busy)}>更新密码</FeedbackButton>
    </form><p className="account-security-help">验证码 10 分钟内有效。为保护账户，无论邮箱是否绑定，发送后的提示相同。旧账户若尚未验证邮箱，请先登录并在“账户与连接”中完成绑定。</p><p className="auth-service"><button disabled={!!busy} onClick={()=>navigate('login')}>返回登录</button></p><div className="auth-footer"><Leaf size={13}/>{client.brand.tagline}</div>
  </div>
}
