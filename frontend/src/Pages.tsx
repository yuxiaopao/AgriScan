import {Xiaohe} from './Xiaohe'
import {CropRoom} from './CropRoom'
import {useCropTheme} from './CropTheme'
import {XiaoheMotionDemo} from './XiaoheMotionDemo'
import PlotEditor from './PlotEditor'
import PlotCoverCarousel from './PlotCoverCarousel'
import {confidenceText, PredictionScores} from './PredictionScores'
import type {ReactNode} from 'react'
import {useEffect, useRef, useState, type FormEvent} from 'react'
import {ArrowRight, ArrowUpRight, BookOpen, Check, CheckCircle2, CircleAlert, CloudUpload, FileImage, Filter, FlaskConical, HardDrive, Layers3, Leaf, LoaderCircle, MapPin, Pencil, Plus, Search, Server, Settings2, ShieldCheck, Sprout, Trash2, Upload, X} from 'lucide-react'
import {api, downloadCsv} from './api'
import {Badge, CropIcon, DetectionTable, Empty, Modal, statusLabels} from './components'
import type {Article, Detection, Health, ModelInfo, Plot, User} from './types'

interface ProtectedProps {requireAuth: () => boolean; onChange: () => void; toast: (message: string) => void}
export function DetectPage({plots, model, requireAuth, onChange, toast, onDetected}: {plots: Plot[]; model: ModelInfo; onDetected: (record: Detection) => void} & ProtectedProps) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState('')
  const {crop, setCrop} = useCropTheme()
  const [plotId, setPlotId] = useState('')
  const [note, setNote] = useState('')
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<Detection | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const crops = model.active ? model.supported_crops : model.available_crops
  const modelReady = model.status === 'ready'
  useEffect(() => {
    if (crops.length && !crops.includes(crop)) {setCrop(crops[0]); setPlotId(''); setResult(null)}
  }, [crops, crop, setCrop])
  const selectCrop = (next: string) => {
    if (busy || crop === next || !crops.includes(next)) return
    setCrop(next); setPlotId(''); setResult(null)
  }
  useEffect(() => {if (!file) {setPreview(''); return}; const url = URL.createObjectURL(file); setPreview(url); return () => URL.revokeObjectURL(url)}, [file])
  const chooseFile = (next?: File) => {
    if (busy || !next) return
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(next.type)) {toast('请选择 JPG、PNG 或 WebP 格式的图片。'); return}
    if (next.size > 10 * 1024 * 1024) {toast('图片不能超过 10 MB，请压缩后重新选择。'); return}
    setFile(next); setResult(null)
  }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy || !file || !requireAuth()) return
    setBusy(true); setDragging(false)
    const body = new FormData()
    body.append('file', file); body.append('crop', crop); if (plotId) body.append('plot_id', plotId); body.append('note', note)
    try {const saved = await api<Detection>('/detections', {method: 'POST', body}); setResult(saved); onChange(); onDetected(saved); toast(saved.status === 'awaiting_model' ? '样本已保存，小禾正在辅助解读照片。' : '检测完成，小禾正在整理处理与复检建议。')}
    catch (error) {toast((error as Error).message)}
    finally {setBusy(false)}
  }
  return <>
    <CropRoom crops={crops} availableCrops={model.available_crops} busy={busy} onSelect={selectCrop}/>
    <div className={`detect-grid ${result ? 'has-result' : ''}`}><form className="panel upload-panel" onSubmit={submit} aria-busy={busy}><div className="panel-header"><h2><span className="step-number">01</span>上传作物图片</h2><span className="quiet">单图检测</span></div>
      <div className="upload-workspace"><div className="upload-media"><input ref={input} type="file" disabled={busy} accept="image/jpeg,image/png,image/webp" className="sr-only" aria-label="选择作物图片" onChange={event => chooseFile(event.target.files?.[0])}/>
      <div className={`drop-zone ${dragging ? 'dragging' : ''} ${preview ? 'has-preview' : ''}`} onDragOver={event => {event.preventDefault(); setDragging(!busy)}} onDragLeave={() => setDragging(false)} onDrop={event => {event.preventDefault(); setDragging(false); chooseFile(event.dataTransfer.files[0])}}>
        {preview ? <><img src={preview} className="upload-preview" alt="待检测作物预览"/><button type="button" disabled={busy} className="preview-remove" onClick={() => {setFile(null); setResult(null); if (input.current) input.current.value = ''}} aria-label="移除已选图片"><X size={18}/></button><div className="file-chip"><FileImage size={15}/><span>{file?.name}</span><small>{((file?.size ?? 0) / 1024 / 1024).toFixed(2)} MB</small></div></> : <><div className="upload-guidance"><h3>拍得清楚，看得更准</h3><ol>{[['自然光线', '避开强烈反光，保留叶片真实颜色。'], ['主体清晰', '靠近叶片拍摄，让病斑与纹理清楚可见。'], ['完整记录', '一次选择一张图片，并补充采集备注。']].map(([title, content], index) => <li key={title}><span>{String(index + 1).padStart(2, '0')}</span><div><strong>{title}</strong><p>{content}</p></div></li>)}</ol></div><button type="button" className="button primary" disabled={busy} onClick={() => input.current?.click()}><Upload size={16}/>选择图片</button><span className="upload-hint">支持 JPG、PNG、WebP · 最大 10 MB</span></>}
      </div>
      {file && <button className="text-button change-file" type="button" disabled={busy} onClick={() => input.current?.click()}>重新选择图片</button>}
      </div><div className="form-section"><h2><span className="step-number">02</span>补充样本信息</h2><div className="form-grid"><label>作物类型<select value={crop} disabled={busy || !crops.length} onChange={event => selectCrop(event.target.value)}>{crops.map(item => <option key={item}>{item}</option>)}</select></label><label>所属地块 <span>（选填）</span><select value={plotId} disabled={busy} onChange={event => setPlotId(event.target.value)}><option value="">暂不关联地块</option>{plots.filter(plot => plot.crop === crop).map(plot => <option key={plot.id} value={plot.id}>{plot.name}</option>)}</select></label></div><label>样本备注 <span>（选填）</span><textarea value={note} disabled={busy} onChange={event => setNote(event.target.value)} maxLength={500} placeholder="例如：叶片出现黄斑，采集于植株中部…" rows={3}/></label></div>
      </div><div className="upload-actions"><span><ShieldCheck size={14}/>图片用于检测与小禾解读</span><button className="button primary" type="submit" disabled={!file || busy}>{busy ? <LoaderCircle size={17} className="spin"/> : <CloudUpload size={17}/>} {busy ? (modelReady ? '正在分析…' : '正在保存…') : (modelReady ? '分析并保存' : '保存检测样本')}</button></div>
    </form>{result && <aside className="detect-aside"><section className="panel result-panel"><div className="result-icon"><CheckCircle2 size={32}/></div><h2>{result.status === 'awaiting_model' ? '样本保存成功' : '分析完成'}</h2><p>结果已保存至检测记录。</p><Badge status={result.status}/><dl><div><dt>样本编号</dt><dd>{result.id.slice(0, 12)}</dd></div><div><dt>作物类型</dt><dd>{result.crop}</dd></div><div><dt>分析结果</dt><dd>{result.result || '等待模型接入'}</dd></div><div className="result-confidence"><dt>分类置信度</dt><dd title={`原始输出：${result.confidence ?? "未提供"}`}>{confidenceText(result.confidence)}</dd></div></dl><PredictionScores record={result}/><a className="button outline full" href="#records">查看检测记录<ArrowRight size={15}/></a></section></aside>}</div>
  </>
}

