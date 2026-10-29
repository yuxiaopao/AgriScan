import {confidenceText, PredictionScores} from './PredictionScores'
import {lazy, Suspense, useCallback, useEffect, useRef, useState} from 'react'
import {flushSync} from 'react-dom'
import {ArrowRight, ArrowUpRight, Bell, BookOpen, ChevronDown, ChevronRight, CircleAlert, CircleHelp, FlaskConical, LayoutDashboard, Leaf, LogIn, LogOut, Map, Menu, RefreshCw, ScanLine, Search, Settings2, ShieldCheck, Sprout, Trash2, X, History} from 'lucide-react'
import Access from './Access'
import {useCropTheme} from './CropTheme'
import {MotionSurface, reducedMotion} from './motion'
import FloatingAssistant from './FloatingAssistant'
import {DetectionTaskCenter,useDetectionTasks} from './DetectionTasks'
import {useClientConfiguration} from './ClientConfig'
import {api, getToken, setToken} from './api'
import {Badge, CropIcon, Loading, Modal, SecureImage} from './components'
import {DetectPage, exportRecords, KnowledgePage, ModelsPage, PlotsPage, RecordsPage, SettingsPage} from './Pages'
import type {Article, Dashboard as DashboardData, Detection, Health, ModelInfo, Page, Plot, User} from './types'

const navigation = [
  {page: 'dashboard', name: '总览工作台', icon: LayoutDashboard},
  {page: 'detect', name: '作物检测', icon: ScanLine},
  {page: 'records', name: '检测记录', icon: History},
  {page: 'plots', name: '地块管理', icon: Map},
  {page: 'knowledge', name: '病害知识库', icon: BookOpen},
  {page: 'models', name: '模型状态', icon: FlaskConical},
] as const
const Dashboard = lazy(() => import('./Dashboard'))
const adminUrl = import.meta.env.VITE_ADMIN_URL || (import.meta.env.DEV ? `${window.location.protocol}//${window.location.hostname}:5175/` : '/admin/')
const isAdminHash = () => window.location.hash === '#admin' || window.location.hash.startsWith('#admin/')
const pageFromHash = (): Page => {
  const hash = window.location.hash.slice(1)
  return [...navigation.map(item => item.page), 'settings'].includes(hash as Page) ? hash as Page : 'dashboard'
}
const accessFromHash = () => {const hash = window.location.hash.slice(1); return !hash ? 'welcome' : ['welcome', 'login', 'register','forgot-password'].includes(hash) ? hash : ''}
interface Resources {dashboard: DashboardData; records: Detection[]; plots: Plot[]; articles: Article[]; model: ModelInfo}

