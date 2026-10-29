import {useCallback, useEffect, useRef, useState} from 'react'
import {ArrowLeft, Home, Leaf, ListChecks, MessageCircle, ScanLine, UserRound} from 'lucide-react'
import Access from './Access'
import AssistantPage from './AssistantPage'
import DetectPage from './DetectPage'
import {api, getServiceBase, getToken, setToken} from './api'
import {DetectionResult, ErrorNote, Loading, Sheet} from './components'
import {navigate, useRoute} from './hooks'
import {HomePage, KnowledgePage, PlotsPage, ProfilePage, RecordsPage, ServiceSettings} from './WorkspacePages'
import {emptyWorkspace, type Article, type Detection, type ModelInfo, type Plot, type User, type Workspace} from './types'
import {applyCropTheme} from './cropThemes'
import {isNativeAndroid, minimizeNativeApp, registerNativeBackButton} from './native'
import {ClientConfigProvider, useClientConfig} from './ClientConfig'

const tabs=[{id:'home',label:'首页',icon:Home},{id:'detect',label:'检测',icon:ScanLine},{id:'records',label:'记录',icon:ListChecks},{id:'profile',label:'我的',icon:UserRound}]
const titles:Record<string,string>={home:'禾观',detect:'作物检测',records:'检测记录',profile:'我的禾观',plots:'地块档案',knowledge:'田间笔记',assistant:'小禾助手',settings:'账户与连接'}
export default function App() {
  return <ClientConfigProvider><Application/></ClientConfigProvider>
}
function Application() {
  const {config,refreshConfig,configError}=useClientConfig()
  const route=useRoute();const page=route.split('/')[0];const [user,setUser]=useState<User|null>(null);const [checking,setChecking]=useState(true)
  const [data,setData]=useState<Workspace>(emptyWorkspace);const [loading,setLoading]=useState(false);const [error,setError]=useState('');const [toast,setToast]=useState('')
  const [serviceVersion,setServiceVersion]=useState(0);const [selected,setSelected]=useState<Detection|null>(null);const [analysis,setAnalysis]=useState<Detection|null>(null)
  const dataVersion=useRef(0);const needsService=isNativeAndroid()&&!getServiceBase();const authPage=['welcome','login','register'].includes(page)
  const refresh=useCallback(async()=>{
    if(!user)return;const version=++dataVersion.current;setLoading(true);setError('')
    void refreshConfig()
    try {const [records,plots,articles,model]=await Promise.all([api<Detection[]>('/detections'),api<Plot[]>('/plots'),api<Article[]>('/knowledge'),api<ModelInfo>('/models')]);if(dataVersion.current===version)setData({records,plots,articles,model})}
    catch(e){if(dataVersion.current===version)setError((e as Error).message)}finally{if(dataVersion.current===version)setLoading(false)}
  },[user,serviceVersion,refreshConfig])
  useEffect(()=>{document.documentElement.classList.toggle('reduce-motion',localStorage.getItem('agriscan-mobile-motion')==='false');const crop=localStorage.getItem('agriscan-mobile-crop');if(crop)applyCropTheme(crop)},[])
  useEffect(()=>{
    let disposed=false;let remove:(()=>void)|undefined
    registerNativeBackButton(()=>{
      if(document.querySelector('[role="dialog"]')){document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));return}
      if(user&&page!=='home')navigate('home')
      else if(!user&&!['login','welcome'].includes(page))navigate('login')
      else void minimizeNativeApp()
    }).then(cleanup=>{if(disposed)cleanup();else remove=cleanup})
    return()=>{disposed=true;remove?.()}
  },[page,user])
  useEffect(()=>{
    let alive=true
    if(!getToken()||needsService){setChecking(false);return}
    const token=getToken(),base=getServiceBase()
    const stillCurrent=()=>alive&&getToken()===token&&getServiceBase()===base
    setChecking(true);api<User>('/auth/me').then(value=>{if(stillCurrent())setUser(value)}).catch(()=>{if(stillCurrent()){dataVersion.current++;setUser(null);setData(emptyWorkspace);setSelected(null);setAnalysis(null)}}).finally(()=>{if(alive)setChecking(false)})
    return()=>{alive=false}
  },[serviceVersion,needsService])
  useEffect(()=>{if(user)void refresh()},[user,refresh])
  useEffect(()=>{
    const expired=()=>{dataVersion.current++;setUser(null);setData(emptyWorkspace);setSelected(null);setAnalysis(null);setToast('登录已过期，请重新登录。');navigate('login')}
    window.addEventListener('agriscan-mobile-auth-expired',expired);return()=>window.removeEventListener('agriscan-mobile-auth-expired',expired)
  },[])
  useEffect(()=>{if(checking)return;if(user&&authPage)navigate('home');else if(!user&&!authPage&&page!=='settings')navigate('login')},[checking,user,authPage,page])
  useEffect(()=>{if(!toast)return;const timer=window.setTimeout(()=>setToast(''),4500);return()=>window.clearTimeout(timer)},[toast])
  const handled=useCallback(()=>setAnalysis(null),[])
  const recognized=useCallback((crop:string)=>applyCropTheme(crop),[])
  function ask(record:Detection){if(!config.features.assistant){setToast('小禾新问答已由管理员暂停，已有对话仍可阅读。');return}setSelected(null);setAnalysis(record);recognized(record.crop);navigate('assistant')}
  function serviceSaved(){dataVersion.current++;setToken(null);setUser(null);setData(emptyWorkspace);setSelected(null);setAnalysis(null);setServiceVersion(value=>value+1);setToast('连接设置已保存，请登录对应服务。');navigate('login')}
  async function logout(){const token=getToken(),base=getServiceBase();try{await api('/auth/logout',{method:'POST'})}catch{if(getServiceBase()===base&&getToken()===token)setToast('已退出本机账户。服务暂不可用。')}finally{if(getServiceBase()===base&&(!getToken()||getToken()===token)){dataVersion.current++;setToken(null);setUser(null);setData(emptyWorkspace);setAnalysis(null);setSelected(null);setError('');navigate('login')}}}
  if(checking)return <div className="app-frame"><div className="startup"><Leaf size={30}/><h1>禾观</h1><Loading text="正在连接你的田间工作空间…"/></div></div>
  if(!user&&authPage&&!(needsService&&page!=='welcome'))return <div className="app-frame"><Access key={serviceVersion} page={page} onLogin={value=>{dataVersion.current++;setData(emptyWorkspace);setSelected(null);setAnalysis(null);setError('');setToast('');setUser(value);navigate('home')}} onSettings={()=>navigate('settings')}/>{toast&&<div className="toast" role="status">{toast}</div>}</div>
  return <div className={`app-frame page-${page}`} key={`${getServiceBase()}:${user?.username??'guest'}`}><header className="app-topbar"><button className="icon-button" aria-label={tabs.some(tab=>tab.id===page)?'打开首页':'返回'} onClick={()=>navigate(user?'home':'login')}>{tabs.some(tab=>tab.id===page)?<Leaf size={23}/>:<ArrowLeft size={22}/>}</button><strong>{needsService?'连接禾观服务':(page==='home'?config.brand.app_name:titles[page])||config.brand.app_name}<small>{page==='home'?'AGRISCAN':''}</small></strong>{user?<button className="icon-button" aria-label="和小禾聊天" onClick={()=>navigate('assistant')}><MessageCircle size={21}/></button>:<span className="topbar-spacer"/>}</header>
    <main className={`app-main ${user?'with-tabs':''} ${page==='assistant'?'chat-main':''}`}>
      {config.brand.announcement&&<div className="client-announcement" role="status"><Leaf size={15}/><p>{config.brand.announcement}</p></div>}{configError&&<p className="config-refresh-note">{configError}<button onClick={()=>void refreshConfig()}>重试</button></p>}
      {(page==='settings'||needsService)?<><div className="first-service-note">{needsService&&<><Leaf size={20}/><p>欢迎来到禾观。先填写可访问的农业检测服务地址，之后就能登录、上传照片和与小禾交流。</p></>}</div><ServiceSettings key={serviceVersion} user={user} onSaved={serviceSaved} onLogout={user?()=>void logout():undefined}/></>:
      user?<><ErrorNote message={error} retry={()=>void refresh()}/>{loading&&!data.model&&page!=='assistant'?<Loading/>:page==='home'?<HomePage user={user} data={data} onDetail={setSelected}/>:page==='detect'?<DetectPage mode={route.split('/')[1]||'image'} model={data.model} plots={data.plots} onSaved={()=>void refresh()} onAsk={config.features.assistant?ask:undefined} onRecognized={recognized}/>:page==='records'?<RecordsPage records={data.records} onDetail={setSelected} onRefresh={()=>void refresh()} loading={loading}/>:page==='profile'?<ProfilePage user={user} data={data} onLogout={()=>void logout()}/>:page==='plots'?<PlotsPage plots={data.plots}/>:page==='knowledge'?<KnowledgePage articles={data.articles}/>:page==='assistant'?<AssistantPage key={`${getServiceBase()}:${user.username}`} user={user} record={analysis} onHandled={handled}/>:<HomePage user={user} data={data} onDetail={setSelected}/>}</>:null}
    </main>{user&&<nav className="bottom-tabs" aria-label="主要导航">{tabs.map(tab=><button key={tab.id} aria-current={page===tab.id?'page':undefined} className={page===tab.id?'active':''} onClick={()=>navigate(tab.id==='detect'?'detect/image':tab.id)}><span><tab.icon size={22} strokeWidth={page===tab.id?2:1.7}/></span><strong>{tab.label}</strong>{page===tab.id&&<i/>}</button>)}</nav>}
    {selected&&<Sheet title="叶片观察报告" onClose={()=>setSelected(null)}><DetectionResult record={selected} onAsk={config.features.assistant?ask:undefined}/></Sheet>}{toast&&<div className="toast" role="status">{toast}</div>}
  </div>
}
