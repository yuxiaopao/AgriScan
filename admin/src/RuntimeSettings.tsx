import {useEffect, useRef, useState, type FormEvent} from 'react'
import {Check, EyeOff, LoaderCircle, PlugZap, RefreshCw, Save, Settings2, X} from 'lucide-react'
import {api} from '../../frontend/src/api'
import './runtime-settings.css'

type SecretName = 'smtp_password' | 'llm_api_key'
type SecretDraft = {mode: 'keep' | 'set' | 'clear'; value: string}
interface Integrations {
  registration_enabled: boolean; email_verification_enabled: boolean
  smtp_host: string; smtp_port: number; smtp_username: string; smtp_from: string; smtp_security: 'starttls' | 'ssl'
  smtp_password_configured: boolean; llm_enabled: boolean; llm_base_url: string; llm_model: string
  llm_timeout: number; llm_key_configured: boolean; model_max_mb: number
}
interface Configuration {
  version: number
  brand: {app_name: string; tagline: string; announcement: string}
  features: {image_detection: boolean; video_detection: boolean; live_detection: boolean; assistant: boolean; knowledge: boolean; plots: boolean}
  limits: {image_max_mb: number; video_max_mb: number; video_max_seconds: number; video_max_frames: number; frame_interval_ms: number}
  integrations: Integrations
}
interface LlmTestResult {
  ok: boolean; model: string; elapsed_ms: number; configuration_saved: false
  text: {ok: boolean; message: string}
  vision: {ok: boolean; message: string}
}
const DEEPSEEK_BASE = 'https://api.deepseek.com'
const DEEPSEEK_MODEL = 'deepseek-flash'
const featureLabels: Record<keyof Configuration['features'], [string,string]> = {
  image_detection: ['图片检测','上传图片、自动识别作物并保存观察'],
  video_detection: ['视频检测','按时间采样分析并保存各帧结果'],
  live_detection: ['实时相机','开启相机并持续抽帧识别'],
  assistant: ['小禾助手','开启新对话、发送问题与图片分析'],
  knowledge: ['田间知识','显示知识入口并允许知识问答'],
  plots: ['地块入口','在客户端显示地块档案和关联入口'],
}
const limits: [keyof Configuration['limits'],string,number,number,string][] = [
  ['image_max_mb','图片大小',1,10,'MB'],['video_max_mb','视频大小',1,50,'MB'],
  ['video_max_seconds','视频时长',1,60,'秒'],['video_max_frames','视频采样时点',1,8,'帧'],
  ['frame_interval_ms','实时相机最短间隔',750,10000,'毫秒'],
]
const freshSecrets = (): Record<SecretName,SecretDraft> => ({smtp_password:{mode:'keep',value:''},llm_api_key:{mode:'keep',value:''}})
const message = (error: unknown) => error instanceof Error ? error.message : '保存失败，请稍后重试。'

function Toggle({label, detail, value, onChange, disabled}: {label:string;detail?:string;value:boolean;onChange:(value:boolean)=>void;disabled?:boolean}) {
  return <label className="runtime-toggle"><span><strong>{label}</strong>{detail&&<small>{detail}</small>}</span><input type="checkbox" role="switch" checked={value} onChange={event=>onChange(event.target.checked)} disabled={disabled}/><i aria-hidden="true"/></label>
}
function SecretField({name, label, configured, draft, onChange}: {name:SecretName;label:string;configured:boolean;draft:SecretDraft;onChange:(value:SecretDraft)=>void}) {
  return <div className="runtime-secret"><div><strong>{label}</strong><span className={configured?'configured':''}><EyeOff size={13}/>{configured?'已配置 · 不显示原值':'尚未配置'}</span></div><label>处理方式<select aria-label={`${label}处理方式`} value={draft.mode} onChange={event=>onChange({mode:event.target.value as SecretDraft['mode'],value:''})}><option value="keep">保留当前密钥</option><option value="set">替换为新密钥</option><option value="clear">清除当前密钥</option></select></label>{draft.mode==='set'&&<label>新{label}<input name={name} type="password" autoComplete="new-password" maxLength={4096} required placeholder="输入新值；保存后不会回显" value={draft.value} onChange={event=>onChange({...draft,value:event.target.value})}/></label>}{draft.mode==='clear'&&<p className="runtime-caution">保存后会清除已配置的{label}；依赖此密钥的功能需要重新配置。</p>}</div>
}

