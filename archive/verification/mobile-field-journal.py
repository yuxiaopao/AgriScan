from pathlib import Path
p=Path('E:/AgriScan/mobile/src/WorkspacePages.tsx')
s=p.read_text(encoding='utf-8')
s=s.replace('Leaf, LogOut, MapPin,', 'Leaf, ListChecks, LogOut, MapPin,')
start=s.index('export function HomePage(')
end=s.index('export function RecordCard(',start)
s=s[:start]+'''export function HomePage({user, data, onDetail}: {user: User; data: Workspace; onDetail: (record: Detection) => void}) {
  const {config}=useClientConfig()
  const [recentExpanded,setRecentExpanded]=useState(false)
  const real=data.records.filter(record=>!record.is_demo)
  const hour=new Date().getHours(),ready=data.model?.status==='ready'
  const cropCount=ready?(data.model?.supported_crops.length??0):(data.model?.available_crops.length??0)
  const modes=[
    {route:'camera',title:'实时相机',text:'边巡田，边查看结果',icon:Camera,enabled:config.features.live_detection},
    {route:'video',title:'视频检测',text:'按时间抽样查看',icon:Film,enabled:config.features.video_detection},
  ]
  return <div className="home-page field-journal-home">
    <div className="home-greeting journal-greeting"><div><p>{new Date().toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'})}</p><h1>{hour<11?'早上好':hour<14?'中午好':hour<18?'下午好':'晚上好'}，{user.name}</h1></div><button className="avatar" onClick={()=>navigate('profile')} aria-label="打开个人中心">{user.name.slice(0,1)}</button></div>
    <section className="home-hero field-journal-hero">
      <img className="field-journal-hero-image" src="/images/field-morning-hero.png" alt="小禾在田间观察叶片的产品插画" draggable={false} onError={event=>{if(!event.currentTarget.src.endsWith('/images/app-hero.webp'))event.currentTarget.src='/images/app-hero.webp'}}/>
      <div className="home-hero-copy"><span className="journal-context"><i className={ready?'ready':''}/>{ready?'小禾的田间观察':config.features.image_detection?'从采集一张照片开始':'图片采集暂时暂停'}</span><h2><span>一片叶子，</span><span>一份生长记录。</span></h2><p>拍清一片叶子，让每次观察有据可查。</p><button className="button primary journal-photo-action" disabled={!config.features.image_detection} onClick={()=>navigate('detect/image')}><ImagePlus size={18}/>{config.features.image_detection?(ready?'开始图片检测':'开始图片采集'):'图片采集暂时暂停'}</button></div>
    </section>
    <div className="journal-secondary-modes" aria-label="其他观察方式">{modes.map(mode=><button key={mode.route} type="button" disabled={!mode.enabled||!ready} onClick={()=>navigate(`detect/${mode.route}`)}><span className="journal-mode-icon"><mode.icon size={21}/></span><span><strong>{mode.title}</strong><small>{!mode.enabled?'管理员已暂停':!ready?'需启用识别模型':mode.text}</small></span></button>)}</div>
    {!ready&&<p className="journal-service-note">{data.model?(config.features.image_detection?'识别模型尚未启用，照片会先保存为采集记录。':'图片采集暂时暂停，仍可回看已有观察。'):'暂时未能确认服务状态，请稍后刷新。'}</p>}
    <section className="journal-data-strip" aria-label="我的田间档案"><div><strong>{real.length}</strong><span>份观察记录</span></div><div><strong>{data.plots.length}</strong><span>块种植地</span></div><div><strong>{data.model?cropCount:'—'}</strong><span>{ready?'种可识别作物':config.features.image_detection?'种可采集作物':'种已配置作物'}</span></div></section>
    <nav className="journal-tools" aria-label="田间快捷入口"><button type="button" onClick={()=>navigate('records')}><span className="journal-tool-icon"><ListChecks size={21}/></span><strong>观察记录</strong><small>照片与结果</small></button><button type="button" disabled={!config.features.plots} onClick={()=>navigate('plots')}><span className="journal-tool-icon"><MapPin size={21}/></span><strong>地块档案</strong><small>{config.features.plots?'按位置回看':'暂时暂停'}</small></button><button type="button" disabled={!config.features.knowledge} onClick={()=>navigate('knowledge')}><span className="journal-tool-icon"><BookOpen size={21}/></span><strong>田间笔记</strong><small>{config.features.knowledge?'病害与养护':'暂时暂停'}</small></button></nav>
    <section className="journal-recent-section"><div className="section-heading journal-section-heading"><div><span>你的田间时间线</span><h2>最近的观察</h2></div>{real.length>1?<button className="stack-control" aria-expanded={recentExpanded} aria-controls="recent-observations" onClick={()=>setRecentExpanded(value=>!value)}>{recentExpanded?'收起':`展开 ${Math.min(real.length,3)} 份`}</button>:<button onClick={()=>navigate('records')}>全部记录</button>}</div>
      {real.length?<div data-count={Math.min(real.length,3)} className={`recent-stack ${!recentExpanded&&real.length>1?'is-folded':''}`}><div id="recent-observations" className="record-list">{real.slice(0,recentExpanded?3:1).map(record=><RecordCard key={record.id} record={record} onClick={()=>onDetail(record)}/>)}</div>{recentExpanded&&<button className="text-button full" onClick={()=>navigate('records')}>查看全部观察</button>}</div>:<Empty title="第一份记录，从这里生长" text="拍下一张叶片照片，之后可以在这里对照变化。"/>}
    </section>
    <p className="home-footer"><Sprout size={15}/>把观察留住，把生长读懂。</p>
  </div>
}
''' +s[end:]
s=s.replace('className="record-card"','className="record-card journal-record"')
s=s.replace('<div className="page-intro"><h1>观察记录</h1>', '<div className="page-intro journal-page-intro"><span className="journal-page-label">每一次观察，都有迹可循</span><h1>观察记录</h1>')
s=s.replace('<div className="page-intro"><h1>我的地块</h1>', '<div className="page-intro journal-page-intro"><span className="journal-page-label">把观察与土地连起来</span><h1>我的地块</h1>')
s=s.replace('className="plot-totals"','className="plot-totals journal-data-summary"')
s=s.replace('className="card mobile-plot"','className="card mobile-plot journal-plot"')
s=s.replace('<div className="plot-illustration"><Sprout size={64}/><i/><i/></div>', '<div className="plot-illustration journal-plot-placeholder"><Sprout size={48}/><span>尚未设置封面</span></div>')
old='<div className="knowledge-hero"><div><h1>读懂叶片变化，<br/>照顾好每一季。</h1><p>从日常观察，了解作物与养护。</p></div><Art src="/images/xiaohe.png" alt="小禾的田间笔记"/></div>'
new='<section className="knowledge-hero field-notes-hero"><div className="field-notes-hero-copy"><span>田间笔记</span><h1>把叶片读懂，<br/>把田地照顾好。</h1><p>从叶色、纹理到日常养护。</p></div><img src="/images/field-notes-macro.png" alt="" aria-hidden="true" draggable={false} onError={event=>{event.currentTarget.style.display=\'none\'}}/></section>'
assert old in s
s=s.replace(old,new)
s=s.replace('className="article-card"','className="article-card journal-article"')
s=s.replace('<div className="profile-hero">', '<div className="profile-hero journal-profile-hero"><span className="journal-page-label">我的田间账户</span>')
s=s.replace('<Art src="/images/xiaohe.png" alt="小禾陪你巡田"/>','')
s=s.replace('className="profile-stats"','className="profile-stats journal-profile-stats"')
s=s.replace('className="card profile-links"','className="card profile-links journal-profile-links"')
p.write_text(s,encoding='utf-8')
