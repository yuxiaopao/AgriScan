import {useEffect, useRef, useState, type FormEvent} from 'react'
import {ArrowLeft, Eye, EyeOff, Leaf, Settings2} from 'lucide-react'
import {api, getServiceBase, setToken} from './api'
import {Art, ErrorNote} from './components'
import {navigate} from './hooks'
import type {AuthConfig, User} from './types'
import {useClientConfig} from './ClientConfig'
import {FeedbackButton} from './Motion'
import PasswordReset from './PasswordReset'
import './account-security.css'
import {registrationUsernameError, USERNAME_HELP, USERNAME_MAX_LENGTH} from '../../shared/accountValidation'

const slides = [
  {title: <>把田野，<br/>装进口袋里。</>, text: '拍下一片叶子，记下生长变化。小禾陪你把每一次巡田留成记录。', image: 'app-hero.webp'},
  {title: <>每一次观察，<br/>都有迹可循。</>, text: '把照片、地块与采样备注放在一起，下次巡田时可以接着查看。', image: 'feature-image.webp'},
  {title: <>遇到新变化，<br/>随时问问小禾。</>, text: '小禾悬浮球一直在页面旁。看记录、查知识时，都可以打开对话。', image: 'feature-camera.webp'},
]
export default function Access({page, onLogin, onSettings}: {page: string; onLogin: (user: User) => void; onSettings: () => void}) {
  return page==='forgot-password'?<PasswordReset onSettings={onSettings}/>:<AccountAccess page={page} onLogin={onLogin} onSettings={onSettings}/>
}
function AccountAccess({page, onLogin, onSettings}: {page: string; onLogin: (user: User) => void; onSettings: () => void}) {
  const {config:client}=useClientConfig()
  const mounted=useRef(true), submitting=useRef(false), codeSending=useRef(false)
  const screen=useRef({page,version:0})
  if(screen.current.page!==page)screen.current={page,version:screen.current.version+1}
  const [step,setStep]=useState(0)
  const [config,setConfig]=useState<AuthConfig|null>(null)
  const [configLoading,setConfigLoading]=useState(true), [configError,setConfigError]=useState(''), [configRetry,setConfigRetry]=useState(0)
  const [error,setError]=useState(''), [message,setMessage]=useState(''), [busy,setBusy]=useState(false)
  const [created,setCreated]=useState(false)
  const [showPassword,setShowPassword]=useState(false), [email,setEmail]=useState(''), [cooldown,setCooldown]=useState(0), [sending,setSending]=useState(false)
  const register=page==='register'
  const registrationAvailable=!configLoading&&!configError&&!!config?.registration_enabled
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[])
  useEffect(()=>{
    let alive=true;const controller=new AbortController()
    setConfigLoading(true);setConfigError('')
    api<AuthConfig>('/auth/config',{signal:controller.signal})
      .then(value=>{if(alive)setConfig(value)})
      .catch(reason=>{if(alive)setConfigError((reason as Error).message)})
      .finally(()=>{if(alive)setConfigLoading(false)})
    return()=>{alive=false;controller.abort()}
  },[client.version,configRetry])
  useEffect(()=>{setError('');setMessage('');setCreated(false);setShowPassword(false)},[page])
  useEffect(()=>{if(!cooldown)return;const timer=window.setTimeout(()=>setCooldown(value=>value-1),1000);return()=>window.clearTimeout(timer)},[cooldown])
  function finish(){localStorage.setItem('agriscan-mobile-welcomed','true');navigate('login')}
  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault()
    if(submitting.current||(register&&!registrationAvailable)||created)return
    const form=new FormData(event.currentTarget), username=String(form.get('username')||'').trim(), password=String(form.get('password')||'')
    if(register){const invalidUsername=registrationUsernameError(username);if(invalidUsername){setError(invalidUsername);event.currentTarget.querySelector<HTMLInputElement>('[name="username"]')?.focus();return}}
    if(register&&password!==form.get('confirm')){setError('两次密码不一致，请重新输入确认密码。');event.currentTarget.querySelector<HTMLInputElement>('[name="confirm"]')?.focus();return}
    const version=screen.current.version,service=getServiceBase()
    const current=()=>mounted.current&&screen.current.version===version&&service===getServiceBase()
    submitting.current=true;setBusy(true);setError('');setMessage('')
    try{
      if(register){
        await api('/auth/register',{method:'POST',body:JSON.stringify({username,password,name:String(form.get('name')||'').trim(),email:email.trim(),code:form.get('code')||''})})
        if(current()){setCreated(true);setMessage('账户已创建。请使用刚才的用户名和密码登录。')}
      }else{
        const value=await api<{access_token:string;user:User}>('/auth/login',{method:'POST',body:JSON.stringify({username,password})})
        if(!current())return
        setToken(value.access_token);localStorage.setItem('agriscan-mobile-welcomed','true');onLogin(value.user)
      }
    }catch(reason){if(current())setError((reason as Error).message)}
    finally{submitting.current=false;if(mounted.current)setBusy(false)}
  }
  async function sendCode(){
    if(codeSending.current||cooldown||!registrationAvailable||!config?.email_verification_enabled)return
    const address=email.trim()
    if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(address)){setError('请先填写有效的邮箱地址，再获取验证码。');return}
    const version=screen.current.version,service=getServiceBase()
    const current=()=>mounted.current&&screen.current.version===version&&service===getServiceBase()
    codeSending.current=true;setSending(true);setError('');setMessage('')
    try{await api('/auth/email-code',{method:'POST',body:JSON.stringify({email:address})});if(current()){setCooldown(60);setMessage(`验证码已发送至 ${address}，请在 10 分钟内填写。`)}}
    catch(reason){if(current())setError((reason as Error).message)}
    finally{codeSending.current=false;if(mounted.current)setSending(false)}
  }
  if(page==='welcome'){
    const slide=slides[step]
    return <div className="onboarding"><header><span className="wordmark"><img src="/brand/logo.svg" alt="禾观 AgriScan" width="124" height="45" style={{display:'block',objectFit:'contain'}}/></span><button className="text-button" onClick={finish}>直接登录</button></header>
      {client.brand.announcement&&<p className="client-announcement">{client.brand.announcement}</p>}
      <div className="onboarding-art"><div className="art-orbit"/><Art src={`/images/${slide.image}`} alt="小禾陪你记录作物生长" key={slide.image}/><span className="floating-label"><Leaf size={13}/>随身记录，慢慢看见生长</span></div>
      <div className="onboarding-copy" key={step}><p className="onboarding-step">认识禾观 {step+1} / {slides.length}</p><h1>{slide.title}</h1><p>{slide.text}</p></div>
      <footer><div className="step-dots" aria-label={`引导第 ${step+1} 页，共 ${slides.length} 页`}>{slides.map((_,index)=><button key={index} aria-label={`查看第 ${index+1} 页`} aria-current={index===step?'step':undefined} onClick={()=>setStep(index)}/>)}</div><button className="button primary round" onClick={()=>step===slides.length-1?finish():setStep(step+1)}>{step===slides.length-1?'登录，开始记录':'继续了解'}</button></footer>
    </div>
  }
  return <div className="auth-page"><header><button className="icon-button" aria-label="返回欢迎页" disabled={busy||sending} onClick={()=>navigate('welcome')}><ArrowLeft size={21}/></button><span className="wordmark"><img src="/brand/logo.svg" alt="禾观 AgriScan" width="124" height="45" style={{display:'block',objectFit:'contain'}}/></span><button className="icon-button" aria-label="连接服务设置" disabled={busy||sending} onClick={onSettings}><Settings2 size={20}/></button></header>
    {client.brand.announcement&&<p className="client-announcement">{client.brand.announcement}</p>}
    <div className="auth-intro"><Art src="/images/xiaohe.png" alt="小禾欢迎你"/><h1>{register?'创建你的禾观账户':'欢迎回到禾观'}</h1><p>{register?'记录照片与地块，开始自己的田间观察。':'登录后，接着上一次的观察继续记录。'}</p></div>
    <form className="auth-form" onSubmit={submit} key={page}><fieldset disabled={busy||created}>
      {register&&<label>昵称<input name="name" placeholder="怎么称呼你" autoComplete="name" required maxLength={80}/></label>}
      <label>用户名<input name="username" aria-label="用户名" aria-describedby={register?'mobile-username-help':undefined} placeholder={register?'设置用户名，或使用邮箱地址':'输入注册时的用户名'} autoComplete="username" autoCapitalize="none" autoCorrect="off" spellCheck={false} required minLength={register?3:1} maxLength={USERNAME_MAX_LENGTH}/>{register&&<small id="mobile-username-help" className="form-hint">{USERNAME_HELP}</small>}</label>
      {register&&<label>邮箱 <span>{config?.email_verification_enabled?'需验证':'选填'}</span><input name="email" type="email" placeholder="you@example.com" autoComplete="email" autoCapitalize="none" autoCorrect="off" spellCheck={false} required={config?.email_verification_enabled} disabled={sending} value={email} onChange={event=>{setEmail(event.target.value);setMessage('');setCooldown(0)}}/></label>}
      {register&&config?.email_verification_enabled&&<label>邮箱验证码<div className="code-field"><input name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} placeholder="输入 6 位验证码" required/><button type="button" onClick={sendCode} disabled={sending||cooldown>0||!email||!registrationAvailable}>{sending?'正在发送':cooldown?`${cooldown} 秒后重发`:'获取验证码'}</button></div></label>}
      <label>密码<div className="password-field"><input name="password" aria-label="密码" type={showPassword?'text':'password'} required minLength={register?10:1} maxLength={128} autoComplete={register?'new-password':'current-password'} placeholder={register?'至少 10 位字符':'输入密码'}/><button type="button" aria-label={showPassword?'隐藏密码':'显示密码'} aria-pressed={showPassword} onClick={()=>setShowPassword(value=>!value)}>{showPassword?<EyeOff size={18}/>:<Eye size={18}/>}</button></div></label>
      {register&&<label>确认密码<input name="confirm" type={showPassword?'text':'password'} required minLength={10} maxLength={128} autoComplete="new-password" placeholder="再次输入密码"/></label>}
      <ErrorNote message={error}/>
    </fieldset>
      {message&&<p className="success-note" role="status">{message}</p>}
      {configError&&<div className="auth-config-note"><ErrorNote message={`暂时无法读取注册设置。${configError}`} retry={()=>setConfigRetry(value=>value+1)}/><p className="form-hint">已有账户仍可登录；注册设置恢复后即可创建新账户。</p></div>}
      {register&&configLoading&&<p className="form-hint" role="status">正在确认注册是否开放…</p>}
      {register&&!configLoading&&!configError&&!config?.registration_enabled&&<p className="error-note" role="status">新账户注册暂未开放，你可以返回登录。</p>}
      <FeedbackButton type={created?'button':'submit'} onClick={created?()=>navigate('login'):undefined} className="primary full" busy={busy} busyLabel={register?'正在创建账户':'正在登录'} complete={created} completeLabel="账户已创建，前往登录" disabled={!created&&register&&!registrationAvailable}>{register?'创建账户':'登录'}</FeedbackButton>
    </form>
    {!register&&<div className="auth-forgot"><button disabled={busy||sending} onClick={()=>navigate('forgot-password')}>忘记密码？</button></div>}
    <p className="auth-switch">{register?'已有账户？':'还没有账户？'}<button onClick={()=>navigate(register?'login':'register')} disabled={busy||sending||(!register&&!registrationAvailable)}>{register?'返回登录':configLoading?'正在确认注册设置':registrationAvailable?'创建账户':'注册暂不可用'}</button></p>
    <p className="auth-service">无法连接？<button disabled={busy||sending} onClick={onSettings}>检查服务地址</button></p><div className="auth-footer"><Leaf size={13}/>{client.brand.tagline}</div>
  </div>
}