export default function RuntimeSettings({revision=0, active=true, onSaved}: {revision?:number;active?:boolean;onSaved?:()=>void}) {
  const [saved,setSaved]=useState<Configuration|null>(null),[draft,setDraft]=useState<Configuration|null>(null)
  const [secret,setSecret]=useState(freshSecrets),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[reload,setReload]=useState(0)
  const [testing,setTesting]=useState(false),[testResult,setTestResult]=useState<LlmTestResult|null>(null),[testError,setTestError]=useState('')
  const testRequest=useRef(0),testAbort=useRef<AbortController|null>(null)
  const locked=busy||testing
  const dirty=Boolean(saved&&draft&&(JSON.stringify(saved)!==JSON.stringify(draft)||Object.values(secret).some(item=>item.mode!=='keep')))
  const dirtyRef=useRef(dirty);dirtyRef.current=dirty
  const forceReload=useRef(false)
  function clearLlmTest(){testRequest.current+=1;testAbort.current?.abort();testAbort.current=null;setTesting(false);setTestResult(null);setTestError('')}
  function reread(){clearLlmTest();forceReload.current=true;setReload(value=>value+1)}
  useEffect(()=>{
    if(!active)clearLlmTest()
    return()=>{testRequest.current+=1;testAbort.current?.abort();testAbort.current=null}
  },[active])
  useEffect(()=>{
    if(!active)return
    if(dirtyRef.current&&!forceReload.current){setNotice('已保留未保存的改动。若要读取服务器的新配置，请点击“丢弃并重新读取”。');return}
    forceReload.current=false;clearLlmTest()
    const controller=new AbortController();setLoading(true);setError('')
    api<Configuration>('/admin/config',{signal:AbortSignal.any([controller.signal,AbortSignal.timeout(20000)])})
      .then(value=>{if(!controller.signal.aborted){setSaved(value);setDraft(structuredClone(value));setSecret(freshSecrets())}})
      .catch(reason=>{if(!controller.signal.aborted)setError(message(reason))})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false)})
    return()=>controller.abort()
  },[revision,reload,active])
  useEffect(()=>{if(!dirty)return;const warn=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue=''};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn)},[dirty])
  function change<G extends 'brand'|'features'|'limits'|'integrations',K extends keyof Configuration[G]>(group:G,key:K,value:Configuration[G][K]) {if(group==='integrations'&&String(key).startsWith('llm_'))clearLlmTest();setDraft(old=>old?{...old,[group]:{...old[group],[key]:value}}:old);setNotice('')}
  function changeLlmSecret(value:SecretDraft){clearLlmTest();setSecret(old=>({...old,llm_api_key:value}));setNotice('')}
  function useDeepSeek(){
    if(!draft)return
    clearLlmTest()
    const endpointChanged=draft.integrations.llm_base_url.replace(/\/+$/,'')!==DEEPSEEK_BASE
    setDraft(old=>old?{...old,integrations:{...old.integrations,llm_base_url:DEEPSEEK_BASE,llm_model:DEEPSEEK_MODEL}}:old)
    if(secret.llm_api_key.mode==='clear'||(secret.llm_api_key.mode==='keep'&&(endpointChanged||!draft.integrations.llm_key_configured)))setSecret(old=>({...old,llm_api_key:{mode:'set',value:''}}))
    setNotice('已填入 DeepSeek 地址与模型，尚未保存。请填写密钥并测试连接。')
  }
  async function testLlm(){
    if(!draft||locked)return
    clearLlmTest()
    const settings=draft.integrations,key=secret.llm_api_key
    if(!settings.llm_base_url.trim()||!settings.llm_model.trim()){setTestError('请先填写 API 基础地址和模型名称。');return}
    if(!Number.isInteger(settings.llm_timeout)||settings.llm_timeout<1||settings.llm_timeout>120){setTestError('请求超时须为 1–120 秒的整数。');return}
    if(key.mode==='clear'){setTestError('清除密钥时无法测试。请保留当前密钥或输入新密钥。');return}
    if(key.mode==='set'&&!key.value.trim()){setTestError('请先输入新的大模型 API 密钥。');return}
    if(key.mode==='keep'&&!settings.llm_key_configured){setTestError('尚未配置密钥，请选择“替换为新密钥”并填写。');return}
    if(key.mode==='keep'&&saved&&settings.llm_base_url.replace(/\/+$/,'')!==saved.integrations.llm_base_url.replace(/\/+$/,'')){setTestError('服务地址已变更，请输入对应的新密钥后测试。');return}
    const requestId=++testRequest.current,controller=new AbortController();testAbort.current=controller;setTesting(true)
    const body={llm_base_url:settings.llm_base_url.trim(),llm_model:settings.llm_model.trim(),llm_timeout:settings.llm_timeout,...(key.mode==='set'?{llm_api_key:key.value}:{})}
    try{
      const result=await api<LlmTestResult>('/admin/config/llm/test',{method:'POST',body:JSON.stringify(body),signal:AbortSignal.any([controller.signal,AbortSignal.timeout(70000)])})
      if(requestId===testRequest.current&&!controller.signal.aborted)setTestResult(result)
    }catch(reason){if(requestId===testRequest.current&&!controller.signal.aborted)setTestError(message(reason))}
    finally{if(requestId===testRequest.current){setTesting(false);testAbort.current=null}}
  }
  async function save(event:FormEvent) {
    event.preventDefault();if(!draft||!saved||locked||!dirty)return;clearLlmTest();setBusy(true);setError('');setNotice('')
    const patch:Record<string,unknown>={version:saved.version}
    for(const group of ['brand','features','limits'] as const)if(JSON.stringify(draft[group])!==JSON.stringify(saved[group]))patch[group]=draft[group]
    const integrations:Record<string,unknown>={}
    for(const key of Object.keys(draft.integrations) as (keyof Integrations)[])if(!key.endsWith('_configured')&&draft.integrations[key]!==saved.integrations[key])integrations[key]=draft.integrations[key]
    for(const name of ['smtp_password','llm_api_key'] as const)if(secret[name].mode!=='keep')integrations[name]=secret[name].mode==='clear'?null:secret[name].value
    if(Object.keys(integrations).length)patch.integrations=integrations
    try {const value=await api<Configuration>('/admin/config',{method:'PATCH',body:JSON.stringify(patch)});setSaved(value);setDraft(structuredClone(value));setSecret(freshSecrets());setNotice(`配置 v${value.version} 已保存。客户端刷新或重新进入前台后读取最新配置，服务端立即按新配置控制操作。`);onSaved?.()}
    catch(reason){setError(message(reason))}finally{setBusy(false)}
  }
  if(loading)return <div className="adm-loading" role="status"><LoaderCircle className="spin" size={22}/>正在读取运行配置…</div>
  if(!draft)return <section className="adm-panel runtime-error"><p role="alert">{error}</p><button className="adm-button" onClick={reread}>重新读取</button></section>
  return <form className="runtime-settings" onSubmit={save}>
    <div className="runtime-toolbar"><div><Settings2 size={21}/><span><strong>客户端与服务配置</strong><small>当前版本 v{saved?.version}{dirty?' · 有未保存的改动':' · 已同步'}</small></span></div><button type="button" className="adm-button" disabled={locked} onClick={reread}>{dirty?'丢弃并重新读取':'重新读取'}</button><button className="adm-button primary" disabled={locked||!dirty}>{busy?<LoaderCircle size={16} className="spin"/>:<Save size={16}/>}保存所有配置</button></div>
    {error&&<div className="adm-error" role="alert"><span>{error}</span><button type="button" disabled={locked} onClick={reread}>丢弃改动并重新读取</button></div>}
    {notice&&<div className="runtime-success" role="status"><Check size={18}/>{notice}</div>}
    <fieldset disabled={locked}>
      <section className="adm-panel"><h2>品牌与公告</h2><p className="runtime-intro">应用名称、介绍与公告会下发至手机 APP 和桌面用户端。</p><div className="runtime-grid"><label>应用名称<input maxLength={60} required value={draft.brand.app_name} onChange={event=>change('brand','app_name',event.target.value)}/></label><label>介绍文字<input maxLength={140} value={draft.brand.tagline} onChange={event=>change('brand','tagline',event.target.value)}/></label><label className="runtime-wide">客户端公告<textarea rows={3} maxLength={1000} placeholder="留空时不显示公告" value={draft.brand.announcement} onChange={event=>change('brand','announcement',event.target.value)}/></label></div></section>
      <section className="adm-panel"><h2>客户端功能开关</h2><p className="runtime-intro">关闭后停止新操作，保留已有观察与对话供查阅。管理员仍可维护内容与地块。</p><div className="runtime-feature-grid">{(Object.keys(featureLabels) as (keyof Configuration['features'])[]).map(key=><Toggle key={key} label={featureLabels[key][0]} detail={featureLabels[key][1]} value={draft.features[key]} onChange={value=>change('features',key,value)}/>)}</div></section>
      <section className="adm-panel"><h2>检测限额</h2><p className="runtime-intro">限制在服务器支持的范围内。视频按时间采样识别；采样时点增加会延长处理时间。</p><div className="runtime-grid runtime-limit-grid">{limits.map(([key,label,min,max,unit])=><label key={key}>{label}<div className="runtime-number"><input type="number" required min={min} max={max} step={1} value={draft.limits[key]} onChange={event=>change('limits',key,Number(event.target.value))}/><span>{unit}</span></div><small>允许 {min}–{max} {unit}</small></label>)}</div></section>
      <section className="adm-panel"><h2>账户与注册</h2><div className="runtime-feature-grid"><Toggle label="开放注册" detail="允许新用户创建账户" value={draft.integrations.registration_enabled} onChange={value=>change('integrations','registration_enabled',value)}/><Toggle label="注册验证邮箱" detail="启用前需完成下方 SMTP 配置" value={draft.integrations.email_verification_enabled} onChange={value=>change('integrations','email_verification_enabled',value)}/></div></section>
      <section className="adm-panel"><h2>邮件服务 SMTP</h2><p className="runtime-intro">验证码通过此服务发送。保存时校验配置；邮件送达需邮箱服务商允许 SMTP 发信。</p><div className="runtime-grid"><label>服务器<input maxLength={253} autoComplete="off" value={draft.integrations.smtp_host} onChange={event=>change('integrations','smtp_host',event.target.value)}/></label><label>端口<input type="number" min={1} max={65535} required value={draft.integrations.smtp_port} onChange={event=>change('integrations','smtp_port',Number(event.target.value))}/></label><label>用户名<input maxLength={254} autoComplete="off" value={draft.integrations.smtp_username} onChange={event=>change('integrations','smtp_username',event.target.value)}/></label><label>发信邮箱<input type="email" maxLength={254} value={draft.integrations.smtp_from} onChange={event=>change('integrations','smtp_from',event.target.value)}/></label><label>加密方式<select value={draft.integrations.smtp_security} onChange={event=>change('integrations','smtp_security',event.target.value as 'starttls'|'ssl')}><option value="starttls">STARTTLS</option><option value="ssl">SSL / TLS</option></select></label></div><SecretField name="smtp_password" label="SMTP 授权密码" configured={draft.integrations.smtp_password_configured} draft={secret.smtp_password} onChange={value=>setSecret(old=>({...old,smtp_password:value}))}/></section>
      <section className="adm-panel runtime-llm-panel">
        <div className="runtime-llm-heading"><div><h2>小禾大模型服务</h2><p className="runtime-intro">管理员可在这里配置、测试并保存接入信息。密钥加密存入数据库，不会回显到客户端。</p></div><button type="button" className="adm-button" onClick={useDeepSeek}>填入 DeepSeek 配置</button></div>
        <Toggle label="启用大模型接入" detail="开启并保存后，小禾使用此服务进行问答与检测图片解读；需支持图片的模型。" value={draft.integrations.llm_enabled} onChange={value=>change('integrations','llm_enabled',value)}/>
        <div className="runtime-grid"><label className="runtime-wide">API 基础地址<input type="url" maxLength={2000} placeholder="https://api.deepseek.com" value={draft.integrations.llm_base_url} onChange={event=>change('integrations','llm_base_url',event.target.value)}/></label><label>模型名称<input maxLength={200} placeholder="deepseek-flash" value={draft.integrations.llm_model} onChange={event=>change('integrations','llm_model',event.target.value)}/></label><label>请求超时（秒）<input type="number" required min={1} max={120} value={draft.integrations.llm_timeout} onChange={event=>change('integrations','llm_timeout',Number(event.target.value))}/></label></div>
        <SecretField name="llm_api_key" label="大模型 API 密钥" configured={draft.integrations.llm_key_configured} draft={secret.llm_api_key} onChange={changeLlmSecret}/>
        <div className="runtime-llm-testbar"><button type="button" className="adm-button" disabled={locked||secret.llm_api_key.mode==='clear'} onClick={()=>{void testLlm()}}>{testing?<LoaderCircle className="spin" size={16}/>:<PlugZap size={16}/>} {testing?'正在测试文字与图片…':'测试连接'}</button><p>测试当前填写的信息或已保存的密钥，会向服务商发送少量文字和测试图片，产生少量调用用量。测试不会保存配置；确认后点击“保存所有配置”。</p></div>
        {testError&&<div className="runtime-llm-test-error" role="alert">{testError}</div>}
        {testResult&&<div className={`runtime-llm-result ${testResult.ok?'passed':'failed'}`} role="status" aria-live="polite"><div className="runtime-llm-result-heading"><strong>{testResult.ok?'连接测试通过':'连接测试未全部通过'}</strong><span>{testResult.model} · {(testResult.elapsed_ms/1000).toFixed(1)} 秒</span></div><dl>{(['text','vision'] as const).map(kind=><div key={kind}><dt>{kind==='text'?'文字问答':'图片理解'}</dt><dd className={testResult[kind].ok?'passed':'failed'}>{testResult[kind].ok?<Check size={15}/>:<X size={15}/>}<span>{testResult[kind].message}</span></dd></div>)}</dl><p>本次测试未写入数据库，也未开启接入。结果仅验证连接与图片输入，不代表病害判断准确率。</p></div>}
      </section>
      <section className="adm-panel"><h2>模型产物</h2><div className="runtime-grid"><label>权重上传上限（MB）<input type="number" min={1} max={2048} required value={draft.integrations.model_max_mb} onChange={event=>change('integrations','model_max_mb',Number(event.target.value))}/></label></div><p className="runtime-intro">上传产物在模型管理中登记，启用推理模型仍需通过模型适配及发布校验。</p></section>
    </fieldset>
    <div className="runtime-footer"><span>{dirty?'改动尚未保存':'所有配置已同步'} · 密钥加密存储，接口不返回原值</span><button type="button" className="adm-button" disabled={locked} onClick={()=>{clearLlmTest();setDraft(structuredClone(saved));setSecret(freshSecrets());setError('');setNotice('')}}><RefreshCw size={15}/>撤销本次改动</button><button className="adm-button primary" disabled={locked||!dirty}><Save size={16}/>{busy?'保存中…':'保存所有配置'}</button></div>
  </form>
}
