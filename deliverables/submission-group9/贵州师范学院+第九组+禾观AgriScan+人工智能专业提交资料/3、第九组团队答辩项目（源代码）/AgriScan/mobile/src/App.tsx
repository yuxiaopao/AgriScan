import {useCallback, useEffect, useRef, useState} from 'react'
import {ArrowLeft, Leaf} from 'lucide-react'
import Access from './Access'
import FloatingAssistant from './FloatingAssistant'
import DetectPage from './DetectPage'
import {api, ApiError, getServiceBase, getToken, setToken} from './api'
import {DetectionResult, Empty, ErrorNote, Loading, Sheet} from './components'
import {goBack, navigate, replaceRoute, useRoute} from './hooks'
import {HomePage, KnowledgePage, PlotsPage, ProfilePage, RecordsPage, ServiceSettings} from './WorkspacePages'
import {emptyWorkspace, type Article, type Detection, type ModelInfo, type Plot, type User, type Workspace} from './types'
import {applyCropTheme,cropThemes} from './cropThemes'
import {isNativeAndroid, minimizeNativeApp, registerNativeBackButton} from './native'
import {ClientConfigProvider, useClientConfig} from './ClientConfig'
import {RouteRipple} from './Motion'
import {IpIcon} from './IpIcon'
import ModelsPage from './ModelsPage'
import DetectionTasksPage,{DetectionTaskResult} from './DetectionTasks'
import {taskFinished,useDetectionTasks} from './useDetectionTasks'