export default function App() {
  const client = useClientConfiguration()
  const sessionToken = getToken()
  const {crop: activeCrop, theme} = useCropTheme()
  const [accessPage,setAccessPage]=useState(accessFromHash)
  const [accessNotice,setAccessNotice]=useState('')
  const [authLoading, setAuthLoading] = useState(Boolean(getToken()))
  const [page, setPage] = useState<Page>(pageFromHash)
  const [data, setData] = useState<Resources | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [period, setPeriod] = useState(7)
  const [refresh, setRefresh] = useState(0)
  const [user, setUser] = useState<User | null>(null)
  const [detectionRequests, setDetectionRequests] = useState<Detection[]>([])
  const [adviceRequest,setAdviceRequest]=useState<Detection|null>(null)
  const [sessionVersion,setSessionVersion]=useState(0)
  const assistantSessionToken=useRef(sessionToken)
  const sameSession=assistantSessionToken.current===sessionToken
  const queueDetection = useCallback((record: Detection) => {if(sessionToken===getToken()){setAdviceRequest(null);setDetectionRequests(old => [...old, record])}}, [sessionToken])
  const handledDetection = useCallback((id: string) => setDetectionRequests(old => old.filter(record => record.id !== id)), [])
  const requestAdvice=useCallback((record:Detection)=>{if(sessionToken===getToken()){setAdviceRequest(record);setToastMessage('正在打开小禾建议，可查看后台处理进度。')}},[sessionToken])
  const handledAdvice=useCallback(()=>setAdviceRequest(null),[])
  const [search, setSearch] = useState('')
  const [recordStatus, setRecordStatus] = useState('')
  const [toastMessage, setToastMessage] = useState('')
  const [menu, setMenu] = useState(false)
  const [narrow, setNarrow] = useState(() => window.matchMedia('(max-width: 900px)').matches)
  const routeTransition = useRef<ViewTransition | null>(null)
  const [notifications, setNotifications] = useState(false)
  const [accountOpen, setAccountOpen] = useState(false)
  const sidebarRef = useRef<HTMLElement>(null)
  const menuButton = useRef<HTMLButtonElement>(null)
  const accountArea = useRef<HTMLDivElement>(null)
  const accountButton = useRef<HTMLButtonElement>(null)
  const [help, setHelp] = useState(false)
  const [selected, setSelected] = useState<Detection | null>(null)
  const [deleteRecord, setDeleteRecord] = useState(false)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const reload = useCallback(() => setRefresh(value => value + 1), [])
  const toast = useCallback((message: string) => setToastMessage(message), [])
  const tasks=useDetectionTasks(user&&sameSession?sessionToken:null,(record,job)=>{reload();toast(`${job.filename}已完成，可在检测任务中查看结果。`);if(client.features.assistant)queueDetection(record)})
  const navigate = (next: Page) => {window.location.hash = next; setMenu(false); setNotifications(false); setAccountOpen(false)}
  const requireAuth = () => {if (user && getToken()) return true; setSelected(null); setDeleteRecord(false); (window.location.hash = 'login'); return false}
  function clearAccountData(){setData(null);setSelected(null);setDeleteRecord(false);setDeleteBusy(false);setDetectionRequests([]);setAdviceRequest(null);setSearch('');setRecordStatus('');setPeriod(7);setError('');setToastMessage('');setNotifications(false);setAccountOpen(false)}

  useEffect(()=>{
    const sync=()=>{
      const token=getToken()
      if(token===assistantSessionToken.current)return
      assistantSessionToken.current=token
      clearAccountData();setSessionVersion(value=>value+1)
      setUser(null)
      if(token){
        setAuthLoading(true)
        api<User>('/auth/me').then(value=>{if(getToken()===token)setUser(value)})
          .catch(()=>{if(getToken()===token)setUser(null)})
          .finally(()=>{if(getToken()===token)setAuthLoading(false)})
      }else setAuthLoading(false)
    }
    sync()
    window.addEventListener('storage',sync);window.addEventListener('focus',sync)
    return()=>{window.removeEventListener('storage',sync);window.removeEventListener('focus',sync)}
  },[sessionToken])

  useEffect(() => {
    const onHash = () => {
      if (isAdminHash()) {window.location.replace(adminUrl + window.location.hash); return}
      const update = () => {setPage(pageFromHash()); setAccessPage(accessFromHash()); setAccountOpen(false); window.scrollTo({top: 0, behavior: 'instant'})}
      if (!reducedMotion() && document.startViewTransition) {
        routeTransition.current?.skipTransition()
        document.documentElement.dataset.routeTransition = 'true'
        const transition = document.startViewTransition(() => flushSync(update))
        routeTransition.current = transition
        void transition.finished.catch(() => {}).finally(() => {if (routeTransition.current === transition) {delete document.documentElement.dataset.routeTransition; window.dispatchEvent(new Event('agriscan-route-settled'))}})
        void transition.ready.catch(() => {})
      } else update()
    }
    if (isAdminHash()) window.location.replace(adminUrl + window.location.hash)
    const expired = () => {clearAccountData();setUser(null);(window.location.hash = 'login')}
    const dismiss = (event: KeyboardEvent) => {if (event.key === 'Escape') {setMenu(false); setNotifications(false); setAccountOpen(false)}}
    window.addEventListener('hashchange', onHash)
    window.addEventListener('agriscan-auth-expired', expired)
    window.addEventListener('keydown', dismiss)
    document.documentElement.classList.toggle('compact', localStorage.getItem('agriscan-compact') === 'true')
    document.documentElement.classList.toggle('reduce-motion', localStorage.getItem('agriscan-motion') === 'false')
    const bootToken=getToken()
    if (bootToken) api<User>('/auth/me').then(value=>{if(getToken()===bootToken)setUser(value)}).catch(() => {if(getToken()===bootToken){clearAccountData();setUser(null)}}).finally(() => {if(getToken()===bootToken)setAuthLoading(false)})
    else setAuthLoading(false)
    return () => {window.removeEventListener('hashchange', onHash); window.removeEventListener('agriscan-auth-expired', expired); window.removeEventListener('keydown', dismiss)}
  }, [])
  useEffect(() => {
    const media = window.matchMedia('(max-width: 900px)')
    const update = () => {setNarrow(media.matches); if (!media.matches) setMenu(false)}
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  useEffect(() => {
    if (!menu) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    sidebarRef.current?.querySelector<HTMLElement>('a[aria-current="page"], a')?.focus()
    const trap = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return
      const items = Array.from(sidebarRef.current?.querySelectorAll<HTMLElement>('a[href], button:not(:disabled)') || [])
      if (event.shiftKey && document.activeElement === items[0]) {event.preventDefault(); items[items.length - 1]?.focus()}
      if (!event.shiftKey && document.activeElement === items[items.length - 1]) {event.preventDefault(); items[0]?.focus()}
    }
    document.addEventListener('keydown', trap)
    return () => {document.body.style.overflow = previousOverflow; document.removeEventListener('keydown', trap); menuButton.current?.focus()}
  }, [menu])
  useEffect(() => {
    if (!accountOpen) return
    accountArea.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus()
    const outside = (event: PointerEvent) => {
      if (!accountArea.current?.contains(event.target as Node)) setAccountOpen(false)
    }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [accountOpen])
  useEffect(() => {
    if (accessPage || isAdminHash()) return
    const requestToken=getToken()
    if(!user||!requestToken){setData(null);setLoading(false);if(!authLoading)window.location.hash='login';return}
    let current = true
    const controller=new AbortController()
    const signal=AbortSignal.any([controller.signal,AbortSignal.timeout(20000)])
    const stillCurrent=()=>current&&getToken()===requestToken
    setError('')
    if (!data) setLoading(true)
    api<Health>('/health',{signal}).then(value => {if (stillCurrent()) setHealth(value)}).catch(() => {if (stillCurrent()) setHealth(null)})
    Promise.all([
      api<DashboardData>(`/dashboard?days=${period}`,{signal}),
      api<Detection[]>('/detections',{signal}),
      api<Plot[]>('/plots',{signal}),
      api<Article[]>('/knowledge',{signal}),
      api<ModelInfo>('/models',{signal}),
    ]).then(([dashboard, records, plots, articles, model]) => {if (stillCurrent()) setData({dashboard, records, plots, articles, model})}).catch(e => {if (stillCurrent()) setError((e as Error).message)}).finally(() => {if (stillCurrent()) setLoading(false)})
    return () => {current = false;controller.abort()}
    // Data remains visible during refresh; only inputs below trigger a request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refresh, period, accessPage, user?.username, authLoading,sessionVersion])
  useEffect(() => {if (!toastMessage) return; const timer = setTimeout(() => setToastMessage(''), 5000); return () => clearTimeout(timer)}, [toastMessage])
  useEffect(() => {document.title = `${accessPage ? ({welcome:'欢迎来到禾观',login:'登录',register:'创建账户','forgot-password':'找回密码'}[accessPage]) : navigation.find(item => item.page === page)?.name ?? '系统设置'} · ${client.brand.app_name}`}, [page, accessPage, client.brand.app_name])
  async function logout() {
    const logoutToken = getToken()
    let logoutError = ''
    try {await api('/auth/logout', {method: 'POST'})}
    catch (e) {logoutError = (e as Error).message}
    finally {
      const currentToken = getToken()
      if (!currentToken || currentToken === logoutToken) {
        setToken(null);setUser(null);clearAccountData()
        window.location.hash = 'welcome'; reload(); toast(logoutError ? `已退出本地登录。${logoutError}` : '已退出登录。')
      }
    }
  }
  async function removeRecord() {
    if (!selected) return
    setDeleteBusy(true)
    const requestToken=getToken()
    try {await api(`/detections/${selected.id}`, {method: 'DELETE'});if(getToken()===requestToken){setSelected(null);setDeleteRecord(false);reload();toast('我的检测样本已删除。')}}
    catch (e) {if(getToken()===requestToken)toast((e as Error).message)}
    finally {if(getToken()===requestToken)setDeleteBusy(false)}
  }
  const currentPageName = navigation.find(item => item.page === page)?.name ?? '系统设置'
  if (isAdminHash()) return <main className="main-content"><section className="panel empty"><ShieldCheck size={36}/><h1>正在打开独立管理控制台</h1><a className="button primary" href={adminUrl}>前往管理端</a></section></main>
  if (authLoading||!sameSession) return <main className="main-content"><Loading/></main>
  if (accessPage) return <MotionSurface key={accessPage} page={accessPage} className="access-motion"><Access page={accessPage} notice={accessNotice} onPasswordReset={()=>{setToken(null);clearAccountData();setUser(null);setAccessNotice('密码已更新，请使用新密码登录。');window.location.hash='login'}} onLogin={value=>{clearAccountData();setAccessNotice('');setUser(value);window.location.hash='dashboard';reload()}}/></MotionSurface>
  return <div className="app-shell" key={`${user?.username??'guest'}:${sessionVersion}`}>
    <a className="skip-to-content" href="#workspace-content" onClick={event => {event.preventDefault(); document.getElementById('workspace-content')?.focus()}}>跳至页面内容</a>
    {menu && <button className="sidebar-scrim" aria-label="关闭导航" onClick={() => setMenu(false)}/>}
    <aside ref={sidebarRef} id="workspace-navigation" inert={narrow && !menu || undefined} className={`sidebar ${menu ? 'open' : ''}`}>
      <a className="brand" href="#dashboard" onClick={() => setMenu(false)}><img className="brand-logo" src="/brand/logo.svg" alt="禾观 AgriScan" width="166" height="60"/></a>
      <div className="workspace-name"><span className="workspace-avatar"><Leaf size={17}/></span><span><strong>{client.brand.app_name}</strong><small>AGRICULTURE WORKSPACE</small></span><span className="workspace-dot"/></div>
      <div className="nav-section-title">工作空间<span>WORKSPACE</span></div>
      <nav aria-label="主导航">{navigation.filter(item => (item.page !== 'knowledge' || client.features.knowledge) && (item.page !== 'plots' || client.features.plots)).map(item => <a key={item.page} href={`#${item.page}`} className={`nav-link ${page === item.page ? 'active' : ''}`} aria-current={page === item.page ? 'page' : undefined} onClick={() => setMenu(false)}><item.icon size={18} strokeWidth={1.7}/><span>{item.name}</span>{item.page === 'detect' ? <span className="nav-ai">AI</span> : page === item.page ? <span className="nav-dot"/> : null}</a>)}</nav>
      <div className="sidebar-bottom">{user?.role === 'admin' && <a className="nav-link" href={adminUrl} target="_blank" rel="noreferrer" onClick={() => setMenu(false)}><ShieldCheck size={18}/><span>管理中心</span><ArrowUpRight size={14}/></a>}<a className={`nav-link ${page === 'settings' ? 'active' : ''}`} href="#settings" aria-current={page === 'settings' ? 'page' : undefined} onClick={() => setMenu(false)}><Settings2 size={18}/><span>系统设置</span></a><button className="nav-link help-link" onClick={() => setHelp(true)}><CircleHelp size={18}/><span>使用帮助</span><ArrowUpRight size={14}/></button></div>
    </aside>
    <div className="main-shell" inert={menu || undefined}><header className="topbar"><div className="breadcrumb"><button ref={menuButton} className="icon-button mobile-menu" onClick={() => setMenu(true)} aria-label="打开导航" aria-expanded={menu} aria-controls="workspace-navigation"><Menu size={20}/></button><Sprout size={16}/><span>工作空间</span><ChevronRight size={13}/><strong>{currentPageName}</strong></div><div className="topbar-actions"><DetectionTaskCenter tasks={tasks} onView={key=>{tasks.select(key);navigate('detect')}}/><span className="crop-theme-indicator" title="在作物检测页切换作物主题"><i/>{activeCrop} · {theme.name}</span><form className="global-search" onSubmit={event => {event.preventDefault(); navigate('records')}}><Search size={15}/><input value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索检测记录…" aria-label="全局搜索检测记录"/><kbd>↵</kbd></form><div className="topbar-divider"/><div className="notification-wrap"><button className={`icon-button notification-button ${notifications ? 'selected' : ''}`} aria-label="通知" aria-expanded={notifications} onClick={() => {setAccountOpen(false); setNotifications(value => !value)}}><Bell size={19}/>{!!data?.dashboard.stats.pending && <i/>}</button>{notifications && <div className="notification-menu"><h3>工作空间通知</h3><div><span className="notification-icon"><FlaskConical size={18}/></span><p><strong>{data?.model.active ? '检测服务已就绪' : '模型等待接入'}</strong><span>{data?.dashboard.stats.pending ?? 0} 份样本等待分析，模型管理中可查看接入进度。</span></p></div><button className="text-button" onClick={() => navigate('models')}>前往模型管理<ArrowRight size={14}/></button></div>}</div>
      <div className="account-wrap" ref={accountArea} onBlur={event => {
        if (!event.currentTarget.contains(event.relatedTarget as Node)) setAccountOpen(false)
      }} onKeyDown={event => {
        if (event.key === 'Escape') {event.stopPropagation(); setAccountOpen(false); accountButton.current?.focus(); return}
        if (event.key === 'Tab') {setAccountOpen(false); accountButton.current?.focus(); return}
        if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
        event.preventDefault()
        if (!accountOpen) {
          setNotifications(false); setAccountOpen(true)
          if (event.key === 'ArrowUp') requestAnimationFrame(() => accountArea.current?.querySelector<HTMLButtonElement>('[role="menuitem"]:last-child')?.focus())
          return
        }
        const items = Array.from(accountArea.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? [])
        const index = items.indexOf(document.activeElement as HTMLButtonElement)
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1
          : event.key === 'ArrowDown' ? (index + 1) % items.length : (index < 0 ? items.length - 1 : (index - 1 + items.length) % items.length)
        items[next]?.focus()
      }}>
        <button ref={accountButton} id="account-toggle" className="topbar-account" aria-label={`账户菜单：${user?.name || '访客'}`} aria-haspopup="menu" aria-expanded={accountOpen} aria-controls="account-menu" onClick={() => {setNotifications(false); setAccountOpen(value => !value)}}>
          <span className="topbar-avatar" aria-hidden="true">{user?.name.charAt(0) || '访'}</span><span className="account-name" title={user?.name || '访客'}>{user?.name || '访客'}</span><ChevronDown size={13} aria-hidden="true"/>
        </button>
        {accountOpen && <div className="account-menu" id="account-menu" role="menu" aria-labelledby="account-toggle">
          <div className="account-menu-heading" role="presentation"><strong>{user?.name || '访客'}</strong><small>{user ? `${user.username} · ${user.role === 'admin' ? '管理员' : '成员'}` : '登录后管理工作空间'}</small></div>
          <button role="menuitem" tabIndex={-1} onClick={() => {navigate('settings'); accountButton.current?.focus()}}><Settings2 size={16}/>个人设置</button>
          {user ? <button role="menuitem" tabIndex={-1} className="account-signout" onClick={() => {setAccountOpen(false); void logout()}}><LogOut size={16}/>退出登录</button>
            : <button role="menuitem" tabIndex={-1} onClick={() => {setAccountOpen(false); window.location.hash = 'login'}}><LogIn size={16}/>登录账号</button>}
        </div>}
      </div></div></header>
      <main className="main-content" id="workspace-content" tabIndex={-1}>
      {client.brand.announcement && <div className="client-announcement" role="status"><Bell size={17}/><p>{client.brand.announcement}</p></div>}
      {error && <div className="error-banner" role="alert"><CircleAlert size={18}/><span>{error}</span><button onClick={reload}>重新连接<RefreshCw size={14}/></button></div>}
      {loading ? <Loading/> : data ? <MotionSurface key={page} page={page}>
        {page === 'dashboard' ? <h1 className="sr-only">总览工作台</h1> : <div className="page-intro"><div><span className="eyebrow">禾观 · 田间工作空间</span><h1>{currentPageName}</h1><p>{({detect:'从一张清晰的照片开始，记录作物的真实变化。', records:'筛选、对照与导出，让每一次观察都有迹可循。', plots:'把照片与土地连接起来，持续关注每一块地。', knowledge:'观察之外，多了解一点作物与养护。', models:'查看识别能力、覆盖范围和服务运行状态。', settings:'调整工作空间，让记录更合你的习惯。'} as Record<string,string>)[page]}</p></div></div>}
        {page === 'dashboard' && <Suspense fallback={<Loading/>}><Dashboard data={data.dashboard} plots={data.plots} period={period} setPeriod={setPeriod} navigate={navigate} onSelect={setSelected} onExport={() => exportRecords(data.records)} onAttention={() => {setRecordStatus('attention'); setSearch(''); navigate('records')}}/></Suspense>}
        {page === 'detect' && <DetectPage plots={data.plots} model={data.model} requireAuth={requireAuth} onChange={reload} toast={toast} tasks={tasks} onViewAdvice={requestAdvice}/>}
        {page === 'records' && <RecordsPage records={data.records} crops={data.model.available_crops} onSelect={setSelected} search={search} setSearch={setSearch} status={recordStatus} setStatus={setRecordStatus}/>}
        {page === 'plots' && (client.features.plots ? <PlotsPage canManage={Boolean(user)} plots={data.plots} crops={data.model.available_crops} draftOwner={user?.username ?? 'guest'} requireAuth={requireAuth} onChange={reload} toast={toast}/> : <section className="panel empty"><h2>地块入口暂未开放</h2><p>请联系管理员调整客户端功能配置。</p></section>)}
        {page === 'knowledge' && (client.features.knowledge ? <KnowledgePage articles={data.articles}/> : <section className="panel empty"><h2>知识入口暂未开放</h2><p>管理员已暂停此入口。</p></section>)}
        {page === 'models' && <ModelsPage model={data.model} health={health}/>}
        {page === 'settings' && <SettingsPage health={health} user={user} onLogin={() => (window.location.hash = 'login')} onLogout={logout}/>}
      </MotionSurface> : !loading && <div className="connection-empty"><img src="/images/xiaohe.png" alt="小禾等待服务连接"/><h1>小禾正在等待工作空间就绪</h1><p>启动后端服务，连接后即可查看地块与检测数据。</p><button className="button primary" onClick={reload}><RefreshCw size={16}/>重新连接</button></div>}
      <footer className="page-footer"><span><img src="/brand/icon.svg" alt="" width="20" height="20"/>{client.brand.app_name} <span className="footer-dot">·</span>{client.brand.tagline}</span><span>用心守护每一份绿意 <Leaf size={12}/></span></footer>
      </main>
    </div>
    <FloatingAssistant key={`${user?.username||'guest'}:${sessionVersion}`} user={user} detectionRequests={detectionRequests} onDetectionHandled={handledDetection} adviceRequest={adviceRequest} onAdviceHandled={handledAdvice}/>
    {toastMessage && <div className="toast" role="status"><Bell size={17}/><span>{toastMessage}</span><button aria-label="关闭提示" onClick={() => setToastMessage('')}><X size={15}/></button></div>}
    {selected && <Modal title="检测样本详情" wide onClose={() => {if (!deleteBusy) {setSelected(null); setDeleteRecord(false)}}}><div className="detection-detail"><div className="detail-image">{selected.image_url ? <SecureImage url={selected.image_url} alt={selected.name}/> : <><CropIcon crop={selected.crop} size={90}/><span>示例样本 · 无原始图片</span></>}</div><div className="detail-info"><div className="detail-title"><h3>{selected.name}</h3><Badge status={selected.status}/></div>{selected.is_demo && <div className="sample-disclaimer"><CircleAlert size={14}/>该条为示例数据，不代表真实检测结果。</div>}<dl><div><dt>作物类型</dt><dd>{selected.crop}</dd></div><div><dt>所属地块</dt><dd>{selected.plot_name}</dd></div><div><dt>检测结果</dt><dd>{selected.result || '等待模型接入'}</dd></div><div><dt>置信度</dt><dd>{confidenceText(selected.confidence)}</dd></div><div><dt>采集时间</dt><dd>{new Date(selected.created_at).toLocaleString('zh-CN')}</dd></div></dl><PredictionScores record={selected}/><div className="detail-note"><span>样本备注</span><p>{selected.note || '暂无备注'}</p></div></div></div>{deleteRecord ? <div className="delete-confirm"><span>确认删除这份样本及原始图片？此操作无法撤销。</span><button className="button outline small" disabled={deleteBusy} onClick={() => setDeleteRecord(false)}>取消</button><button className="button danger small" disabled={deleteBusy} onClick={removeRecord}>{deleteBusy ? '删除中…' : '确认删除'}</button></div> : <div className="detail-actions"><span><ShieldCheck size={14}/>数据已保存至我的账户</span><button className="text-button danger-text" onClick={() => {if (requireAuth()) setDeleteRecord(true)}}><Trash2 size={14}/>删除样本</button></div>}</Modal>}
    {help && <Modal title="开始使用禾观" onClose={() => setHelp(false)}><div className="help-content"><p>用一张照片，开启作物健康管理。</p>{[['管理地块', '添加种植地块、作物与面积，让样本有迹可循。'], ['采集样本', '登录后上传清晰的叶片图片，可关联地块并填写备注。'], ['查看记录', '筛选上传样本，查看详情，或导出 CSV 检测档案。'], ['接入模型', '模型管理页显示当前状态；正式权重接入前仅保存样本。']].map(([title, content], index) => <div key={title}><span>{index + 1}</span><section><h3>{title}</h3><p>{content}</p></section></div>)}<button className="button primary full" onClick={() => {setHelp(false); navigate('detect')}}>开始采集样本<ArrowRight size={16}/></button></div></Modal>}
  </div>
}
