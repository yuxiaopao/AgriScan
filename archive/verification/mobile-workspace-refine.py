from pathlib import Path

path = Path('E:/AgriScan/mobile/src/WorkspacePages.tsx')
s = path.read_text(encoding='utf-8')

def replace(old, new):
    global s
    if old not in s:
        raise RuntimeError('Source target missing: ' + old[:90])
    s = s.replace(old, new)

replace("import {useMemo, useState, type FormEvent}", "import {useEffect, useMemo, useRef, useState, type FormEvent}")
replace('ArrowRight, BookOpen,', 'BookOpen,')
replace('Sprout, Wifi}', 'Sprout, Wifi, X}')
replace("import {api, getServiceBase, saveServiceBase} from './api'", "import {getServiceBase, normalizeServiceBase, saveServiceBase} from './api'")
replace("import type {Article, Detection, Plot, User, Workspace} from './types'", "import type {Article, Detection, Plot, User, Workspace} from './types'\n\nconst searchText=(value:string)=>value.trim().toLocaleLowerCase('zh-CN')\nconst pendingStatuses=['awaiting_model','queued','processing']")
replace("const real = data.records.filter(record => !record.is_demo); const hour = new Date().getHours()", "const real = data.records.filter(record => !record.is_demo); const hour = new Date().getHours(); const ready=data.model?.status==='ready'; const cropCount=ready?(data.model?.supported_crops.length??0):(data.model?.available_crops.length??0)")
replace('YOUR LITTLE FIELD COMPANION', '小禾陪你，认真观察')
replace('小禾已准备好，陪你认真观察。', '拍下一片叶子，留住田间的变化。')
replace('开始一份观察<ArrowRight size={16}/>', "{config.features.image_detection?(ready?'开始图片检测':'开始图片采集'):'图片采集暂时暂停'}")
replace('用你顺手的方式', '开始一次观察')
replace('观察，从这里开始', '选择适合的方式')
replace("{route:'image',title:'拍照识别',text:'一片叶，一份观察',icon:ImagePlus}", "{route:'image',title:ready?'图片检测':'图片采集',text:'拍照或从相册选择',icon:ImagePlus}")
replace("{route:'camera',title:'实时相机',text:'走近叶片，随手巡田',icon:Camera}", "{route:'camera',title:'实时相机',text:'边巡田，边查看结果',icon:Camera}")
replace("{route:'video',title:'视频观察',text:'沿着时间，发现变化',icon:Film}", "{route:'video',title:'视频检测',text:'按时间抽样查看',icon:Film}")
replace("disabled={!config.features[item.route==='image'?'image_detection':item.route==='video'?'video_detection':'live_detection']}", "disabled={!config.features[item.route==='image'?'image_detection':item.route==='video'?'video_detection':'live_detection']||(item.route!=='image'&&!ready)}")
replace("{config.features[item.route==='image'?'image_detection':item.route==='video'?'video_detection':'live_detection']?item.text:'管理员已暂停'}", "{!config.features[item.route==='image'?'image_detection':item.route==='video'?'video_detection':'live_detection']?'管理员已暂停':item.route!=='image'&&!ready?'需启用识别模型':item.text}")
replace("<div className=\"workspace-strip\"><span><i className={data.model?.status==='ready'?'ready':''}/>{data.model?.status==='ready'?'叶片识别已就绪':'样本采集已就绪'}</span><strong>{data.model?.supported_crops.length || 0}<small>种作物</small></strong></div>", "<div className=\"workspace-strip home-overview\"><span><i className={ready?'ready':''}/>{ready?'识别模型已就绪':data.model?'当前为样本采集模式':'服务状态待确认'}</span><strong>{cropCount>0?<>{cropCount}<small>{ready?'种作物可识别':'种作物可采集'}</small></>:<small>{data.model?'等待配置作物范围':'请刷新服务状态'}</small>}</strong></div>{!ready&&data.model&&<p className=\"home-model-note field-hint\">当前可保存照片和采样备注；模型启用前，不会生成病害判断。</p>}")
replace('<strong>小禾田间笔记</strong><span>读懂叶片，积累种植经验</span>', "<strong>田间笔记</strong><span>{config.features.knowledge?'病害知识与日常养护':'管理员已暂停'}</span>")
replace("<button disabled={!config.features.assistant} onClick={()=>navigate('assistant')}><MessageCircle size={23}/><strong>问问小禾</strong><span>聊聊你的田间新发现</span></button>", "<button onClick={()=>navigate('assistant')}><MessageCircle size={23}/><strong>{config.features.assistant?'问问小禾':'小禾对话'}</strong><span>{config.features.assistant?'聊聊你的田间新发现':'新问答暂停，可阅读历史'}</span></button>")
replace('<ChevronRight size={13}/></button>:<button onClick={()=>navigate(\'records\')}>全部记录<ChevronRight size={13}/>', '</button>:<button onClick={()=>navigate(\'records\')}>全部记录')
replace('查看全部观察<ChevronRight size={13}/>', '查看全部观察')
replace('第一份观察，等你开始', '还没有保存的观察')
replace('清晰拍下一片叶子，给生长留一份记录。', '从一张清晰的叶片照片开始，慢慢建立你的田间档案。')
replace("{record.result||'等待模型接入'}", "{record.result||({awaiting_model:'已采集，尚无识别结果',queued:'正在等待处理',processing:'正在分析图片',failed:'本次观察未完成'}[record.status])||'尚无识别结果'}")
replace('{confidence(record.confidence)}<ChevronRight', "{record.confidence==null?'查看':confidence(record.confidence)}<ChevronRight")

