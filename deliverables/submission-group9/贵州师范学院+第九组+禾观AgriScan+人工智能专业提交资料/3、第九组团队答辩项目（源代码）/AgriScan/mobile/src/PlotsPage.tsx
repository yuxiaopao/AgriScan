import {useEffect,useRef,useState} from 'react'
import {ChevronRight,MapPin,Search} from 'lucide-react'
import {useClientConfig} from './ClientConfig'
import {Badge,Empty,SecureImage,Sheet} from './components'
import {confidence,navigate} from './hooks'
import {IpIcon} from './IpIcon'
import PlotEditor from './PlotEditor'
import type {Detection,Plot,User} from './types'
import {usePlotScope} from './usePlotScope'
import './plots.css'

export default function PlotsPage({plots,records,crops,user,onChanged,onDetail}:{plots:Plot[];records:Detection[];crops:string[];user:User;onChanged:(plot?:Plot)=>void;onDetail:(record:Detection)=>void}){
  const {config}=useClientConfig(),scope=usePlotScope()
  const [localPlots,setLocalPlots]=useState(plots),[search,setSearch]=useState(''),[editing,setEditing]=useState<Plot|'new'|null>(null),[selected,setSelected]=useState<string|null>(null)
  const enabled=useRef(config.features.plots);enabled.current=config.features.plots
  useEffect(()=>{if(scope.current())setLocalPlots(plots)},[plots])
  const keyword=search.trim().normalize('NFKC').toLocaleLowerCase('zh-CN')
  const filtered=localPlots.filter(plot=>`${plot.name} ${plot.crop} ${plot.location} ${plot.manager}`.normalize('NFKC').toLocaleLowerCase('zh-CN').includes(keyword))
  const detail=localPlots.find(plot=>plot.id===selected)
  const related=records.filter(record=>record.plot_id===selected&&!record.is_demo)
  const editCrops=[...new Set([...crops,...(editing&&editing!=='new'?[editing.crop]:[])])]
  function edit(plot:Plot|'new'){if(scope.current()&&enabled.current){setSelected(null);setEditing(plot)}}
  function saved(plot:Plot){if(!scope.current())return;setSearch('');setLocalPlots(old=>[plot,...old.filter(item=>item.id!==plot.id)]);onChanged(plot)}
  if(!scope.valid)return <Empty title="账户或服务已变化" text="本页草稿已关闭。请返回首页，确认当前登录账户后再进入地块。" action={<button className="button outline" onClick={()=>navigate('home')}>返回首页</button>}/>
  return <div className="mobile-plots-page">
    <div className="page-intro journal-page-intro"><h1>我的地块</h1><p>把土地的位置、作物与每次观察连接起来。</p><button className="button primary plot-create-button" disabled={!config.features.plots} onClick={()=>edit('new')}><IpIcon name="plots"/>创建我的地块</button></div>
    {!config.features.plots&&<p className="info-note" role="status">地块编辑已暂停。已有档案与关联观察仍可查看，暂不能新建或修改。</p>}
    <div className="search-field"><Search size={18}/><input aria-label="搜索地块" placeholder="搜索地块、作物、位置或负责人" value={search} onChange={event=>setSearch(event.target.value)}/></div>
    <div className="plot-totals journal-data-summary"><span><MapPin size={17}/>共 {localPlots.length} 块地</span><strong>{localPlots.reduce((sum,plot)=>sum+plot.area,0).toLocaleString('zh-CN',{maximumFractionDigits:1})}<small>亩种植面积</small></strong></div>
    <div className="mobile-plots">{filtered.map(plot=><article className="card mobile-plot journal-plot" key={plot.id}><div className="plot-cover">{plot.cover_url?<SecureImage url={plot.cover_url} alt={plot.name}/>:<div className="plot-illustration journal-plot-placeholder"><IpIcon name="plots"/><span>尚未设置封面</span></div>}<span>{plot.crop}种植区</span><strong>{plot.area}<small>亩</small></strong></div><div className="plot-info"><h2><button type="button" className="plot-open-title" onClick={()=>setSelected(plot.id)}>{plot.name}<ChevronRight size={18}/></button></h2><p><MapPin size={13}/>{plot.location||'位置待补充'}</p><div><span>负责人<strong>{plot.manager||'未设置'}</strong></span><span>观察记录<strong>{plot.detections} 份</strong></span><span>历史健康率<strong>{plot.health_score==null?'—':`${Math.round(plot.health_score)}%`}</strong></span></div><footer className="plot-card-actions"><button className="button outline" onClick={()=>setSelected(plot.id)}>查看地块与观察</button><button className="text-button" disabled={!config.features.plots} onClick={()=>edit(plot)}>编辑地块</button></footer></div></article>)}</div>
    {!filtered.length&&(keyword?<Empty title="没有匹配的地块" text="换个关键词，或清除搜索查看全部地块。" action={<button className="button outline" onClick={()=>setSearch('')}>清除搜索</button>}/>:<Empty title="从第一块种植地开始" text={config.features.plots?'填写作物和位置，下次采样时就能直接关联。':'当前没有地块档案，管理员恢复编辑后可创建。'} action={config.features.plots?<button className="button primary" onClick={()=>edit('new')}>创建第一块地</button>:undefined}/>)}
    {editing&&<PlotEditor key={editing==='new'?'new':editing.id} plot={editing==='new'?null:editing} crops={editCrops} manager={user.name} onSaved={saved} onClose={()=>setEditing(null)} onCheck={()=>{if(scope.current()){setEditing(null);onChanged()}}}/>}
    {detail&&<Sheet title="我的地块档案" onClose={()=>setSelected(null)}><div className="mobile-plot-detail"><span className="eyebrow">{detail.crop}种植区</span><h2>{detail.name}</h2>{detail.cover_url&&<SecureImage url={detail.cover_url} alt={`${detail.name}封面`} className="plot-detail-cover"/>}<dl><div><dt>种植面积</dt><dd>{detail.area} 亩</dd></div><div><dt>地块位置</dt><dd>{detail.location||'未填写'}</dd></div><div><dt>负责人</dt><dd>{detail.manager||'未填写'}</dd></div><div><dt>历史健康率</dt><dd>{detail.health_score==null?'暂无识别记录':`${Math.round(detail.health_score)}%`}</dd></div>{detail.latitude!=null&&detail.longitude!=null&&<div><dt>经纬度</dt><dd>{detail.latitude}，{detail.longitude}</dd></div>}</dl>{detail.latitude!=null&&detail.longitude!=null&&Number.isFinite(detail.latitude)&&Number.isFinite(detail.longitude)&&Math.abs(detail.latitude)<=90&&Math.abs(detail.longitude)<=180&&<a className="button outline full" href={`https://www.openstreetmap.org/?mlat=${detail.latitude}&mlon=${detail.longitude}#map=17/${detail.latitude}/${detail.longitude}`} target="_blank" rel="noreferrer"><MapPin size={16}/>在地图中查看</a>}<button className="button primary full" disabled={!config.features.plots} onClick={()=>edit(detail)}>编辑信息与封面</button><div className="section-heading"><h2>关联的个人观察</h2><span>{related.length} 份</span></div>{related.length?<div className="record-list">{related.map(record=><button key={record.id} className="record-card journal-record" onClick={()=>{setSelected(null);onDetail(record)}}>{record.image_url?<SecureImage url={record.image_url} alt={record.name} className="record-thumb"/>:<span className="record-thumb record-leaf"><IpIcon name="records"/></span>}<span className="record-copy"><strong>{record.crop}<Badge status={record.status}/></strong><span>{record.result||'尚无识别结果'}</span><small>{new Date(record.created_at).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}</small></span><span className="record-score">{confidence(record.confidence)}<ChevronRight size={15}/></span></button>)}</div>:<Empty title="这里还没有观察记录" text="检测叶片时关联这块地，之后就能回来对照变化。"/>}</div></Sheet>}
  </div>
}