const tabs=[{id:'home',label:'首页',icon:'home'},{id:'detect',label:'检测',icon:'detect'},{id:'records',label:'记录',icon:'records'},{id:'profile',label:'我的',icon:'profile'}] as const
const titles:Record<string,string>={home:'禾观',detect:'作物检测',records:'检测记录',profile:'我的禾观',plots:'地块档案',knowledge:'田间笔记',assistant:'小禾助手',settings:'账户与连接',models:'识别服务',tasks:'检测任务'}
export default function App() {
  return <ClientConfigProvider><Application/></ClientConfigProvider>
}
function Application() {
  const {config,refreshConfig,configError}=useClientConfig()
  const route=useRoute();const page=route.split('/')[0];const [user,setUser]=useState<User|null>(null);const [checking,setChecking]=useState(true)
  const [data,setData]=useState<Workspace>(emptyWorkspace);const [loading,setLoading]=useState(false);const [error,setError]=useState('');const [toast,setToast]=useState('')
  const [serviceVersion,setServiceVersion]=useState(0);const [selected,setSelected]=useState<Detection|null>(null);const [analysis,setAnalysis]=useState<Detection|null>(null)
  const [assistantOpen,setAssistantOpen]=useState(() => window.location.hash === '#assistant')
  const [authError,setAuthError]=useState('');const [authRetry,setAuthRetry]=useState(0)
  const [workspaceReady,setWorkspaceReady]=useState(false)
  const [taskDetailKey,setTaskDetailKey]=useState<string|null>(null)
  const authIdentity=useRef({token:getToken(),base:getServiceBase()})
  const [visitedTabs,setVisitedTabs]=useState<string[]>(['home'])
  const lastDetectMode=useRef('image')
  if(page==='detect')lastDetectMode.current=route.split('/')[1]||'image'
  const dataVersion=useRef(0);const needsService=isNativeAndroid()&&!getServiceBase();const authPage=['welcome','login','register','forgot-password'].includes(page)
  const refresh=useCallback(async()=>{
    if(!user)return;const version=++dataVersion.current;setLoading(true);setError('')
    void refreshConfig()
    try {
      const [records,plots,articles,model]=await Promise.allSettled([api<Detection[]>('/detections'),api<Plot[]>('/plots'),api<Article[]>('/knowledge'),api<ModelInfo>('/models')])
      if(dataVersion.current!==version)return
      setData(old=>({records:records.status==='fulfilled'?records.value:old.records,plots:plots.status==='fulfilled'?plots.value:old.plots,articles:articles.status==='fulfilled'?articles.value:old.articles,model:model.status==='fulfilled'?model.value:old.model}))
      const results=[records,plots,articles,model],labels=['观察记录','地块档案','种植知识','识别服务']
      const failed=results.flatMap((result,index)=>result.status==='rejected'?[labels[index]]:[])
      if(failed.length<results.length)setWorkspaceReady(true)
      setError(failed.length?`${failed.join('、')}暂时未能读取。${failed.length<results.length?'其他内容仍可使用，可稍后重试。':'请检查服务连接后重试。'}`:'')
    }
    catch(e){if(dataVersion.current===version)setError((e as Error).message)}finally{if(dataVersion.current===version)setLoading(false)}
  },[user,serviceVersion,refreshConfig])
  const tasks=useDetectionTasks(user,()=>{setToast('检测任务结果已保存，可在任务中查看。');void refresh()})
  const activeTasks=tasks.jobs.filter(job=>!taskFinished(job)).length
  const taskDetail=tasks.jobs.find(job=>job.key===taskDetailKey)
  const currentToken=getToken(),currentBase=getServiceBase(),sameAccount=authIdentity.current.token===currentToken&&authIdentity.current.base===currentBase
  useEffect(()=>{
    const sync=()=>{
      const token=getToken(),base=getServiceBase()
      if(token===authIdentity.current.token&&base===authIdentity.current.base)return
      tasks.dispose();authIdentity.current={token,base};dataVersion.current++;setUser(null);setData(emptyWorkspace);setSelected(null);setAnalysis(null);setTaskDetailKey(null);setAssistantOpen(false);setAuthError('');setChecking(Boolean(token));setServiceVersion(value=>value+1)
    }
    sync();window.addEventListener('storage',sync);window.addEventListener('focus',sync);window.addEventListener('agriscan-mobile-service-changed',sync)
    return()=>{window.removeEventListener('storage',sync);window.removeEventListener('focus',sync);window.removeEventListener('agriscan-mobile-service-changed',sync)}
  },[currentToken,currentBase])
  useEffect(()=>{setVisitedTabs(['home']);setWorkspaceReady(false)},[user?.username,serviceVersion])
  useEffect(()=>{if(user&&tabs.some(tab=>tab.id===page))setVisitedTabs(old=>old.includes(page)?old:[...old,page])},[user,page])
  useEffect(()=>{setSelected(null);setTaskDetailKey(null)},[route])
  useEffect(()=>{document.documentElement.classList.toggle('reduce-motion',localStorage.getItem('agriscan-mobile-motion')==='false');const crop=localStorage.getItem('agriscan-mobile-crop');if(crop)applyCropTheme(crop)},[])
  useEffect(()=>{
    const open=()=>{if(!getToken())return;setSelected(null);setAssistantOpen(true)}
    window.addEventListener('agriscan-mobile-assistant-open',open)
    return()=>window.removeEventListener('agriscan-mobile-assistant-open',open)
  },[])
  useEffect(()=>{if(!checking&&!user)setAssistantOpen(false)},[user,checking])
  useEffect(()=>{
    const sync=()=>setAssistantOpen(Boolean(getToken()&&window.history.state?.agriscanMobileAssistant))
    window.addEventListener('popstate',sync)
    return()=>window.removeEventListener('popstate',sync)
  },[])
  useEffect(()=>{
    if(!assistantOpen||!user)return
    if(!window.history.state?.agriscanMobileAssistant)window.history.pushState({...window.history.state,agriscanMobileAssistant:true},'',window.location.href)
    return()=>{if(window.history.state?.agriscanMobileAssistant)window.history.back()}
  },[assistantOpen,user?.username])
  useEffect(()=>{
    let disposed=false;let remove:(()=>void)|undefined
    registerNativeBackButton(()=>{
      if(document.querySelector('[role="dialog"]')){document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));return}
      if(user&&page!=='home')goBack('home')
      else if(!user&&!['login','welcome'].includes(page))goBack('login')
      else void minimizeNativeApp()
    }).then(cleanup=>{if(disposed)cleanup();else remove=cleanup})
    return()=>{disposed=true;remove?.()}
  },[page,user])
  useEffect(()=>{
    let alive=true
    setAuthError('')
    if(!getToken()||needsService){setChecking(false);return}
    const token=getToken(),base=getServiceBase()
    const stillCurrent=()=>alive&&getToken()===token&&getServiceBase()===base
    setChecking(true);api<User>('/auth/me').then(value=>{if(stillCurrent())setUser(value)}).catch(reason=>{if(stillCurrent()){
      if(reason instanceof ApiError&&(reason.status===401||reason.status===403)){dataVersion.current++;setUser(null);setData(emptyWorkspace);setSelected(null);setAnalysis(null)}
      else setAuthError((reason as Error).message)
    }}).finally(()=>{if(stillCurrent())setChecking(false)})
    return()=>{alive=false}
  },[serviceVersion,needsService,authRetry])
  useEffect(()=>{if(user)void refresh()},[user,refresh])
  useEffect(()=>{
    const expired=()=>{tasks.dispose();authIdentity.current={token:getToken(),base:getServiceBase()};dataVersion.current++;setUser(null);setData(emptyWorkspace);setSelected(null);setAnalysis(null);setTaskDetailKey(null);setChecking(false);setAuthError('');setToast('登录已过期，请重新登录。');replaceRoute('login',true)}
    window.addEventListener('agriscan-mobile-auth-expired',expired);return()=>window.removeEventListener('agriscan-mobile-auth-expired',expired)
  },[])
  useEffect(()=>{if(checking||authError)return;if(user&&authPage)replaceRoute('home',true);else if(!user&&!authPage&&page!=='settings')replaceRoute('login',true)},[checking,user,authPage,page,authError])
  useEffect(()=>{if(!toast)return;const timer=window.setTimeout(()=>setToast(''),4500);return()=>window.clearTimeout(timer)},[toast])
  const handled=useCallback(()=>setAnalysis(null),[])
  const recognized=useCallback((crop:string)=>applyCropTheme(crop),[])
  const screenPages=Array.from(new Set([...visitedTabs,...(tabs.some(tab=>tab.id===page)?[page]:[])]))
  function screen(id:string) {
    if(!user)return null
    if(id==='home')return <HomePage user={user} data={data} onDetail={setSelected}/>
    if(id==='detect')return <DetectPage visible={page==='detect'&&!assistantOpen&&!taskDetailKey} mode={lastDetectMode.current} model={data.model} plots={data.plots} tasks={tasks} onOpenTask={setTaskDetailKey} onAsk={config.features.assistant?ask:undefined} onRecognized={recognized}/>
    if(id==='records')return <RecordsPage records={data.records} onDetail={setSelected} onRefresh={()=>void refresh()} loading={loading}/>
    if(id==='profile')return <ProfilePage user={user} data={data} onLogout={()=>void logout()}/>
    return null
  }
  function ask(record:Detection){if(record.status==='awaiting_model')return;if(!config.features.assistant){setToast('小禾新问答已由管理员暂停，已有对话仍可阅读。');return}setSelected(null);setTaskDetailKey(null);setAnalysis(record);recognized(record.crop);setAssistantOpen(true)}
  function serviceSaved(){tasks.dispose();dataVersion.current++;setToken(null);authIdentity.current={token:getToken(),base:getServiceBase()};setUser(null);setData(emptyWorkspace);setSelected(null);setAnalysis(null);setTaskDetailKey(null);setAuthError('');setServiceVersion(value=>value+1);setToast('连接设置已保存，请登录对应服务。');replaceRoute('login',true)}
  async function logout(){const token=getToken(),base=getServiceBase();tasks.dispose();dataVersion.current++;setToken(null);authIdentity.current={token:null,base};setUser(null);setData(emptyWorkspace);setAnalysis(null);setSelected(null);setTaskDetailKey(null);setAssistantOpen(false);setError('');setAuthError('');replaceRoute('login',true);if(!token)return;try{const response=await fetch(`${base}/api/auth/logout`,{method:'POST',headers:{Authorization:`Bearer ${token}`},cache:'no-store',credentials:'omit',redirect:'error',signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error()}catch{if(getServiceBase()===base&&!getToken())setToast('已退出本机账户，服务器暂未确认注销。')}}
  if(checking||!sameAccount)return <div className="app-frame"><div className="startup"><Leaf size={30}/><h1>禾观</h1><Loading text="正在连接你的田间工作空间…"/></div></div>
  if(authError&&page!=='settings')return <div className="app-frame"><main className="connection-recovery"><img src="/brand/logo.svg" width="166" height="60" alt="禾观"/><h1>暂时无法连接工作空间</h1><p>登录信息仍保留。恢复连接后，可以继续查看你的田间记录。</p><ErrorNote message={authError}/><button className="button primary" onClick={()=>setAuthRetry(value=>value+1)}>重新连接</button><button className="button outline" onClick={()=>navigate('settings')}>检查服务地址</button></main></div>
  if(!user&&authPage&&!(needsService&&page!=='welcome'))return <div className="app-frame"><Access key={serviceVersion} page={page} onLogin={value=>{authIdentity.current={token:getToken(),base:getServiceBase()};dataVersion.current++;setData(emptyWorkspace);setSelected(null);setAnalysis(null);setError('');setToast('');setUser(value);replaceRoute('home',true)}} onSettings={()=>navigate('settings')}/>{toast&&<div className="toast" role="status">{toast}</div>}</div>
  return <div className={`app-frame page-${page}`} key={`${getServiceBase()}:${user?.username??'guest'}`} inert={Boolean(user&&assistantOpen) || undefined}><header className="app-topbar"><button className="icon-button" aria-label={tabs.some(tab=>tab.id===page)?'打开首页':'返回'} onClick={()=>tabs.some(tab=>tab.id===page)?navigate(user?'home':'login'):goBack(user?'home':'login')}>{tabs.some(tab=>tab.id===page)?<IpIcon name="home"/>:<ArrowLeft size={22}/>}</button><strong>{needsService?'连接禾观服务':(page==='home'?config.brand.app_name:titles[page])||config.brand.app_name}<small>{page==='home'?'AGRISCAN':''}</small></strong>{user?<button className="icon-button tasks-entry" aria-label={`查看检测任务${activeTasks?`，${activeTasks}项进行中`:''}`} onClick={()=>navigate('tasks')}><IpIcon name="records"/>{activeTasks>0&&<span>{activeTasks}</span>}</button>:<span className="topbar-spacer" aria-hidden="true"/>}</header>
    <a className="skip-to-content" href="#main-content" onClick={event=>{event.preventDefault();document.getElementById('main-content')?.focus()}}>跳到主要内容</a><RouteRipple route={route}/><main id="main-content" tabIndex={-1} className={`app-main ${user?'with-tabs':''} `}><div className="route-content">
      {config.brand.announcement&&<div className="client-announcement" role="status"><Leaf size={15}/><p>{config.brand.announcement}</p></div>}{configError&&<p className="config-refresh-note">{configError}<button onClick={()=>void refreshConfig()}>重试</button></p>}
      {(page==='settings'||needsService)?<><div className="first-service-note">{needsService&&<><Leaf size={20}/><p>欢迎来到禾观。先填写可访问的农业检测服务地址，之后就能登录、上传照片和与小禾交流。</p></>}</div><ServiceSettings key={serviceVersion} user={user} onSaved={serviceSaved} onLogout={user?()=>void logout():undefined}/></>:null}
      {user&&!needsService?<>{page!=='settings'&&<ErrorNote message={error} retry={()=>void refresh()}/>}<div className="workspace-pages" hidden={page==='settings'}>{!workspaceReady?(loading?<Loading/>:<Empty title="工作空间暂未连接" text="检查网络与服务地址后重试，你的登录信息仍然保留。" action={<button className="button primary" onClick={()=>void refresh()}>重新读取记录</button>}/>):<>
        {screenPages.map(id=><div key={id} className="workspace-screen" hidden={page!==id} inert={page!==id||undefined}>{screen(id)}</div>)}
        {page==='plots'&&<div className="workspace-screen"><PlotsPage plots={data.plots} records={data.records} crops={data.model?.available_crops??Object.keys(cropThemes)} user={user} onChanged={plot=>{if(plot)setData(old=>({...old,plots:[plot,...old.plots.filter(item=>item.id!==plot.id)]}));void refresh()}} onDetail={setSelected}/></div>}
        {page==='knowledge'&&<div className="workspace-screen"><KnowledgePage articles={data.articles}/></div>}
        {page==='models'&&<div className="workspace-screen"><ModelsPage model={data.model}/></div>}
        {page==='tasks'&&<div className="workspace-screen"><DetectionTasksPage runtime={tasks} onOpen={setTaskDetailKey}/></div>}
      </>}</div></>:null}
    </div></main>{user&&<nav className="bottom-tabs" aria-label="主要导航">{tabs.map(tab=><button key={tab.id} aria-current={page===tab.id?'page':undefined} className={page===tab.id?'active':''} onClick={()=>navigate(tab.id==='detect'?`detect/${lastDetectMode.current}`:tab.id)}><span><IpIcon name={tab.icon}/></span><strong>{tab.label}</strong>{page===tab.id&&<i/>}</button>)}</nav>}
    {user&&<FloatingAssistant key={`assistant:${getServiceBase()}:${user.username}`} user={user} record={analysis} onHandled={handled} open={assistantOpen} onOpen={()=>{setSelected(null);setAssistantOpen(true)}} onClose={()=>setAssistantOpen(false)}/>}
    {selected&&<Sheet title="叶片观察报告" onClose={()=>setSelected(null)}><DetectionResult record={selected} onAsk={config.features.assistant&&selected.status!=='awaiting_model'?ask:undefined}/></Sheet>}{taskDetail&&<Sheet title="我的检测任务" onClose={()=>setTaskDetailKey(null)}><DetectionTaskResult key={taskDetail.key} job={taskDetail} runtime={tasks} visible={!assistantOpen} onAsk={config.features.assistant?ask:undefined} onRecognized={recognized}/></Sheet>}{toast&&<div className="toast" role="status">{toast}</div>}
  </div>
}
