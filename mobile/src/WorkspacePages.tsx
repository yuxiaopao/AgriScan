import {useEffect, useMemo, useRef, useState, type FormEvent} from 'react'
import {ChevronRight, LogOut, Search, ShieldCheck, Sprout, Wifi, X} from 'lucide-react'
import {getServiceBase, normalizeServiceBase, saveServiceBase} from './api'
import {isNativeAndroid} from './native'
import {useClientConfig} from './ClientConfig'
import {Art, Badge, Empty, ErrorNote, LinkRow, SecureImage, Sheet} from './components'
import {FeedbackButton} from './Motion'
import {IpIcon} from './IpIcon'
import {cropThemes} from './cropThemes'
import {confidence, navigate} from './hooks'
import type {Article, Detection, User, Workspace} from './types'
import EmailBinding from './EmailBinding'

const searchText=(value:string)=>value.trim().toLocaleLowerCase('zh-CN')
const pendingStatuses=['awaiting_model','queued','processing']
const recordDescriptions:Record<string,string>={awaiting_model:'已采集，尚无识别结果',queued:'正在等待处理',processing:'正在分析图片',failed:'本次观察未完成'}

export function HomePage({user, data, onDetail}: {user: User; data: Workspace; onDetail: (record: Detection) => void}) {
  const {config}=useClientConfig()
  const [recentExpanded,setRecentExpanded]=useState(false)
  const real=data.records.filter(record=>!record.is_demo)
  const hour=new Date().getHours(),ready=data.model?.status==='ready'
  const cropCount=ready?(data.model?.supported_crops.length??0):(data.model?.available_crops.length??0)
  const modes=[
    {route:'camera',title:'实时相机',text:'边巡田，边查看结果',icon:'camera' as const,enabled:config.features.live_detection},
    {route:'video',title:'视频检测',text:'按时间抽样查看',icon:'video' as const,enabled:config.features.video_detection},
  ]
  return <div className="home-page field-journal-home">
    <div className="home-greeting journal-greeting"><div><p>{new Date().toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'})}</p><h1>{hour<11?'早上好':hour<14?'中午好':hour<18?'下午好':'晚上好'}，{user.name}</h1></div><button className="avatar" onClick={()=>navigate('profile')} aria-label="打开个人中心">{user.name.slice(0,1)}</button></div>
    <section className="home-hero field-journal-hero">
      <img className="field-journal-hero-image" src="/images/field-morning-hero.png" alt="小禾在田间观察叶片的产品插画" draggable={false} onError={event=>{if(!event.currentTarget.src.endsWith('/images/app-hero.webp'))event.currentTarget.src='/images/app-hero.webp'}}/>
      <div className="home-hero-copy"><span className="journal-context"><i className={ready?'ready':''}/>{ready?'小禾的田间观察':config.features.image_detection?'从采集一张照片开始':'图片采集暂时暂停'}</span><h2><span>一片叶子，</span><span>一份生长记录。</span></h2><p>拍清一片叶子，让每次观察有据可查。</p><button className="button primary journal-photo-action" disabled={!config.features.image_detection} onClick={()=>navigate('detect/image')}><IpIcon name="detect"/>{config.features.image_detection?(ready?'开始图片检测':'开始图片采集'):'图片采集暂时暂停'}</button></div>
    </section>
    <div className="journal-secondary-modes" role="group" aria-label="其他观察方式">{modes.map(mode=><button key={mode.route} type="button" disabled={!mode.enabled||!ready} onClick={()=>navigate(`detect/${mode.route}`)}><span className="journal-mode-icon"><IpIcon name={mode.icon}/></span><span><strong>{mode.title}</strong><small>{!mode.enabled?'管理员已暂停':!ready?'需启用识别模型':mode.text}</small></span></button>)}</div>
    {!ready&&<p className="journal-service-note">{data.model?(config.features.image_detection?'识别模型尚未启用，照片会先保存为采集记录。':'图片采集暂时暂停，仍可回看已有观察。'):'暂时未能确认服务状态，请稍后刷新。'}</p>}
    <section className="journal-data-strip" aria-label="我的田间档案"><div><strong>{real.length}</strong><span>份观察记录</span></div><div><strong>{data.plots.length}</strong><span>块种植地</span></div><div><strong>{data.model?cropCount:'—'}</strong><span>{ready?'种可识别作物':config.features.image_detection?'种可采集作物':'种已配置作物'}</span></div></section>
    <nav className="journal-tools" aria-label="田间快捷入口"><button type="button" onClick={()=>navigate('records')}><span className="journal-tool-icon"><IpIcon name="records"/></span><strong>观察记录</strong><small>照片与结果</small></button><button type="button" disabled={!config.features.plots} onClick={()=>navigate('plots')}><span className="journal-tool-icon"><IpIcon name="plots"/></span><strong>地块档案</strong><small>{config.features.plots?'按位置回看':'暂时暂停'}</small></button><button type="button" disabled={!config.features.knowledge} onClick={()=>navigate('knowledge')}><span className="journal-tool-icon"><IpIcon name="knowledge"/></span><strong>田间笔记</strong><small>{config.features.knowledge?'病害与养护':'暂时暂停'}</small></button></nav>
    <section className="journal-recent-section"><div className="section-heading journal-section-heading"><div><span>你的田间时间线</span><h2>最近的观察</h2></div>{real.length>1?<button className="stack-control" aria-expanded={recentExpanded} aria-controls="recent-observations" onClick={()=>setRecentExpanded(value=>!value)}>{recentExpanded?'收起':`展开 ${Math.min(real.length,3)} 份`}</button>:<button onClick={()=>navigate('records')}>全部记录</button>}</div>
      {real.length?<div data-count={Math.min(real.length,3)} className={`recent-stack ${!recentExpanded&&real.length>1?'is-folded':''}`}><div id="recent-observations" className="record-list">{real.slice(0,recentExpanded?3:1).map(record=><RecordCard key={record.id} record={record} onClick={()=>onDetail(record)}/>)}</div>{recentExpanded&&<button className="text-button full" onClick={()=>navigate('records')}>查看全部观察</button>}</div>:<Empty title="第一份记录，从这里生长" text="拍下一张叶片照片，之后可以在这里对照变化。"/>}
    </section>
    <p className="home-footer"><Sprout size={15}/>把观察留住，把生长读懂。</p>
  </div>
}
export function RecordCard({record,onClick}:{record:Detection;onClick:()=>void}) {return <button className="record-card journal-record" onClick={onClick}>{record.image_url?<SecureImage url={record.image_url} alt={`${record.crop}样本`} className="record-thumb"/>:<span className="record-thumb record-leaf"><IpIcon name="records"/></span>}<span className="record-copy"><strong>{record.crop}<Badge status={record.status}/></strong><span>{record.result||recordDescriptions[record.status]||'尚无识别结果'}</span><small>{new Date(record.created_at).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})} · {record.is_demo?'示例样本':record.plot_name||'未关联地块'}</small></span><span className="record-score">{record.confidence==null?'查看':confidence(record.confidence)}<ChevronRight size={15}/></span></button>}
export function RecordsPage({records,onDetail,onRefresh,loading}:{records:Detection[];onDetail:(record:Detection)=>void;onRefresh:()=>void;loading:boolean}) {
  const {config}=useClientConfig()
  const [search,setSearch]=useState('');const [status,setStatus]=useState('');const [demo,setDemo]=useState(false)
  const keyword=searchText(search),hasFilters=Boolean(keyword||status)
  const filtered=records.filter(record=>(demo||!record.is_demo)&&(!status||(status==='pending'?pendingStatuses.includes(record.status):record.status===status))&&searchText(`${record.name} ${record.crop} ${record.result||''} ${record.plot_name} ${record.note||''}`).includes(keyword))
  const clearFilters=()=>{setSearch('');setStatus('')}
  return <div><div className="page-intro journal-page-intro"><h1>观察记录</h1><p>回看照片与结果，接着上次的观察。</p></div><div className="search-field"><Search size={18}/><input aria-label="搜索检测记录" value={search} onChange={event=>setSearch(event.target.value)} placeholder="搜索作物、地块或病害"/>{search&&<button type="button" className="icon-button" aria-label="清除记录搜索" onClick={()=>setSearch('')}><X size={17}/></button>}</div>
    <div className="filter-chips scroll-chips" role="group" aria-label="筛选检测状态">{[['','全部'],['healthy','健康'],['attention','需关注'],['pending','未出结果'],['failed','未完成']].map(([value,label])=><button key={value} aria-pressed={status===value} className={status===value?'active':''} onClick={()=>setStatus(value)}>{label}</button>)}</div>
    <div className="records-caption records-filter-summary"><span aria-live="polite">{hasFilters?'找到':'共'} {filtered.length} 份观察</span><div>{hasFilters&&filtered.length>0&&<button className="text-button filter-reset" onClick={clearFilters}>清除筛选</button>}<button className="text-button" onClick={onRefresh} disabled={loading}>{loading?'正在刷新…':'刷新'}</button></div></div>
    {filtered.length?<div className="record-list">{filtered.map(record=><RecordCard key={record.id} record={record} onClick={()=>onDetail(record)}/>)}</div>:hasFilters?<Empty title="没有匹配的观察" text="换个关键词，或清除筛选后查看现有记录。" action={<button className="button outline" onClick={clearFilters}>清除筛选</button>}/>:<Empty title="还没有保存的观察" text={config.features.image_detection?'采集一张叶片照片，记录将保存在这里。':'图片采集暂时暂停，可返回首页查看其他观察方式。'} action={<button className="button outline" onClick={()=>navigate(config.features.image_detection?'detect/image':'home')}>{config.features.image_detection?'开始图片观察':'返回首页'}</button>}/>}
    <label className="checkbox-line"><input type="checkbox" checked={demo} onChange={event=>setDemo(event.target.checked)}/>同时显示示例数据</label></div>
}
export {default as PlotsPage} from './PlotsPage'
export function KnowledgePage({articles}:{articles:Article[]}) {
  const {config}=useClientConfig();const [search,setSearch]=useState('');const [crop,setCrop]=useState('');const [selected,setSelected]=useState<Article|null>(null)
  const crops=useMemo(()=>[...new Set(articles.map(article=>article.crop).filter(Boolean))],[articles]);const keyword=searchText(search),hasFilters=Boolean(keyword||crop);const filtered=articles.filter(article=>(!crop||article.crop===crop)&&searchText(`${article.title} ${article.summary} ${article.content} ${article.crop}`).includes(keyword))
  if(!config.features.knowledge)return <Empty title="田间笔记已暂停" text="管理员暂时关闭了知识入口，你仍可查看已有的观察记录。"/>
  return <div><section className="knowledge-hero field-notes-hero"><div className="field-notes-hero-copy"><span>田间笔记</span><h1>把叶片读懂，<br/>把田地照顾好。</h1><p>从叶色、纹理到日常养护。</p></div><img src="/images/field-notes-macro.png" alt="" aria-hidden="true" draggable={false} onError={event=>{event.currentTarget.style.display='none'}}/></section><div className="search-field"><Search size={18}/><input aria-label="搜索农业知识" placeholder="搜索病害、作物与养护知识" value={search} onChange={event=>setSearch(event.target.value)}/></div><div className="filter-chips scroll-chips" role="group" aria-label="筛选笔记作物">{['',...crops].map(value=><button key={value} aria-pressed={value===crop} className={crop===value?'active':''} onClick={()=>setCrop(value)}>{value||'全部笔记'}</button>)}</div><div className="article-list">{filtered.map((article,index)=><button key={article.id} className="article-card journal-article" onClick={()=>setSelected(article)}><div className={`article-mark mark-${index%3}`}><Art src={cropThemes[article.crop]?"/images/crops/"+cropThemes[article.crop].id+"-still.webp":"/images/ip-icons/knowledge.webp"} alt="" className="article-crop-ip"/><span>{article.crop||'通用'}</span></div><span><small>{article.category}</small><strong>{article.title}</strong><p>{article.summary}</p></span><ChevronRight size={17}/></button>)}</div>{!filtered.length&&(hasFilters?<Empty title="没有匹配的笔记" text="换个关键词，或清除作物与搜索条件。" action={<button className="button outline" onClick={()=>{setSearch('');setCrop('')}}>清除筛选</button>}/>:<Empty title="暂时没有已发布的笔记" text="之后发布的种植与养护知识，会整理在这里。"/>)}<button className="button outline full" disabled={!config.features.assistant} onClick={()=>navigate('assistant')}><IpIcon name="profile"/>{config.features.assistant?'把问题带给小禾':'小禾新问答暂时暂停'}</button>{selected&&<Sheet title="田间笔记" onClose={()=>setSelected(null)}><article className="article-detail"><span className="badge healthy">{selected.crop||'通用'} · {selected.category}</span><h1>{selected.title}</h1><p className="article-summary">{selected.summary}</p>{selected.content.split('\n').filter(Boolean).map((paragraph,index)=><p key={index}>{paragraph}</p>)}{selected.sources?.map(source=><a key={source.url} href={source.url} target="_blank" rel="noreferrer">{source.title}</a>)}<p className="fine-print">用于一般种植学习，实际病害请结合现场情况由农技人员确认。</p></article></Sheet>}</div>
}
export function ProfilePage({user,data,onLogout}:{user:User;data:Workspace;onLogout:()=>void}) {
  const {config}=useClientConfig();const ready=data.model?.status==='ready';const cropCount=ready?(data.model?.supported_crops.length??0):(data.model?.available_crops.length??0)
  return <div><div className="profile-hero journal-profile-hero"><span className="journal-page-label">我的田间账户</span><div className="profile-avatar">{user.name.slice(0,1)}</div><h1>{user.name}</h1><p>@{user.username}<span>{user.role==='admin'?'管理员':'田间伙伴'}</span></p></div><div className="profile-stats journal-profile-stats"><span><strong>{data.records.filter(record=>!record.is_demo).length}</strong>我的观察记录</span><span><strong>{data.plots.length}</strong>我的地块</span><span><strong>{data.model?cropCount:'—'}</strong>{ready?'可识别作物':data.model?(config.features.image_detection?'可采集作物':'已配置作物'):'状态待确认'}</span></div><div className="card profile-links journal-profile-links"><LinkRow icon={<IpIcon name="plots"/>} title="地块档案" description={config.features.plots?'创建地块、补充封面与回看观察':'当前仅可查看已有地块'} onClick={()=>navigate('plots')}/><LinkRow icon={<IpIcon name="knowledge"/>} title="田间笔记" disabled={!config.features.knowledge} description={config.features.knowledge?'病害知识与日常养护':'管理员已暂停知识入口'} onClick={()=>navigate('knowledge')}/><LinkRow icon={<IpIcon name="profile"/>} title="我的小禾对话" description={config.features.assistant?'继续你的私人对话':'新问答暂停，历史仍可阅读'} onClick={()=>navigate('assistant')}/><LinkRow icon={<IpIcon name="records"/>} title="我的检测任务" description="上传进度、处理状态与任务结果" onClick={()=>navigate('tasks')}/><LinkRow icon={<IpIcon name="detect"/>} title="识别服务" description={data.model?.active?.pipeline==='detection_with_classification'?'目标检测与整图分类复核':'查看识别模型与覆盖范围'} onClick={()=>navigate('models')}/><LinkRow icon={<IpIcon name="settings"/>} title="账户与连接" description="服务地址、界面与应用信息" onClick={()=>navigate('settings')}/></div><div className="privacy-note"><ShieldCheck size={18}/><p>观察记录和小禾对话按账户保存，管理员通过独立管理端维护服务。</p></div><button className="button ghost full logout-button" onClick={onLogout}><LogOut size={17}/>退出当前账户</button><p className="version-note">禾观 AgriScan · 随身巡田</p></div>
}
function validateServiceAddress(value:string) {
  const base=normalizeServiceBase(value)
  if(isNativeAndroid()) {
    if(!base)throw new Error('请填写手机能够访问的服务地址。')
    if(['localhost','127.0.0.1','[::1]'].includes(new URL(base).hostname))throw new Error('手机无法通过 localhost 访问电脑，请填写电脑局域网地址或服务器域名。')
  }
  return base
}
export function ServiceSettings({onSaved,user,onLogout}:{onSaved:()=>void;user:User|null;onLogout?:()=>void}) {
  const [value,setValue]=useState(getServiceBase());const [error,setError]=useState('');const [message,setMessage]=useState('');const [testing,setTesting]=useState(false);const [notice,setNotice]=useState('')
  const [motion,setMotion]=useState(localStorage.getItem('agriscan-mobile-motion')!=='false')
  const testVersion=useRef(0);const testController=useRef<AbortController|null>(null);const currentBase=getServiceBase()
  const changed=(()=>{try{return normalizeServiceBase(value)!==currentBase}catch{return true}})()
  useEffect(()=>()=>{testVersion.current++;testController.current?.abort()},[])
  function edit(next:string){testVersion.current++;testController.current?.abort();testController.current=null;setTesting(false);setValue(next);setMessage('');setError('');setNotice('')}
  async function test() {
    if(testController.current)return
    setError('');setMessage('');setNotice('')
    let base:string
    try{base=validateServiceAddress(value)}catch(reason){setError((reason as Error).message);return}
    const version=++testVersion.current,controller=new AbortController();testController.current=controller;setTesting(true)
    try {
      // This public probe must never attach the saved account token to a new address.
      const response=await fetch(`${base}/api/health`,{headers:{Accept:'application/json'},credentials:'omit',cache:'no-store',redirect:'error',signal:AbortSignal.any([controller.signal,AbortSignal.timeout(10000)])})
      if(!response.ok)throw new Error(`服务检查未通过（${response.status}），请确认地址后重试。`)
      const health:{status?:string;model?:string}=await response.json().catch(()=>{throw new Error('这个地址未返回有效的服务状态，请确认完整服务路径。')})
      if(!health||health.status!=='ok'||typeof health.model!=='string')throw new Error('这个地址未返回禾观服务状态，请确认地址中包含正确的服务路径。')
      if(testVersion.current===version)setMessage(`${base===currentBase?'当前服务连接正常':'此地址可以连接，保存后即可登录'}，${health.model==='ready'?'识别模型已就绪':'识别模型尚未启用'}。`)
    } catch(reason) {
      if(testVersion.current!==version||controller.signal.aborted)return
      setError(reason instanceof DOMException&&reason.name==='TimeoutError'?'连接检查超时，请确认服务已启动并检查网络。':reason instanceof TypeError?'无法连接此地址，请检查地址、网络以及服务是否允许访问。':(reason as Error).message)
    } finally {if(testController.current===controller)testController.current=null;if(testVersion.current===version)setTesting(false)}
  }
  function save(event:FormEvent){event.preventDefault();if(testing)return;setError('');setNotice('');try{const base=validateServiceAddress(value);if(base===currentBase){setNotice('服务地址未改变，当前登录状态已保留。');return}saveServiceBase(base);onSaved()}catch(reason){setError((reason as Error).message)}}
  return <div className="settings-page"><div className="page-intro"><h1>账户与连接</h1><p>查看当前账户，调整服务连接与界面偏好。</p></div>{user&&<div className="settings-account"><span className="avatar">{user.name.slice(0,1)}</span><div><strong>{user.name}</strong><p>{user.role==='admin'?'管理员':'田间伙伴'} · @{user.username}</p></div><ShieldCheck size={20}/></div>}
    {user&&<EmailBinding key={`${currentBase}:${user.username}`}/>}
    <form className="card settings-service" onSubmit={save} noValidate><div className="section-heading"><h2><IpIcon name="settings"/>服务连接</h2><Wifi size={17}/></div><div className="service-current"><span>当前服务</span><strong>{currentBase||(isNativeAndroid()?'尚未配置':'本地代理')}</strong></div>
      <label>服务地址<input type="url" inputMode="url" value={value} onChange={event=>edit(event.target.value)} placeholder="例如 https://agriscan.example.com" autoCapitalize="none" autoCorrect="off" spellCheck={false}/></label>
      <details className="service-help"><summary>如何填写服务地址</summary><p>{isNativeAndroid()?'填写手机能访问的服务器或电脑局域网地址。手机上的 localhost 指向手机本身。':'留空使用本地代理；连接其他服务时，填写完整地址和服务路径。'}</p></details>
      <ErrorNote message={error}/>{message&&<p className="success-note" role="status">{message}</p>}{notice&&<p className="settings-save-note" role="status">{notice}</p>}
      <div className="settings-buttons"><FeedbackButton type="button" className="outline" onClick={test} busy={testing} busyLabel="正在检查地址" complete={!!message} completeLabel="连接检查通过">检查此地址</FeedbackButton><button className="button primary" disabled={testing||!changed}>{changed?'保存并重新登录':'当前地址已保存'}</button></div>
      <small className="settings-save-note">{changed?'保存后将切换服务并重新登录，当前账户的令牌不会发送到新地址。':'检查连接不会修改地址，也不会退出当前账户。'}</small>
    </form>
    <section className="card settings-preferences"><h2>界面偏好</h2><div><span><strong>界面动效</strong><small>同时遵循系统的减少动态效果设置</small></span><button className={`toggle ${motion?'on':''}`} role="switch" aria-checked={motion} aria-label="界面动效" onClick={()=>{const next=!motion;setMotion(next);localStorage.setItem('agriscan-mobile-motion',String(next));document.documentElement.classList.toggle('reduce-motion',!next)}}><i/></button></div></section>
    {onLogout&&<button className="button ghost full logout-button" onClick={onLogout}><LogOut size={17}/>退出当前账户</button>}<p className="version-note">禾观 AgriScan · 随身巡田<br/>连接好服务，再开始新的观察。</p></div>
}
