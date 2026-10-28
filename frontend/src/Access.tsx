import {Xiaohe} from './Xiaohe'
import {useEffect, useRef, useState, type FormEvent} from 'react'
import {ArrowRight, Leaf, ScanLine, ShieldCheck, Sprout} from 'lucide-react'
import {api, setToken} from './api'
import type {User} from './types'
import {useClientConfiguration} from './ClientConfig'

export default function Access({page, onLogin}: {page: string; onLogin: (user: User) => void}) {
  const client=useClientConfiguration()
  const mounted=useRef(true)
  const actionPage=useRef({page,generation:0})
  if(actionPage.current.page!==page)actionPage.current={page,generation:actionPage.current.generation+1}
  const [config, setConfig] = useState<{registration_enabled:boolean;email_verification_enabled:boolean}|null>(null)
  const [configRetry,setConfigRetry]=useState(0)
  const [configState,setConfigState]=useState({key:'',loading:true,error:''})
  const configKey=`${page}:${client.version}:${configRetry}`
  const configReady=configState.key===configKey&&!configState.loading&&!configState.error&&Boolean(config)
  const configError=configState.key===configKey?configState.error:''
  const registrationAvailable=configReady&&Boolean(config?.registration_enabled)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [sending, setSending] = useState(false)
  const [email, setEmail] = useState('')
  const [seconds, setSeconds] = useState(0)
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[])
  useEffect(()=>{
    let current=true;const controller=new AbortController()
    setConfigState({key:configKey,loading:true,error:''})
    api<NonNullable<typeof config>>('/auth/config',{signal:AbortSignal.any([controller.signal,AbortSignal.timeout(20000)])})
      .then(value=>{if(current){setConfig(value);setConfigState({key:configKey,loading:false,error:''})}})
      .catch(reason=>{if(current)setConfigState({key:configKey,loading:false,error:(reason as Error).message})})
    return()=>{current=false;controller.abort()}
  },[configKey])
  useEffect(()=>{setError('');setMessage('')},[page])
  useEffect(()=>{if(!seconds)return; const timer=setTimeout(()=>setSeconds(seconds-1),1000);return()=>clearTimeout(timer)},[seconds])
  const register=page==='register'
  async function submit(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();if(busy||(register&&!registrationAvailable))return;setError('');setMessage('')
    const values=Object.fromEntries(new FormData(event.currentTarget))
    if(register && values.password!==values.confirm){setError('两次输入的密码不一致。');return}
    setBusy(true);const generation=actionPage.current.generation
    try {
      if(register){await api('/auth/register',{method:'POST',body:JSON.stringify(values)});if(mounted.current&&actionPage.current.generation===generation)setMessage('注册成功！现在可以前往登录。')}
      else {const result=await api<{access_token:string;user:User}>('/auth/login',{method:'POST',body:JSON.stringify(values)});if(!mounted.current||actionPage.current.generation!==generation)return;setToken(result.access_token);onLogin(result.user)}
    } catch(e){if(mounted.current&&actionPage.current.generation===generation)setError((e as Error).message)} finally{if(mounted.current)setBusy(false)}
  }
  async function sendCode(){if(sending||seconds>0||!email||!registrationAvailable||!config?.email_verification_enabled)return;const generation=actionPage.current.generation;setSending(true);setError('');try{await api('/auth/email-code',{method:'POST',body:JSON.stringify({email})});if(mounted.current&&actionPage.current.generation===generation){setSeconds(60);setMessage('验证码已发送，请查收邮件。')}}catch(e){if(mounted.current&&actionPage.current.generation===generation)setError((e as Error).message)}finally{if(mounted.current)setSending(false)}}
  return <div className="access-shell"><header className="access-header"><a href="#welcome" className="brand"><img className="brand-logo" src="/brand/logo.svg" alt="禾观 AgriScan" width="166" height="60"/></a><nav><a href="#welcome">产品首页</a><a href="#login">登录</a>{registrationAvailable && <a className="button primary" href="#register">创建账户<ArrowRight size={15}/></a>}</nav></header>
    {page==='welcome' ? <main className="welcome-page"><div className="welcome-intro"><span className="hero-label"><Leaf size={16}/>面向田野的作物健康工作空间</span><h1>看见每片叶子的变化，<br/><em>守护每一季的丰收。</em></h1><p>从田间采样，到健康档案。让小禾陪你记录作物生长，<br/>用清晰的数据，连接每一次观察与行动。</p><div className="welcome-actions"><a href="#login" className="button primary">进入工作空间<ArrowRight size={17}/></a>{registrationAvailable && <a href="#register" className="button outline">注册新账户</a>}</div><span className="welcome-footnote">保留叶片原图，让检测结果与田间记录有据可查</span></div><div className="welcome-mascot"><div/><Xiaohe state="wave" label="小禾农业助手向你招手"/><span>你好，我是小禾。一起把田地照顾好。</span></div><div className="welcome-features">{[[ScanLine,'一张照片，开始观察','上传叶片图片，保留清晰的田间细节。'],[Sprout,'一块土地，一份档案','关联地块与作物，让每次采样有迹可循。'],[ShieldCheck,'记录真实，判断有据','保留原始图片、识别结果与当次模型信息。']].map(([Icon,title,text])=>{const I=Icon as typeof Leaf;return <article key={String(title)}><I size={23}/><h3>{String(title)}</h3><p>{String(text)}</p></article>})}</div></main> :
    <main className="auth-layout"><section className="auth-story"><span className="hero-label">GROW WITH CARE</span><h1>每一份用心，<br/>都会在田野里生长。</h1><p>欢迎{register?'加入':'回到'}禾观，和小禾一起记录新的生长。</p><Xiaohe state="idle" label="小禾欢迎你"/></section><section className="auth-card"><div className="eyebrow">YOUR AGRICULTURE WORKSPACE</div><h2>{register?'创建你的禾观账户':'欢迎回到禾观'}</h2><p>{register?'注册后可浏览共享工作空间并采集作物样本。':'登录后继续管理田间的每一份观察。'}</p><form className="modal-form" onSubmit={submit} key={page}>{register && <label>昵称<input name="name" required maxLength={80} autoComplete="name" placeholder="怎么称呼你"/></label>}<label>用户名<input name="username" required minLength={register?3:1} maxLength={register?40:80} pattern={register?'[a-zA-Z0-9_-]+':undefined} autoComplete="username" placeholder="字母、数字、下划线或短横线"/></label>{register && <label>邮箱 {config?.email_verification_enabled?'（需要验证）':'（选填）'}<input name="email" type="email" required={config?.email_verification_enabled} value={email} onChange={e=>setEmail(e.target.value)} autoComplete="email" placeholder="you@example.com"/></label>}{register && config?.email_verification_enabled && <label>邮箱验证码<div className="code-row"><input name="code" required pattern="[0-9]{6}" maxLength={6} placeholder="6 位数字"/><button type="button" className="button outline" disabled={sending||seconds>0||!email||!registrationAvailable} onClick={sendCode}>{sending?'发送中…':seconds?`${seconds} 秒后重发`:'发送验证码'}</button></div></label>}<label>密码<input name="password" required type="password" minLength={register?10:1} maxLength={128} autoComplete={register?'new-password':'current-password'} placeholder={register?'至少 10 位字符':'请输入密码'}/></label>{register&&<label>确认密码<input name="confirm" required type="password" minLength={10} autoComplete="new-password" placeholder="再次输入密码"/></label>}{configError&&<div className="form-error" role="alert"><p>注册配置读取失败：{configError}</p><button type="button" className="text-button" onClick={()=>setConfigRetry(value=>value+1)}>重试读取配置</button></div>}{register&&!configReady&&!configError&&<p className="quiet" role="status">正在确认最新注册配置…</p>}{register&&configReady&&!config?.registration_enabled&&<p className="form-error" role="status">管理员已暂停新账户注册。</p>}{error&&<p className="form-error" role="alert">{error}</p>}{message&&<p className="form-success" role="status">{message}</p>}<button className="button primary full" disabled={busy||(register&&!registrationAvailable)}>{busy?'正在处理…':register?'创建账户':'登录工作空间'}<ArrowRight size={16}/></button></form><div className="auth-switch">{register?<>已有账户？<a href="#login">前往登录</a></>:<>还没有账户？{registrationAvailable?<a href="#register">立即注册</a>:<span>注册暂未开放</span>}</>}</div></section></main>}
    <footer className="access-footer">AgriScan 禾观 · 让科技扎根，让生长可见</footer></div>
}
