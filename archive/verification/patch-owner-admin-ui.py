from pathlib import Path

path=Path('admin/src/Admin.tsx')
source=path.read_text(encoding='utf-8')
def replace_once(old,new):
    global source
    if source.count(old)!=1:
        raise RuntimeError('Expected one edit anchor: '+old[:80])
    source=source.replace(old,new,1)

replace_once("import RuntimeSettings from './RuntimeSettings'", "import RuntimeSettings from './RuntimeSettings'\nimport OwnerPicker from './OwnerPicker'")
replace_once("interface CommonProps {revision: number; changed: () => void; toast: (message: string) => void}", """interface CommonProps {revision: number; changed: () => void; toast: (message: string) => void}
interface Ownership {owner_id:string|null;owner_name:string|null;owner_username:string|null}
type AdminDetection = Detection & Ownership
type AdminPlot = Plot & Ownership
function ownerText(row:Ownership){return row.owner_id?`${row.owner_name||'用户'}${row.owner_username?' · @'+row.owner_username:''}`:'历史待分配'}""")
replace_once("const filter = useFilters({search: '', crop: ''}), state = useLoad<PageData<Plot>>(query('/admin/plots',", "const filter = useFilters({search: '', crop: '', owner_id: ''}), state = useLoad<PageData<AdminPlot>>(query('/admin/plots',")
replace_once("[editing, setEditing] = useState<Plot | 'new' | null>(null), [removing, setRemoving] = useState<Plot | null>(null)", "[editing, setEditing] = useState<AdminPlot | 'new' | null>(null), [removing, setRemoving] = useState<AdminPlot | null>(null)")
replace_once('地块封面、定位和编辑草稿与工作台同步。', '按归属用户维护地块。用户端仅显示本人地块，历史待分配数据仅管理端可见。')
replace_once('<select aria-label="地块作物"', '<OwnerPicker value={filter.filters.owner_id} onChange={value=>filter.set(\'owner_id\',value)} emptyLabel="全部用户"/><select aria-label="地块作物"')
replace_once('<th>种植地块</th><th>作物 / 面积</th>', '<th>种植地块</th><th>归属用户</th><th>作物 / 面积</th>')
replace_once('</div></div></td><td>{plot.crop}<small', '</div></div></td><td>{ownerText(plot)}</td><td>{plot.crop}<small')
replace_once("{editing && <PlotEditor key={editing === 'new' ? 'new' : editing.id} plot={editing === 'new' ? null : editing} owner={user.username} crops={crops} onClose={() => setEditing(null)} onChange={changed} toast={toast}/>}", "{editing && <AdminPlotEditor key={editing === 'new' ? 'new' : editing.id} plot={editing === 'new' ? null : editing} user={user} crops={crops} onClose={() => setEditing(null)} onChange={changed} toast={toast}/>}")
replace_once("await api('/plots/' + removing.id, {method: 'DELETE'})", "await api('/admin/plots/' + removing.id, {method: 'DELETE'})")
replace_once("function DetectionsAdmin({revision, changed, toast}: CommonProps) {", """function AdminPlotEditor({plot,user,...props}:{plot:AdminPlot|null;user:User;crops:string[];onClose:()=>void;onChange:()=>void;toast:(message:string)=>void}){
  const [owner,setOwner]=useState(plot?(plot.owner_id??'unassigned'):'')
  return <PlotEditor {...props} plot={plot} owner={user.username} apiPrefix="/admin/plots" ownerId={owner===''?undefined:owner==='unassigned'?null:owner}
    ownerField={<div className="adm-owner-field"><strong>归属用户</strong><OwnerPicker value={owner} onChange={setOwner} selectedLabel={plot?ownerText(plot):undefined} emptyLabel={!plot?'当前管理员（默认）':undefined}/><small>选择历史待分配后，该地块不会出现在任何用户的个人工作台。</small></div>}/>
}

function DetectionsAdmin({revision, changed, toast}: CommonProps) {""")
replace_once("useFilters({search: '', crop: '', status: '', plot_id: '', source: '', date_from: '', date_to: ''})", "useFilters({search: '', crop: '', status: '', plot_id: '', source: '', date_from: '', date_to: '', owner_id: ''})")
replace_once("[selected, setSelected] = useState<Detection | null>(null), [editing, setEditing] = useState<Detection | null>(null), [removing, setRemoving] = useState<Detection | null>(null)", "[selected, setSelected] = useState<AdminDetection | null>(null), [editing, setEditing] = useState<AdminDetection | null>(null), [removing, setRemoving] = useState<AdminDetection | null>(null)")
replace_once("const plots = useLoad<PageData<Plot>>(query('/admin/plots', {search: plotSearch, page: 1, page_size: 100}), revision)", "const plots = useLoad<PageData<AdminPlot>>(query('/admin/plots', {search: plotSearch, owner_id:filter.filters.owner_id, page: 1, page_size: 100}), revision)")
replace_once("useLoad<PageData<Detection>>(invalidDates ? null : query('/admin/detections',", "useLoad<PageData<AdminDetection>>(invalidDates ? null : query('/admin/detections',")
replace_once('<select aria-label="检测作物"', '<OwnerPicker value={filter.filters.owner_id} onChange={value=>{filter.set(\'owner_id\',value);filter.set(\'plot_id\',\'\')}} emptyLabel="全部用户"/><select aria-label="检测作物"')
replace_once('<th>检测样本</th><th>作物 / 地块</th>', '<th>检测样本</th><th>归属用户</th><th>作物 / 地块</th>')
replace_once('</div></div></td><td>{row.crop}<small', '</div></div></td><td>{ownerText(row)}</td><td>{row.crop}<small')
replace_once('onEdit={() => {setEditing(selected); setSelected(null)}}', 'onEdit={record => {setEditing(record); setSelected(null)}}')
replace_once("await api('/detections/' + removing.id, {method: 'DELETE'})", "await api('/admin/detections/' + removing.id, {method: 'DELETE'})")