start=s.index('export function RecordsPage(')
end=s.index('export function PlotsPage(', start)
s=s[:start]+'''export function RecordsPage({records,onDetail,onRefresh,loading}:{records:Detection[];onDetail:(record:Detection)=>void;onRefresh:()=>void;loading:boolean}) {
  const {config}=useClientConfig()
  const [search,setSearch]=useState('');const [status,setStatus]=useState('');const [demo,setDemo]=useState(false)
  const keyword=searchText(search),hasFilters=Boolean(keyword||status)
  const filtered=records.filter(record=>(demo||!record.is_demo)&&(!status||(status==='pending'?pendingStatuses.includes(record.status):record.status===status))&&searchText(`${record.name} ${record.crop} ${record.result||''} ${record.plot_name} ${record.note||''}`).includes(keyword))
  const clearFilters=()=>{setSearch('');setStatus('')}
  return <div><div className="page-intro"><h1>观察记录</h1><p>回看照片与结果，接着上次的观察。</p></div><div className="search-field"><Search size={18}/><input aria-label="搜索检测记录" value={search} onChange={event=>setSearch(event.target.value)} placeholder="搜索作物、地块或病害"/>{search&&<button type="button" className="icon-button" aria-label="清除记录搜索" onClick={()=>setSearch('')}><X size={17}/></button>}</div>
    <div className="filter-chips scroll-chips" role="group" aria-label="筛选检测状态">{[['','全部'],['healthy','健康'],['attention','需关注'],['pending','未出结果'],['failed','未完成']].map(([value,label])=><button key={value} aria-pressed={status===value} className={status===value?'active':''} onClick={()=>setStatus(value)}>{label}</button>)}</div>
    <div className="records-caption records-filter-summary"><span aria-live="polite">{hasFilters?'找到':'共'} {filtered.length} 份观察</span><div>{hasFilters&&<button className="text-button filter-reset" onClick={clearFilters}>清除筛选</button>}<button className="text-button" onClick={onRefresh} disabled={loading}>{loading?'正在刷新…':'刷新'}</button></div></div>
    {filtered.length?<div className="record-list">{filtered.map(record=><RecordCard key={record.id} record={record} onClick={()=>onDetail(record)}/>)}</div>:hasFilters?<Empty title="没有匹配的观察" text="换个关键词，或清除筛选后查看现有记录。" action={<button className="button outline" onClick={clearFilters}>清除筛选</button>}/>:<Empty title="还没有保存的观察" text={config.features.image_detection?'采集一张叶片照片，记录将保存在这里。':'图片采集暂时暂停，可返回首页查看其他观察方式。'} action={<button className="button outline" onClick={()=>navigate(config.features.image_detection?'detect/image':'home')}>{config.features.image_detection?'开始图片观察':'返回首页'}</button>}/>}
    <label className="checkbox-line"><input type="checkbox" checked={demo} onChange={event=>setDemo(event.target.checked)}/>同时显示示例数据</label></div>
}
''' + s[end:]