export function RecordsPage({records, crops, onSelect, search, setSearch, status, setStatus}: {records: Detection[]; crops: string[]; onSelect: (record: Detection) => void; search: string; setSearch: (search: string) => void; status: string; setStatus: (status: string) => void}) {
  const [crop, setCrop] = useState('')
  const [source, setSource] = useState('')
  const [page, setPage] = useState(1)
  const filtered = records.filter(record => `${record.name} ${record.crop} ${record.plot_name} ${record.id}`.toLowerCase().includes(search.toLowerCase()) && (!crop || record.crop === crop) && (!status || record.status === status) && (!source || (source === 'demo' ? record.is_demo : !record.is_demo)))
  const pages = Math.max(1, Math.ceil(filtered.length / 8))
  const currentPage = Math.min(page, pages)
  useEffect(() => setPage(1), [search, crop, status, source])
  return <><section className="panel records-panel"><div className="records-toolbar"><div className="input-search"><Search size={17}/><input aria-label="搜索检测记录" placeholder="搜索样本、作物、地块…" value={search} onChange={event => setSearch(event.target.value)}/>{search && <button className="icon-button" aria-label="清除搜索" onClick={() => setSearch('')}><X size={14}/></button>}</div><div className="filter-selects"><Filter size={16}/><select aria-label="筛选作物" value={crop} onChange={event => setCrop(event.target.value)}><option value="">全部作物</option>{crops.map(item => <option key={item}>{item}</option>)}</select><select aria-label="筛选检测状态" value={status} onChange={event => setStatus(event.target.value)}><option value="">全部状态</option>{Object.entries(statusLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><select aria-label="筛选样本来源" value={source} onChange={event => setSource(event.target.value)}><option value="">全部来源</option><option value="upload">上传样本</option><option value="demo">示例样本</option></select></div></div>{filtered.length ? <DetectionTable records={filtered.slice((currentPage - 1) * 8, currentPage * 8)} onSelect={onSelect}/> : <Empty title="没有找到匹配的记录" description="试试其他关键词，或调整筛选条件。"/>}<div className="pagination"><span>共 {filtered.length} 条记录 <span className="quiet">· 示例结果仅用于界面演示</span></span><div><button disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}>上一页</button><span>{currentPage} / {pages}</span><button disabled={currentPage >= pages} onClick={() => setPage(currentPage + 1)}>下一页</button></div></div></section></>
}

export function exportRecords(records: Detection[]) {
  downloadCsv([['样本编号', '名称', '作物', '地块', '状态', '结果', '置信度', '示例数据', '检测时间', '备注'], ...records.map(record => [record.id, record.name, record.crop, record.plot_name, statusLabels[record.status], record.result, record.confidence, record.is_demo ? '是' : '否', record.created_at, record.note])], `禾观-检测记录-${new Date().toISOString().slice(0, 10)}.csv`)
}

export function PlotsPage({plots, crops, draftOwner, requireAuth, onChange, toast}: {plots: Plot[]; crops: string[]; draftOwner: string} & ProtectedProps) {
  const [editing, setEditing] = useState<Plot | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Plot | null>(null)
  const [busy, setBusy] = useState(false)
  const [search, setSearch] = useState('')
  const filtered = plots.filter(plot => `${plot.name} ${plot.crop} ${plot.location}`.includes(search))
  async function remove() {
    if (!deleting) return
    setBusy(true)
    try {await api(`/plots/${deleting.id}`, {method: 'DELETE'}); setDeleting(null); onChange(); toast('地块已移除，历史样本仍保留。')}
    catch (error) {toast((error as Error).message)}
    finally {setBusy(false)}
  }
  return <><div className="plot-summary"><span><MapPin size={18}/>管理中的地块 <strong>{plots.length}</strong> 块</span><span><Layers3 size={18}/>总种植面积 <strong>{plots.reduce((sum, plot) => sum + plot.area, 0).toLocaleString(undefined, {maximumFractionDigits: 2})}</strong> 亩</span><div className="input-search"><Search size={16}/><input aria-label="搜索地块" placeholder="查找地块…" value={search} onChange={event => setSearch(event.target.value)}/></div></div><div className="plot-grid">{filtered.map((plot, index) => <article className="panel plot-card" key={plot.id}><PlotCoverCarousel plot={plot} index={index}/><div className="plot-body"><div className="plot-title"><h2>{plot.name}</h2><button className="icon-button" aria-label={`编辑${plot.name}`} onClick={() => {if (requireAuth()) setEditing(plot)}}><Pencil size={16}/></button></div><p><MapPin size={13}/>{plot.location || '位置待补充'}</p>{plot.latitude != null && plot.longitude != null && <a className="plot-map-link" href={`https://www.openstreetmap.org/?mlat=${plot.latitude}&mlon=${plot.longitude}#map=18/${plot.latitude}/${plot.longitude}`} target="_blank" rel="noreferrer"><MapPin size={12}/>查看定位<ArrowUpRight size={12}/></a>}<div className="plot-metrics"><div><span>负责人</span><strong>{plot.manager || '未设置'}</strong></div><div><span>检测记录</span><strong>{plot.detections} <small>份</small></strong></div><div><span>历史健康率</span><strong>{plot.health_score == null ? '—' : `${Math.round(plot.health_score)}%`}</strong></div></div><div className="plot-card-footer"><span>健康率根据已有结果统计</span><button aria-label={`删除${plot.name}`} onClick={() => {if (requireAuth()) setDeleting(plot)}}><Trash2 size={14}/></button></div></div></article>)}<button className="add-plot-card" onClick={() => {if (requireAuth()) setEditing('new')}}><span><Plus size={28}/></span><strong>添加一块新地</strong><p>让每一份生长，都有迹可循</p></button></div>
    {editing && <PlotEditor key={`${draftOwner}:${editing === 'new' ? 'new' : editing.id}`} owner={draftOwner} plot={editing === 'new' ? null : editing} crops={crops} onChange={onChange} onClose={() => setEditing(null)} toast={toast}/>}
    {deleting && <Modal title="移除地块" onClose={() => !busy && setDeleting(null)}><p className="modal-message">确定移除「{deleting.name}」吗？该地块关联的历史检测样本将保留。</p><div className="modal-actions"><button className="button outline" disabled={busy} onClick={() => setDeleting(null)}>取消</button><button className="button danger" disabled={busy} onClick={remove}>{busy ? '移除中…' : '确认移除'}</button></div></Modal>}
  </>
}

export function KnowledgePage({articles, children}: {articles: Article[]; children?: ReactNode}) {
  const crops = Array.from(new Set(articles.map(article => article.crop)))
  const [search, setSearch] = useState('')
  const [crop, setCrop] = useState('')
  const [selected, setSelected] = useState<Article | null>(null)
  const filtered = articles.filter(article => (!crop || article.crop === crop) && `${article.title}${article.summary}${article.crop}`.includes(search))
  return <><div className="knowledge-banner"><div><span className="hero-label"><BookOpen size={15}/>小禾的田间笔记</span><h2>多懂一点，离丰收更近一点。</h2><p>从叶片观察到日常管理，把知识种在田间。</p></div><Xiaohe state="think"/></div>{children}<div className="knowledge-toolbar"><div className="crop-tabs">{['', ...crops].map(item => <button className={crop === item ? 'active' : ''} key={item} onClick={() => setCrop(item)}>{item || '全部作物'}</button>)}</div><div className="input-search"><Search size={17}/><input aria-label="搜索知识库" placeholder="搜索病害与养护知识" value={search} onChange={event => setSearch(event.target.value)}/></div></div><div className="knowledge-grid">{filtered.map((article, index) => <button className="panel article-card" key={article.id} onClick={() => setSelected(article)}><div className={`article-cover article-color-${index % 4}`}><span className="article-category">{article.category}</span><Leaf className="article-leaf leaf-back" size={120} strokeWidth={.65}/><Sprout className="article-leaf" size={110} strokeWidth={.8}/><span className="article-cover-caption">{article.crop.toUpperCase()} / FIELD NOTES</span></div><div className="article-body"><span className="article-crop">{article.crop} · 田间知识</span><h2>{article.title}</h2><p>{article.summary}</p><span className="read-article">阅读笔记<ArrowUpRight size={15}/></span></div></button>)}</div>{!filtered.length && <Empty title="暂时没有相关内容" description="换一个关键词，或选择其他作物分类。"/>}<p className="knowledge-disclaimer"><CircleAlert size={14}/>知识内容用于一般种植学习，实际病害请结合现场情况由农技人员确认。</p>{selected && <Modal wide title={selected.title} onClose={() => setSelected(null)}><div className="article-content"><span className="badge healthy">{selected.crop} · {selected.category}</span><p className="article-intro">{selected.summary}</p>{selected.content.split('\n').filter(Boolean).map((paragraph, index) => <p key={index}>{paragraph}</p>)}{selected.sources?.length ? <div className="article-sources"><span>延伸阅读 · 专业资料</span>{selected.sources.map(source => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{source.title}<ArrowUpRight size={14}/></a>)}</div> : null}<div className="notice"><Sprout size={18}/><p>日常巡田、及时记录，与专业农技人员一起做好作物管理。</p></div></div></Modal>}</>
}

export function ModelsPage({model, health, children}: {model: ModelInfo; health: Health | null; children?: ReactNode}) {
  return <><section className="panel model-hero"><div className="model-icon"><FlaskConical size={35}/></div><div><span className={`badge ${model.active ? 'healthy' : 'awaiting_model'}`}>{model.active ? '模型已启用' : '等待训练模型'}</span><h2>{model.active?.name || '下一步，让小禾学会观察。'}</h2><p>{model.message || '检测流程与数据存储已准备就绪，接入训练好的模型即可启用图像分析。'}</p></div><img src="/images/xiaohe.png" alt="等待学习的小禾"/></section>{children}<div className="model-grid"><section className="panel model-details"><div className="panel-header"><h2>推理服务状态</h2><span className="quiet">INFERENCE ENGINE</span></div><dl className="status-list"><div><dt><Server size={17}/>应用服务</dt><dd><span className="live-dot"/>{health?.status === 'ok' ? '运行中' : '服务可访问'}</dd></div><div><dt><HardDrive size={17}/>数据存储</dt><dd>{connectionLabel(health?.database)}</dd></div><div><dt><Layers3 size={17}/>活动模型</dt><dd>{model.active?.name || '尚未配置'}</dd></div><div><dt><Settings2 size={17}/>模型适配器</dt><dd>{model.active ? `ONNX · ${model.active.class_count} 类叶片分类` : '待训练模型验证'}</dd></div></dl><div className="model-supported"><span>{model.active ? '模型支持作物' : '当前可采集作物'}</span><div>{(model.active ? model.supported_crops : model.available_crops).map(crop => <span key={crop}><CropIcon crop={crop} size={26}/>{crop}</span>)}</div></div></section><section className="panel model-roadmap"><div className="panel-header"><h2>接入流程</h2><Sprout size={20}/></div>{[['基础系统', '图片上传、样本管理与数据存储已就绪。', true], ['训练与验证', model.active ? `独立测试集 Top-1 ${(model.active.test_top1 * 100).toFixed(2)}%，宏平均 F1 ${(model.active.test_macro_f1 * 100).toFixed(2)}%。` : '准备数据集，训练并验证作物识别模型。', !!model.active], ['适配推理接口', 'ONNX 推理、类别映射与置信度校验。', !!model.active], ['上线识别', '启用后分析新上传的图片；历史待检测样本保留原状态。', !!model.active]].map(([title, description, done], index) => <div className={`roadmap-step ${done ? 'done' : ''}`} key={String(title)}><span>{done ? <Check size={15}/> : index + 1}</span><div><h3>{title}</h3><p>{description}</p></div></div>)}</section></div><div className="notice"><ShieldCheck size={19}/><div><strong>结果真实，才能判断可靠</strong><p>没有加载并验证模型时，上传记录会保留为“等待模型”，不会生成模拟识别结果。</p></div></div></>
}

export function SettingsPage({health, user, onLogin, onLogout}: {health: Health | null; user: User | null; onLogin: () => void; onLogout: () => void}) {
  const [compact, setCompact] = useState(localStorage.getItem('agriscan-compact') === 'true')
  const [motion, setMotion] = useState(localStorage.getItem('agriscan-motion') !== 'false')
  const change = (key: string, value: boolean) => {localStorage.setItem(`agriscan-${key}`, String(value)); document.documentElement.classList.toggle(key === 'compact' ? 'compact' : 'reduce-motion', key === 'compact' ? value : !value)}
  return <><div className="settings-grid"><section className="panel settings-panel"><div className="panel-header"><h2>个人与偏好</h2><Settings2 size={19}/></div><div className="account-card"><div className="avatar">{user ? user.name.charAt(0) : '访'}</div><div><strong>{user?.name || '访客'}</strong><p>{user ? (user.role === 'admin' ? '管理员 · 管理样本、地块与模型' : '普通成员 · 浏览共享数据与上传样本') : '登录后可以上传样本、管理地块'}</p></div><button className="button outline" onClick={user ? onLogout : onLogin}>{user ? '退出登录' : '登录账户'}</button></div><div className="setting-row"><div><strong>紧凑布局</strong><p>缩小表格行距，在同一屏展示更多记录</p></div><button className={`switch ${compact ? 'on' : ''}`} role="switch" aria-checked={compact} aria-label="紧凑布局" onClick={() => {setCompact(!compact); change('compact', !compact)}}><span/></button></div><div className="setting-row"><div><strong>界面动效</strong><p>小禾逐帧动画与界面过渡，关闭后显示静态形象</p></div><button className={`switch ${motion ? 'on' : ''}`} role="switch" aria-checked={motion} aria-label="界面动效" onClick={() => {setMotion(!motion); change('motion', !motion)}}><span/></button></div></section><section className="panel settings-panel"><div className="panel-header"><h2>系统信息</h2><Leaf size={19}/></div><dl className="status-list"><div><dt>系统名称</dt><dd>AgriScan 禾观</dd></div><div><dt>版本</dt><dd>1.0.0 · 基础版</dd></div><div><dt>运行模式</dt><dd>{health?.mode === 'demo' ? '演示模式' : '标准模式'}</dd></div><div><dt>数据库</dt><dd>{connectionLabel(health?.database)}</dd></div><div><dt>Redis</dt><dd>{connectionLabel(health?.redis)}</dd></div><div><dt>技术栈</dt><dd>React · FastAPI</dd></div></dl><a href="http://localhost:8000/docs" target="_blank" rel="noreferrer" className="text-button api-link">本地 API 文档 <ArrowUpRight size={15}/></a></section></div><XiaoheMotionDemo/></>
}

function connectionLabel(status?: string) { return status === 'connected' ? '已连接' : status === 'disabled' ? '本地演示未启用' : status === 'unavailable' ? '连接异常' : status || '未连接' }
