import {confidenceText, PredictionScores} from './PredictionScores'
import {lazy, Suspense, useCallback, useEffect, useState} from 'react'
import {ArrowRight, ArrowUpRight, Bell, BookOpen, ChevronDown, ChevronRight, CircleAlert, CircleHelp, FlaskConical, LayoutDashboard, Leaf, Map, Menu, RefreshCw, ScanLine, Search, Settings2, ShieldCheck, Sprout, Trash2, X, History} from 'lucide-react'
import Access from './Access'
import FloatingAssistant from './FloatingAssistant'
import {IntegrationSettings, WeightManager} from './Integrations'
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
  {page: 'models', name: '模型管理', icon: FlaskConical},
] as const
const Dashboard = lazy(() => import('./Dashboard'))
const pageFromHash = (): Page => {
  const hash = window.location.hash.slice(1)
  return [...navigation.map(item => item.page), 'settings'].includes(hash as Page) ? hash as Page : 'dashboard'
}
const accessFromHash = () => {const hash = window.location.hash.slice(1); return !hash ? 'welcome' : ['welcome', 'login', 'register'].includes(hash) ? hash : ''}
interface Resources {dashboard: DashboardData; records: Detection[]; plots: Plot[]; articles: Article[]; model: ModelInfo}

export default function App() {
  const [accessPage, setAccessPage] = useState(accessFromHash)
  const [page, setPage] = useState<Page>(pageFromHash)
  const [data, setData] = useState<Resources | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [period, setPeriod] = useState(7)
  const [refresh, setRefresh] = useState(0)
  const [user, setUser] = useState<User | null>(null)
  const [detectionRequests, setDetectionRequests] = useState<Detection[]>([])
  const queueDetection = useCallback((record: Detection) => setDetectionRequests(old => [...old, record]), [])
  const handledDetection = useCallback((id: string) => setDetectionRequests(old => old.filter(record => record.id !== id)), [])
  const [search, setSearch] = useState('')
  const [recordStatus, setRecordStatus] = useState('')
  const [toastMessage, setToastMessage] = useState('')
  const [menu, setMenu] = useState(false)
  const [notifications, setNotifications] = useState(false)
  const [help, setHelp] = useState(false)
  const [selected, setSelected] = useState<Detection | null>(null)
  const [deleteRecord, setDeleteRecord] = useState(false)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const reload = useCallback(() => setRefresh(value => value + 1), [])
  const toast = useCallback((message: string) => setToastMessage(message), [])
  const navigate = (next: Page) => {window.location.hash = next; setMenu(false); setNotifications(false)}
  const requireAuth = () => {if (user && getToken()) return true; setSelected(null); setDeleteRecord(false); (window.location.hash = 'login'); return false}

  useEffect(() => {
    const onHash = () => {setPage(pageFromHash()); setAccessPage(accessFromHash()); window.scrollTo({top: 0, behavior: 'instant'})}
    const expired = () => {setUser(null); setDetectionRequests([]); (window.location.hash = 'login')}
    const dismiss = (event: KeyboardEvent) => {if (event.key === 'Escape') {setMenu(false); setNotifications(false)}}
    window.addEventListener('hashchange', onHash)
    window.addEventListener('agriscan-auth-expired', expired)
    window.addEventListener('keydown', dismiss)
    document.documentElement.classList.toggle('compact', localStorage.getItem('agriscan-compact') === 'true')
    document.documentElement.classList.toggle('reduce-motion', localStorage.getItem('agriscan-motion') === 'false')
    if (getToken()) api<User>('/auth/me').then(setUser).catch(() => setUser(null))
    return () => {window.removeEventListener('hashchange', onHash); window.removeEventListener('agriscan-auth-expired', expired); window.removeEventListener('keydown', dismiss)}
  }, [])
  useEffect(() => {
    if (accessPage) return
    let current = true
    setError('')
    if (!data) setLoading(true)
    api<Health>('/health').then(value => {if (current) setHealth(value)}).catch(() => {if (current) setHealth(null)})
    Promise.all([
      api<DashboardData>(`/dashboard?days=${period}`),
      api<Detection[]>('/detections'),
      api<Plot[]>('/plots'),
      api<Article[]>('/knowledge'),
      api<ModelInfo>('/models'),
    ]).then(([dashboard, records, plots, articles, model]) => {if (current) setData({dashboard, records, plots, articles, model})}).catch(e => {if (current) setError((e as Error).message)}).finally(() => {if (current) setLoading(false)})
    return () => {current = false}
    // Data remains visible during refresh; only inputs below trigger a request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refresh, period, accessPage])
  useEffect(() => {if (!toastMessage) return; const timer = setTimeout(() => setToastMessage(''), 5000); return () => clearTimeout(timer)}, [toastMessage])
  useEffect(() => {document.title = `${accessPage ? ({welcome:'欢迎来到禾观',login:'登录',register:'创建账户'}[accessPage]) : navigation.find(item => item.page === page)?.name ?? '系统设置'} · AgriScan 禾观`}, [page, accessPage])
  async function logout() {
    try {await api('/auth/logout', {method: 'POST'})}
    catch (e) {toast((e as Error).message); return}
    setToken(null); setUser(null); setData(null); setDetectionRequests([]); window.location.hash = 'welcome'; reload(); toast('已退出登录。')
  }
  async function removeRecord() {
    if (!selected) return
    setDeleteBusy(true)
    try {await api(`/detections/${selected.id}`, {method: 'DELETE'}); setSelected(null); setDeleteRecord(false); reload(); toast('检测样本已删除。')}
    catch (e) {toast((e as Error).message)}
    finally {setDeleteBusy(false)}
  }
  const currentPageName = navigation.find(item => item.page === page)?.name ?? '系统设置'
  const today = new Date().toLocaleDateString('zh-CN', {month: 'long', day: 'numeric', weekday: 'long'})
  if (accessPage) return <Access page={accessPage} onLogin={value => {setUser(value); window.location.hash = 'dashboard'; reload()}}/>
  return <div className="app-shell">
    {menu && <button className="sidebar-scrim" aria-label="关闭导航" onClick={() => setMenu(false)}/>}
    <aside className={`sidebar ${menu ? 'open' : ''}`}>
      <a className="brand" href="#dashboard" onClick={() => setMenu(false)}><span className="brand-mark"><Sprout size={25} strokeWidth={1.8}/></span><span><strong>AgriScan<span>禾观</span></strong><small>看见生长的力量</small></span></a>
      <div className="workspace-name"><span className="workspace-avatar"><Leaf size={17}/></span><span><strong>智慧农业工作空间</strong><small>AGRICULTURE WORKSPACE</small></span><span className="workspace-dot"/></div>
      <div className="nav-section-title">工作空间<span>WORKSPACE</span></div>
      <nav aria-label="主导航">{navigation.map(item => <a key={item.page} href={`#${item.page}`} className={`nav-link ${page === item.page ? 'active' : ''}`} aria-current={page === item.page ? 'page' : undefined} onClick={() => setMenu(false)}><item.icon size={18} strokeWidth={1.7}/><span>{item.name}</span>{item.page === 'detect' ? <span className="nav-ai">AI</span> : page === item.page ? <span className="nav-dot"/> : null}</a>)}</nav>
      <div className="sidebar-bottom"><div className="side-note"><div className="side-note-icon"><Sprout size={18}/><span className="side-note-star">✦</span></div><strong>让种植，更有底气。</strong><p>小禾陪你观察每一片叶子，<br/>记录田间每一天的变化。</p><button onClick={() => navigate('knowledge')}>一起学点新知识 <ArrowUpRight size={14}/></button></div><a className={`nav-link ${page === 'settings' ? 'active' : ''}`} href="#settings" onClick={() => setMenu(false)}><Settings2 size={18}/><span>系统设置</span></a><button className="nav-link help-link" onClick={() => setHelp(true)}><CircleHelp size={18}/><span>使用帮助</span><ArrowUpRight size={14}/></button><button className="user-profile" onClick={() => user ? navigate('settings') : (window.location.hash = 'login')}><span className="avatar">{user?.name.charAt(0) || '访'}</span><span><strong>{user?.name || '欢迎来到禾观'}</strong><small>{user ? `农业工作空间 · ${user.role === 'admin' ? '管理员' : '成员'}` : '登录后开始管理'}</small></span><ChevronDown size={14}/></button></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-menu" onClick={() => setMenu(true)} aria-label="打开导航"><Menu size={20}/></button><Sprout size={16}/><span>工作空间</span><ChevronRight size={13}/><strong>{currentPageName}</strong></div><div className="topbar-actions"><form className="global-search" onSubmit={event => {event.preventDefault(); navigate('records')}}><Search size={15}/><input value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索检测记录…" aria-label="全局搜索检测记录"/><kbd>↵</kbd></form><div className="topbar-divider"/><div className="notification-wrap"><button className={`icon-button notification-button ${notifications ? 'selected' : ''}`} aria-label="通知" aria-expanded={notifications} onClick={() => setNotifications(value => !value)}><Bell size={19}/>{!!data?.dashboard.stats.pending && <i/>}</button>{notifications && <div className="notification-menu"><h3>工作空间通知</h3><div><span className="notification-icon"><FlaskConical size={18}/></span><p><strong>{data?.model.active ? '检测服务已就绪' : '模型等待接入'}</strong><span>{data?.dashboard.stats.pending ?? 0} 份样本等待分析，模型管理中可查看接入进度。</span></p></div><button className="text-button" onClick={() => navigate('models')}>前往模型管理<ArrowRight size={14}/></button></div>}</div><button className="topbar-avatar" onClick={() => user ? navigate('settings') : (window.location.hash = 'login')} aria-label={user ? '账户设置' : '登录'}>{user?.name.charAt(0) || '禾'}</button></div></header>
      <main className="main-content"><div className="context-line"><span><span className={`live-dot ${health ? '' : 'offline'}`}/>{health ? '工作空间已连接' : '正在连接工作空间'}<span className="context-divider">/</span><span className="demo-mode">{health?.mode === 'demo' ? '演示工作空间' : '农业检测系统'}</span></span><span className="today">{today}<button className="icon-button" onClick={reload} aria-label="刷新数据"><RefreshCw size={13}/></button></span></div>
      {error && <div className="error-banner" role="alert"><CircleAlert size={18}/><span>{error}</span><button onClick={reload}>重新连接<RefreshCw size={14}/></button></div>}
      {loading ? <Loading/> : data ? <>
        {page === 'dashboard' && <Suspense fallback={<Loading/>}><Dashboard data={data.dashboard} plots={data.plots} period={period} setPeriod={setPeriod} navigate={navigate} onSelect={setSelected} onExport={() => exportRecords(data.records)} onAttention={() => {setRecordStatus('attention'); setSearch(''); navigate('records')}}/></Suspense>}
        {page === 'detect' && <DetectPage plots={data.plots} model={data.model} requireAuth={requireAuth} onChange={reload} toast={toast} onDetected={queueDetection}/>}
        {page === 'records' && <RecordsPage records={data.records} crops={data.model.available_crops} onSelect={setSelected} search={search} setSearch={setSearch} status={recordStatus} setStatus={setRecordStatus}/>}
        {page === 'plots' && <PlotsPage plots={data.plots} crops={data.model.available_crops} requireAuth={requireAuth} onChange={reload} toast={toast}/>}
        {page === 'knowledge' && <KnowledgePage articles={data.articles}/>}
        {page === 'models' && <ModelsPage model={data.model} health={health}><WeightManager onChange={reload} canManage={user?.role === 'admin'}/></ModelsPage>}
        {page === 'settings' && <><SettingsPage health={health} user={user} onLogin={() => (window.location.hash = 'login')} onLogout={logout}/>{user?.role === 'admin' && <IntegrationSettings/>}</>}
      </> : !loading && <div className="connection-empty"><img src="/images/xiaohe.png" alt="小禾等待服务连接"/><h1>小禾正在等待工作空间就绪</h1><p>启动后端服务，连接后即可查看地块与检测数据。</p><button className="button primary" onClick={reload}><RefreshCw size={16}/>重新连接</button></div>}
      <footer className="page-footer"><span><Sprout size={14}/>AgriScan 禾观 <span className="footer-dot">·</span>让科技扎根，让生长可见</span><span>用心守护每一份绿意 <Leaf size={12}/></span></footer>
      </main>
    </div>
    <FloatingAssistant key={user?.username || 'guest'} user={user} detectionRequests={detectionRequests} onDetectionHandled={handledDetection}/>
    {toastMessage && <div className="toast" role="status"><CircleAlert size={17}/><span>{toastMessage}</span><button aria-label="关闭提示" onClick={() => setToastMessage('')}><X size={15}/></button></div>}
    {selected && <Modal title="检测样本详情" wide onClose={() => {if (!deleteBusy) {setSelected(null); setDeleteRecord(false)}}}><div className="detection-detail"><div className="detail-image">{selected.image_url ? <SecureImage url={selected.image_url} alt={selected.name}/> : <><CropIcon crop={selected.crop} size={90}/><span>示例样本 · 无原始图片</span></>}</div><div className="detail-info"><div className="detail-title"><h3>{selected.name}</h3><Badge status={selected.status}/></div>{selected.is_demo && <div className="sample-disclaimer"><CircleAlert size={14}/>该条为示例数据，不代表真实检测结果。</div>}<dl><div><dt>作物类型</dt><dd>{selected.crop}</dd></div><div><dt>所属地块</dt><dd>{selected.plot_name}</dd></div><div><dt>检测结果</dt><dd>{selected.result || '等待模型接入'}</dd></div><div><dt>置信度</dt><dd>{confidenceText(selected.confidence)}</dd></div><div><dt>采集时间</dt><dd>{new Date(selected.created_at).toLocaleString('zh-CN')}</dd></div></dl><PredictionScores record={selected}/><div className="detail-note"><span>样本备注</span><p>{selected.note || '暂无备注'}</p></div></div></div>{deleteRecord ? <div className="delete-confirm"><span>确认删除这份样本及原始图片？此操作无法撤销。</span><button className="button outline small" disabled={deleteBusy} onClick={() => setDeleteRecord(false)}>取消</button><button className="button danger small" disabled={deleteBusy} onClick={removeRecord}>{deleteBusy ? '删除中…' : '确认删除'}</button></div> : <div className="detail-actions"><span><ShieldCheck size={14}/>数据已保存至工作空间</span><button className="text-button danger-text" onClick={() => {if (requireAuth()) setDeleteRecord(true)}}><Trash2 size={14}/>删除样本</button></div>}</Modal>}
    {help && <Modal title="开始使用禾观" onClose={() => setHelp(false)}><div className="help-content"><p>用一张照片，开启作物健康管理。</p>{[['管理地块', '添加种植地块、作物与面积，让样本有迹可循。'], ['采集样本', '登录后上传清晰的叶片图片，可关联地块并填写备注。'], ['查看记录', '筛选上传样本，查看详情，或导出 CSV 检测档案。'], ['接入模型', '模型管理页显示当前状态；正式权重接入前仅保存样本。']].map(([title, content], index) => <div key={title}><span>{index + 1}</span><section><h3>{title}</h3><p>{content}</p></section></div>)}<button className="button primary full" onClick={() => {setHelp(false); navigate('detect')}}>开始采集样本<ArrowRight size={16}/></button></div></Modal>}
  </div>
}
