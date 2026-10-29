import {useEffect,useRef,useState,type FormEvent} from 'react'
import {Mail,ShieldCheck} from 'lucide-react'
import {api} from './api'
import {ErrorNote} from './components'
import {FeedbackButton} from './Motion'
import {useAccountScope,useMailCooldown,validEmail} from './accountSecurity'
import type {AuthConfig} from './types'
import './account-security.css'

interface EmailStatus {email:string|null;verified:boolean}
export default function EmailBinding(){
  const scope=useAccountScope(true),cooldown=useMailCooldown(),form=useRef<HTMLFormElement>(null)
  const [status,setStatus]=useState<EmailStatus|null>(null),[email,setEmail]=useState(''),[enabled,setEnabled]=useState(false),[loading,setLoading]=useState(true),[retry,setRetry]=useState(0)
  const [busy,setBusy]=useState<'code'|'verify'|null>(null),[error,setError]=useState(''),[message,setMessage]=useState('')
  useEffect(()=>{
    const controller=new AbortController();let alive=true;setLoading(true);setError('')
    Promise.all([api<EmailStatus>('/auth/email',{signal:controller.signal}),api<AuthConfig>('/auth/config',{signal:controller.signal})]).then(([value,config])=>{if(alive&&scope.current()){setStatus(value);setEmail(value.email||'');setEnabled(config.password_reset_enabled)}}).catch(reason=>{if(alive&&scope.current())setError((reason as Error).message)}).finally(()=>{if(alive&&scope.current())setLoading(false)})
    return()=>{alive=false;controller.abort()}
  },[retry])
  async function sendCode(){
    if(loading||!enabled||cooldown.seconds)return
    if(!validEmail(email)){setError('请先填写有效的邮箱地址，再获取验证码。');return}
    const controller=scope.begin();if(!controller)return;setBusy('code');setError('');setMessage('')
    try{await api('/auth/email/verification-code',{method:'POST',signal:controller.signal,body:JSON.stringify({email:email.trim()})});if(scope.current()&&!controller.signal.aborted){cooldown.start();setMessage('如果该邮箱可用于绑定，验证码将发送至该邮箱，请稍后查收。')}}
    catch{if(scope.current()&&!controller.signal.aborted)setError('验证码请求暂未完成，请检查邮箱后稍后重试。')}
    finally{scope.finish(controller);if(scope.current())setBusy(null)}
  }
  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(loading||!enabled)return
    const values=new FormData(event.currentTarget),code=String(values.get('code')||''),password=String(values.get('current_password')||'')
    if(!validEmail(email)||!/^\d{6}$/.test(code)||!password||password.length>128){setError('请填写有效邮箱、6 位验证码和当前登录密码。');return}
    const controller=scope.begin();if(!controller)return;setBusy('verify');setError('');setMessage('')
    try{const response=await api<EmailStatus>('/auth/email/verify',{method:'POST',signal:controller.signal,body:JSON.stringify({email:email.trim(),code,current_password:password})});if(scope.current()&&!controller.signal.aborted){setStatus({email:response.email,verified:response.verified});form.current?.reset();setEmail(response.email||'');setMessage('邮箱已验证并绑定，可在登录页通过此邮箱找回密码。')}}
    catch{if(scope.current()&&!controller.signal.aborted)setError('绑定未完成，请检查当前密码与邮箱验证码后重试。')}
    finally{scope.finish(controller);if(scope.current())setBusy(null)}
  }
  if(!scope.valid)return null
  return <details className="card account-email"><summary><Mail size={19}/><span><strong>邮箱与密码找回</strong><small>{loading?'正在读取本人邮箱':status?.verified?'已验证，可用于密码找回':status?.email?'已有邮箱，尚未验证':'尚未绑定验证邮箱'}</small></span><ShieldCheck size={18}/></summary>
    <div className="account-email-body">{status&&<p className="account-email-status">当前邮箱：<strong>{status.email||'未绑定'}</strong><span>{status.verified?'已验证':'未验证'}</span></p>}<p className="account-security-help">绑定或更换邮箱，需要邮箱验证码与当前登录密码。历史邮箱也须完成验证后才能用于找回。</p>
      {loading?<p className="form-hint" role="status">正在读取邮箱设置…</p>:<form ref={form} className="auth-form" onSubmit={submit}><fieldset disabled={!!busy||!enabled||!status}>
        <label>{status?.email?'验证或更换邮箱':'绑定邮箱'}<input type="email" name="email" required maxLength={254} autoComplete="email" autoCapitalize="none" autoCorrect="off" spellCheck={false} value={email} onChange={event=>{setEmail(event.target.value);setMessage('')}} placeholder="you@example.com"/></label>
        <label>邮箱验证码<div className="code-field"><input name="code" required inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} placeholder="输入 6 位验证码"/><button type="button" onClick={sendCode} disabled={!email||cooldown.seconds>0}>{busy==='code'?'正在发送':cooldown.seconds?`${cooldown.seconds} 秒后重发`:'获取验证码'}</button></div></label>
        <label>当前登录密码<input name="current_password" type="password" required maxLength={128} autoComplete="current-password" placeholder="验证当前账户的登录密码"/></label>
      </fieldset><FeedbackButton type="submit" className="primary full" busy={busy==='verify'} busyLabel="正在验证并绑定" disabled={!!busy||!enabled||!status}>验证并绑定邮箱</FeedbackButton></form>}
      <ErrorNote message={error} retry={!busy&&!loading&&!status?()=>setRetry(value=>value+1):undefined}/>{message&&<p className="success-note" role="status">{message}</p>}{!loading&&!error&&!enabled&&<div className="info-note"><p>邮箱验证服务暂未开放，已有绑定状态仍可查看。</p><button type="button" className="text-button" onClick={()=>setRetry(value=>value+1)}>重新检查邮箱服务</button></div>}
    </div>
  </details>
}