start=source.index('function DetectionDetail(')
end=source.index('\nfunction KnowledgeAdmin(',start)
source=source[:start]+'''function DetectionDetail({record,onClose,onEdit}:{record:AdminDetection;onClose:()=>void;onEdit:(record:AdminDetection)=>void}){
  const detail=useLoad<AdminDetection>('/admin/detections/'+record.id)
  const row=detail.data
  return <Modal title="检测样本详情" wide onClose={onClose}><div className="adm-form">
    {detail.loading?<Busy/>:detail.error?<ErrorBox text={detail.error} retry={detail.reload}/>:row&&<>
      <div className="adm-detection-detail"><div className="adm-detail-photo">{row.image_url?<SecureImage url={row.image_url} alt={row.name}/>:<div><Leaf size={45}/><p>此样本无原始照片</p></div>}</div><div><h3>{row.name}</h3><div className="adm-detail-badges"><Badge status={row.status}/>{row.is_demo&&<Pill>演示数据</Pill>}</div><dl className="adm-description">
        <div><dt>归属用户</dt><dd>{ownerText(row)}</dd></div><div><dt>作物</dt><dd>{row.crop}</dd></div><div><dt>所属地块</dt><dd>{row.plot_name}</dd></div><div><dt>识别结果</dt><dd>{row.result||'暂无结论'}</dd></div><div><dt>原始置信度</dt><dd>{confidenceText(row.confidence)}</dd></div><div><dt>入库时间</dt><dd>{dateText(row.created_at)}</dd></div><div><dt>备注</dt><dd>{row.note||'未填写'}</dd></div>
      </dl></div></div><PredictionScores record={row}/>{row.prediction_model&&<div className="adm-model-snapshot"><strong>当次模型快照</strong><p>{row.prediction_model.name} · {row.prediction_model.task}</p><code>{row.prediction_model.onnx_sha256}</code></div>}
    </>}
    <div className="adm-form-footer"><Button onClick={onClose}>关闭</Button>{row&&<Button tone="primary" onClick={()=>onEdit(row)}><Pencil size={15}/>编辑样本信息</Button>}</div>
  </div></Modal>
}
function DetectionEditor({record,onClose,onSaved}:{record:AdminDetection;onClose:()=>void;onSaved:()=>void}){
  const [name,setName]=useState(record.name),[note,setNote]=useState(record.note),[owner,setOwner]=useState(record.owner_id??'unassigned')
  const [plotId,setPlotId]=useState(record.plot_id??''),[search,setSearch]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('')
  const plots=useLoad<PageData<AdminPlot>>(owner==='unassigned'?null:query('/admin/plots',{crop:record.crop,search,owner_id:owner,page:1,page_size:100}))
  const ownerChanged=owner!==(record.owner_id??'unassigned')
  async function submit(event:FormEvent){
    event.preventDefault();if(busy)return;setBusy(true);setError('')
    try{await api('/admin/detections/'+record.id,{method:'PATCH',body:JSON.stringify({name:name.trim(),note:note.trim(),owner_id:owner==='unassigned'?null:owner,plot_id:plotId||null})});onSaved()}
    catch(reason){setError(message(reason))}finally{setBusy(false)}
  }
  return <Modal title="编辑样本信息" onClose={()=>{if(!busy)onClose()}}><form className="adm-form" onSubmit={submit}>
    <div className="adm-info"><ShieldCheck size={16}/><span>识别结果、置信度、候选与模型快照不能修改。调整归属会改变个人工作台的可见范围。</span></div>
    <div className="adm-owner-field"><strong>归属用户</strong><OwnerPicker value={owner} selectedLabel={ownerText(record)} disabled={busy} onChange={value=>{setOwner(value);setPlotId('');setSearch('')}}/></div>
    {ownerChanged&&<p className="adm-help">归属已变更，原地块关联已取消。可重新选择同一用户的同作物地块。</p>}
    <label>样本名称<input required maxLength={180} value={name} onChange={event=>setName(event.target.value)} disabled={busy}/></label>
    <label>查找归属用户的同作物地块<input value={search} onChange={event=>setSearch(event.target.value)} placeholder="输入地块名称…" disabled={busy||owner==='unassigned'}/></label>
    <label>所属地块<select value={plotId} onChange={event=>setPlotId(event.target.value)} disabled={busy||plots.loading}><option value="">不关联地块</option>{!ownerChanged&&record.plot_id&&!plots.data?.items.some(plot=>plot.id===record.plot_id)&&<option value={record.plot_id}>{record.plot_name}（当前关联）</option>}{plots.data?.items.map(plot=><option key={plot.id} value={plot.id}>{plot.name}</option>)}</select><small>{owner==='unassigned'?'请先分配归属用户再关联新地块；已有历史关联可保留或解除。':`只可关联此用户的${record.crop}地块；也可以不关联。`}</small></label>
    {plots.error&&<ErrorBox text={plots.error} retry={plots.reload}/>}<label>样本备注<textarea value={note} onChange={event=>setNote(event.target.value)} rows={4} maxLength={2000} disabled={busy}/></label>
    {error&&<ErrorBox text={error}/>}<FormFooter busy={busy} onClose={onClose}/>
  </form></Modal>
}
''' + source[end:]
path.write_text(source,encoding='utf-8')
print('Admin ownership paths, filters, detail and editor updated.')