replace("const filtered=plots.filter(plot=>`${plot.name}${plot.crop}${plot.location}`.includes(search))", "const keyword=searchText(search);const filtered=plots.filter(plot=>searchText(`${plot.name} ${plot.crop} ${plot.location}`).includes(keyword))")
replace('<span className="eyebrow">ROOTED IN YOUR LAND</span><h1>土地的生长档案</h1><p>查看我自己的地块，在检测时关联采样位置。</p>', '<h1>我的地块</h1><p>采样时关联地块，方便按位置回看。</p>')
replace('placeholder="地块、作物或位置"', 'placeholder="搜索地块、作物或位置"')
replace('<MapPin size={17}/>{plots.length} 块地', '<MapPin size={17}/>共 {plots.length} 块地')
replace('查看地图定位<ArrowRight size={13}/>', '<MapPin size={14}/>在地图中查看')
replace('{!filtered.length&&<Empty title="没有匹配的地块" text="调整关键词，或在网页版创建和维护自己的地块。"/>}', '{!filtered.length&&(keyword?<Empty title="没有匹配的地块" text="换个关键词，或清除搜索查看全部地块。" action={<button className="button outline" onClick={()=>setSearch(\'\')}>清除搜索</button>}/>:<Empty title="还没有地块档案" text="在网页版创建自己的地块后，可在这里查看并关联采样。"/>)}')
replace('articles.map(article=>article.crop))', 'articles.map(article=>article.crop).filter(Boolean)))')
replace("const filtered=articles.filter(article=>(!crop||article.crop===crop)&&`${article.title}${article.summary}${article.content}`.includes(search))", "const keyword=searchText(search),hasFilters=Boolean(keyword||crop);const filtered=articles.filter(article=>(!crop||article.crop===crop)&&searchText(`${article.title} ${article.summary} ${article.content} ${article.crop}`).includes(keyword))")
replace('<span className="eyebrow">XIAOHE\'S FIELD NOTES</span><h1>多懂一点，<br/>离丰收更近一点。</h1><p>把知识，种在每一天的田间。</p>', '<h1>读懂叶片变化，<br/>照顾好每一季。</h1><p>从日常观察，了解作物与养护。</p>')
replace('<div className="filter-chips scroll-chips">', '<div className="filter-chips scroll-chips" role="group" aria-label="筛选笔记作物">')
replace('<span>{article.crop}</span>', "<span>{article.crop||'通用'}</span>")
replace('{!filtered.length&&<Empty title="暂时没有这类笔记" text="换个关键词，或者直接问问小禾。"/>}', '{!filtered.length&&(hasFilters?<Empty title="没有匹配的笔记" text="换个关键词，或清除作物与搜索条件。" action={<button className="button outline" onClick={()=>{setSearch(\'\');setCrop(\'\')}}>清除筛选</button>}/>:<Empty title="暂时没有已发布的笔记" text="之后发布的种植与养护知识，会整理在这里。"/>)}')
replace('<MessageCircle size={17}/>把问题带给小禾', "<MessageCircle size={17}/>{config.features.assistant?'把问题带给小禾':'小禾新问答暂时暂停'}")
replace('<Sheet title="小禾田间笔记"', '<Sheet title="田间笔记"')
replace('{selected.crop} · {selected.category}', "{selected.crop||'通用'} · {selected.category}")
replace('{source.title}<ArrowRight size={13}/>', '{source.title}')
replace('  const {config}=useClientConfig()\n  return <div><div className="profile-hero">', "  const {config}=useClientConfig();const ready=data.model?.status==='ready';const cropCount=ready?(data.model?.supported_crops.length??0):(data.model?.available_crops.length??0)\n  return <div><div className=\"profile-hero\">")
replace('{data.model?.supported_crops.length||0}</strong>已支持作物', "{cropCount}</strong>{ready?'可识别作物':'可采集作物'}")
replace('title="小禾田间笔记"', 'title="田间笔记"')
replace("description={config.features.assistant?'按账户保存的私人聊天记录':'新问答暂停，历史对话仍可阅读'}", "description={config.features.assistant?'继续你的私人对话':'新问答暂停，历史仍可阅读'}")
replace('检测记录、地块与小禾对话按账户隔离；管理人员通过独立管理端维护。', '观察记录和小禾对话按账户保存，管理员通过独立管理端维护服务。')
replace('禾观 AgriScan · 随身巡田 1.0', '禾观 AgriScan · 随身巡田')

