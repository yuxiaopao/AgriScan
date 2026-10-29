import {useEffect,useRef,useState,type FormEvent} from 'react'
import {api,getToken} from './api'
import './email-forms.css'

export interface AuthConfiguration {registration_enabled:boolean;email_verification_enabled:boolean;password_reset_enabled:boolean}
interface EmailStatus {email:string|null;verified:boolean}
const resetCodeNotice='如果该邮箱已验证并关联可用账户，验证码会发送至该邮箱，请稍后查收。'

function useEmailForm(active:()=>boolean){
  const alive=useRef(true),token=useRef(getToken()),request=useRef<AbortController|null>(null),activeRef=useRef(active);activeRef.current=active
  const [action,setAction]=useState<'send'|'submit'|null>(null),[deadline,setDeadline]=useState(0),[now,setNow]=useState(Date.now())
  const current=()=>alive.current&&getToken()===token.current&&activeRef.current()
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;request.current?.abort()}},[])
  useEffect(()=>{
    if(!deadline)return
    const tick=()=>setNow(Date.now()),timer=window.setInterval(tick,1000)
    window.addEventListener('focus',tick)
    return()=>{window.clearInterval(timer);window.removeEventListener('focus',tick)}
  },[deadline])
  return {action,current,seconds:Math.max(0,Math.ceil((deadline-now)/1000)),
    start(kind:'send'|'submit'){
      if(!current()||request.current)return null
      const controller=new AbortController();request.current=controller;setAction(kind)
      return {signal:AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]),valid:()=>current()&&request.current===controller,
        finish(){if(current()&&request.current===controller)setAction(null);if(request.current===controller)request.current=null}}
    },
    cooldown(){const time=Date.now();setNow(time);setDeadline(time+60000)}}
}

export function ForgotPasswordForm({enabled,ready,configError,onRetry,onSuccess}:{enabled:boolean;ready:boolean;configError:string;onRetry:()=>void;onSuccess:()=>void}){
  const scope=useEmailForm(()=>window.location.hash==='#forgot-password'),form=useRef<HTMLFormElement>(null),email=useRef<HTMLInputElement>(null)
  const [error,setError]=useState(''),[message,setMessage]=useState('')
  async function sendCode(){
    if(!enabled||scope.seconds||!email.current?.reportValidity())return
    const action=scope.start('send');if(!action)return
    const target=email.current.value.trim();setError('');setMessage('')
    try{await api('/auth/password-reset-code',{method:'POST',body:JSON.stringify({email:target}),signal:action.signal});if(action.valid()){scope.cooldown();setMessage(resetCodeNotice)}}
    catch{if(action.valid())setError('验证码请求暂未完成，请稍后重试。')}
    finally{action.finish()}
  }
  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(!enabled||scope.action)return
    const values=new FormData(event.currentTarget),password=String(values.get('new_password')??''),confirm=String(values.get('confirm')??'')
    if(password.length<10||password.length>128){setError('新密码需要 10 至 128 位字符。');return}
    if(password!==confirm){setError('两次输入的新密码不一致。');return}
    const action=scope.start('submit');if(!action)return
    setError('');setMessage('')
    try{
      await api('/auth/password-reset',{method:'POST',body:JSON.stringify({email:String(values.get('email')??'').trim(),code:String(values.get('code')??''),new_password:password}),signal:action.signal})
      if(action.valid()){form.current?.reset();onSuccess()}
    }catch{if(action.valid())setError('重置未完成，请检查邮箱、验证码和新密码后重试；验证码可能已过期。')}
    finally{action.finish()}
  }
  return <><h2>找回账户密码</h2><p>使用已验证并绑定的邮箱接收验证码，设置新密码后返回登录。</p>
    <form ref={form} className="modal-form" onSubmit={submit} aria-busy={Boolean(scope.action)}>
      <label>已验证的邮箱<input ref={email} name="email" type="email" required maxLength={254} autoComplete="email" disabled={Boolean(scope.action)} placeholder="you@example.com"/></label>
      <label>邮箱验证码<div className="code-row"><input name="code" required pattern="[0-9]{6}" maxLength={6} inputMode="numeric" autoComplete="one-time-code" disabled={Boolean(scope.action)} placeholder="6 位数字"/><button type="button" className="button outline" disabled={!enabled||Boolean(scope.action)||scope.seconds>0} onClick={()=>void sendCode()}>{scope.action==='send'?'请求中…':scope.seconds?`${scope.seconds} 秒后重发`:'获取重置验证码'}</button></div></label>
      <label>新密码<input name="new_password" required type="password" minLength={10} maxLength={128} autoComplete="new-password" disabled={Boolean(scope.action)} placeholder="10 至 128 位字符"/></label>
      <label>确认新密码<input name="confirm" required type="password" minLength={10} maxLength={128} autoComplete="new-password" disabled={Boolean(scope.action)} placeholder="再次输入新密码"/></label>
      {!ready&&!configError&&<p className="quiet" role="status">正在确认邮箱找回服务…</p>}
      {configError&&<div className="form-error" role="alert"><p>账户服务配置暂未读取，请重试。</p><button type="button" className="text-button" onClick={onRetry}>重新读取配置</button></div>}
      {ready&&!enabled&&<p className="form-error" role="status">邮箱找回暂未开放，请联系管理员启用邮件服务。</p>}
      {error&&<p className="form-error" role="alert">{error}</p>}{message&&<p className="form-success" role="status">{message}</p>}
      <button className="button primary full" type="submit" disabled={!enabled||Boolean(scope.action)}>{scope.action==='submit'?'正在重置…':'更新密码并返回登录'}</button>
      <p className="email-form-note">未验证的历史邮箱不能直接找回密码。仍能登录时，请先到个人设置完成邮箱绑定验证。</p>
    </form><div className="auth-switch"><a href="#login">返回登录</a></div></>
}