start=s.index('export function ServiceSettings(')
s=s[:start]+'''function validateServiceAddress(value:string) {
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
      const health:{status?:string;model?:string}=await response.json()
      if(health.status!=='ok'||typeof health.model!=='string')throw new Error('这个地址未返回禾观服务状态，请确认地址中包含正确的服务路径。')
      if(testVersion.current===version)setMessage(`${base===currentBase?'当前服务连接正常':'此地址可以连接，保存后即可登录'}，${health.model==='ready'?'识别模型已就绪':'识别模型尚未启用'}。`)
    } catch(reason) {
      if(testVersion.current!==version||controller.signal.aborted)return
      setError(reason instanceof DOMException&&reason.name==='TimeoutError'?'连接检查超时，请确认服务已启动并检查网络。':reason instanceof TypeError?'无法连接此地址，请检查地址、网络以及服务是否允许访问。':(reason as Error).message)
    } finally {if(testController.current===controller)testController.current=null;if(testVersion.current===version)setTesting(false)}
  }
  function save(event:FormEvent){event.preventDefault();if(testing)return;setError('');setNotice('');try{const base=validateServiceAddress(value);if(base===currentBase){setNotice('服务地址未改变，当前登录状态已保留。');return}saveServiceBase(base);onSaved()}catch(reason){setError((reason as Error).message)}}
  return <div className="settings-page"><div className="page-intro"><h1>账户与连接</h1><p>查看当前账户，调整服务连接与界面偏好。</p></div>{user&&<div className="settings-account"><span className="avatar">{user.name.slice(0,1)}</span><div><strong>{user.name}</strong><p>{user.role==='admin'?'管理员':'田间伙伴'} · @{user.username}</p></div><ShieldCheck size={20}/></div>}
    <form className="card settings-service" onSubmit={save} noValidate><div className="section-heading"><h2><Server size={18}/>服务连接</h2><Wifi size={17}/></div><div className="service-current"><span>当前服务</span><strong>{currentBase||(isNativeAndroid()?'尚未配置':'本地代理')}</strong></div>
      <label>服务地址<input type="url" inputMode="url" value={value} onChange={event=>edit(event.target.value)} placeholder="例如 https://agriscan.example.com" autoCapitalize="none" autoCorrect="off" spellCheck={false}/></label>
      <details className="service-help"><summary>如何填写服务地址</summary><p>{isNativeAndroid()?'填写手机能访问的服务器或电脑局域网地址。手机上的 localhost 指向手机本身。':'留空使用本地代理；连接其他服务时，填写完整地址和服务路径。'}</p></details>
      <ErrorNote message={error}/>{message&&<p className="success-note" role="status">{message}</p>}{notice&&<p className="settings-save-note" role="status">{notice}</p>}
      <div className="settings-buttons"><FeedbackButton type="button" className="outline" onClick={test} busy={testing} busyLabel="正在检查地址" complete={!!message} completeLabel="连接检查通过">检查此地址</FeedbackButton><button className="button primary" disabled={testing||!changed}>{changed?'保存并重新登录':'当前地址已保存'}</button></div>
      <small className="settings-save-note">{changed?'保存后将切换服务并重新登录，当前账户的令牌不会发送到新地址。':'检查连接不会修改地址，也不会退出当前账户。'}</small>
    </form>
    <section className="card settings-preferences"><h2>界面偏好</h2><div><span><strong>界面动效</strong><small>同时遵循系统的减少动态效果设置</small></span><button className={`toggle ${motion?'on':''}`} role="switch" aria-checked={motion} aria-label="界面动效" onClick={()=>{const next=!motion;setMotion(next);localStorage.setItem('agriscan-mobile-motion',String(next));document.documentElement.classList.toggle('reduce-motion',!next)}}><i/></button></div></section>
    {onLogout&&<button className="button ghost full logout-button" onClick={onLogout}><LogOut size={17}/>退出当前账户</button>}<p className="version-note">禾观 AgriScan · 随身巡田<br/>连接好服务，再开始新的观察。</p></div>
}
'''
path.write_text(s, encoding='utf-8')