export function AccountEmailSettings(){
  const scope=useEmailForm(()=>window.location.hash==='#settings'),form=useRef<HTMLFormElement>(null),email=useRef<HTMLInputElement>(null)
  const [status,setStatus]=useState<EmailStatus|null>(null),[enabled,setEnabled]=useState(false),[loading,setLoading]=useState(true),[retry,setRetry]=useState(0)
  const [draftEmail,setDraftEmail]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState('')
  useEffect(()=>{
    let active=true;const controller=new AbortController();setLoading(true);setError('')
    const valid=()=>active&&scope.current()
    Promise.all([api<EmailStatus>('/auth/email',{signal:controller.signal}),api<AuthConfiguration>('/auth/config',{signal:controller.signal})])
      .then(([value,config])=>{if(valid()){setStatus(value);setDraftEmail(value.email??'');setEnabled(Boolean(config.password_reset_enabled))}})
      .catch(()=>{if(valid())setError('邮箱状态暂未读取，请重新加载。')}).finally(()=>{if(valid())setLoading(false)})
    return()=>{active=false;controller.abort()}
    // The form belongs to the mounted account token; retry only reloads its own status.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[retry])
  async function sendCode(){
    if(!enabled||scope.seconds||!email.current?.reportValidity())return
    const action=scope.start('send');if(!action)return
    const target=draftEmail.trim();setError('');setMessage('')
    try{await api('/auth/email/verification-code',{method:'POST',body:JSON.stringify({email:target}),signal:action.signal});if(action.valid()){scope.cooldown();setMessage('验证邮件请求已提交，请查收邮箱中的验证码。')}}
    catch{if(action.valid())setError('验证码请求未完成，请检查邮箱后稍后重试。')}
    finally{action.finish()}
  }
  async function verify(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(!enabled||scope.action)return
    const action=scope.start('submit');if(!action)return
    const values=new FormData(event.currentTarget);setError('');setMessage('')
    try{
      const value=await api<EmailStatus>('/auth/email/verify',{method:'POST',body:JSON.stringify({email:draftEmail.trim(),code:String(values.get('code')??''),current_password:String(values.get('current_password')??'')}),signal:action.signal})
      if(action.valid()){setStatus(value);form.current?.reset();setDraftEmail(value.email??'');setMessage('邮箱已验证并绑定，以后可用它找回密码。')}
    }catch{if(action.valid())setError('绑定未完成，请检查当前密码与邮箱验证码后重试。')}
    finally{action.finish()}
  }
  return <section className="panel settings-panel email-settings"><div className="panel-header"><h2>我的验证邮箱</h2></div>
    <div className="email-settings-body">{loading?<p role="status">正在读取邮箱状态…</p>:<>
      {status&&<><strong className="email-current">{status.email||'尚未绑定邮箱'}</strong><p>{status.verified?'已验证，可用于找回密码。':status.email?'历史邮箱尚未验证，完成本人绑定验证后才能用于找回密码。':'绑定并验证邮箱后，可通过邮件找回密码。'}</p></>}
      {error&&<p className="form-error" role="alert">{error}</p>}{message&&<p className="form-success" role="status">{message}</p>}
      {!status?<button className="text-button" type="button" onClick={()=>setRetry(value=>value+1)}>重新读取邮箱状态</button>:!enabled?<div><p className="form-error" role="status">邮件验证服务暂未开放，当前邮箱保持不变。请联系管理员启用邮件服务。</p><button type="button" className="text-button" onClick={()=>setRetry(value=>value+1)}>重新检查邮件服务</button></div>:<details><summary>{status.verified?'更换已验证邮箱':'绑定并验证邮箱'}</summary>
        <form ref={form} className="modal-form" onSubmit={verify} aria-busy={Boolean(scope.action)}>
          <label>验证邮箱<input ref={email} name="email" type="email" required maxLength={254} autoComplete="email" disabled={Boolean(scope.action)} value={draftEmail} onChange={event=>{setDraftEmail(event.target.value);setError('');setMessage('')}} placeholder="you@example.com"/></label>
          <label>邮箱验证码<div className="code-row"><input name="code" required pattern="[0-9]{6}" maxLength={6} inputMode="numeric" autoComplete="one-time-code" disabled={Boolean(scope.action)} placeholder="6 位数字"/><button className="button outline" type="button" disabled={Boolean(scope.action)||scope.seconds>0} onClick={()=>void sendCode()}>{scope.action==='send'?'请求中…':scope.seconds?`${scope.seconds} 秒后重发`:'发送验证码'}</button></div></label>
          <label>当前登录密码<input name="current_password" type="password" required maxLength={128} autoComplete="current-password" disabled={Boolean(scope.action)} placeholder="验证本次操作属于你本人"/></label>
          <p className="email-form-note">验证成功前保留当前邮箱。此操作需要当前密码和新邮箱中的验证码。</p>
          <button className="button primary" type="submit" disabled={Boolean(scope.action)}>{scope.action==='submit'?'正在验证…':'验证并绑定邮箱'}</button>
        </form>
      </details>}
    </>}</div></section>
}
