import {useEffect, useRef, useState, type FormEvent, type ReactNode} from 'react'
import {ImagePlus, Trash2, Upload, X} from 'lucide-react'
import {api} from './api'
import {Modal, SecureImage} from './components'
import PlotLocationPicker from './PlotLocationPicker'
import {readPlotDraft, writePlotDraft, type PlotDraft} from './plotDrafts'
import type {Plot} from './types'
import './plot-editor.css'

interface Props {plot: Plot | null; crops: string[]; owner: string; onChange: () => void; onClose: () => void; toast: (message: string) => void; apiPrefix?:'/plots'|'/admin/plots'; ownerId?:string|null; ownerField?:ReactNode}

export default function PlotEditor({plot, crops, owner, onChange, onClose, toast, apiPrefix='/plots', ownerId, ownerField}: Props) {
  const initial = useRef<PlotDraft>({name: plot?.name ?? '', crop: plot?.crop ?? crops[0] ?? '', area: plot?.area.toString() ?? '',
    location: plot?.location ?? '', manager: plot?.manager ?? '', latitude: plot?.latitude?.toString() ?? '',
    longitude: plot?.longitude?.toString() ?? '', file: null, removeCover: false, savedId: plot?.id})
  const [draft, setDraft] = useState(initial.current)
  const currentDraft = useRef(initial.current)
  const key = JSON.stringify([apiPrefix, owner, plot?.id ?? 'new'])
  const [ready, setReady] = useState(false)
  const [hasDraft, setHasDraft] = useState(false)
  const [cacheMessage, setCacheMessage] = useState('')
  const dirty = useRef(false)
  const {file, latitude, longitude, removeCover = false} = draft
  const [savedCoverUrl, setSavedCoverUrl] = useState(plot?.cover_url ?? null)
  const hasCover = Boolean(savedCoverUrl && !removeCover)
  const [preview, setPreview] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let alive = true
    readPlotDraft(key).then(cached => {
      if (!alive || !cached) return
      currentDraft.current = cached; setDraft(cached); dirty.current = true; setHasDraft(true)
      setCacheMessage('已恢复上次未保存的修改')
    }).catch(() => {if (alive) setCacheMessage('浏览器草稿暂不可用，请及时保存地块。')})
      .finally(() => {if (alive) setReady(true)})
    return () => {alive = false}
  }, [key])

  function updateDraft(changes: Partial<PlotDraft>) {
    const next = {...currentDraft.current, ...changes}
    currentDraft.current = next; setDraft(next); dirty.current = true; setHasDraft(true)
    void writePlotDraft(key, next).then(() => setCacheMessage('草稿已保存在当前浏览器，下次打开可继续编辑'))
      .catch(() => setCacheMessage('草稿保存失败，请先保存地块后再关闭。'))
  }

  async function close() {
    if (busy) return
    try {
      if (dirty.current) await writePlotDraft(key, currentDraft.current)
      onClose()
    } catch {setCacheMessage('草稿保存失败，请先保存地块后再关闭。')}
  }

  async function discard() {
    setBusy(true)
    try {await writePlotDraft(key, null); onClose()}
    catch {setCacheMessage('未能清除草稿，请重试。')}
    finally {setBusy(false)}
  }

  useEffect(() => {
    if (!file) {setPreview(''); return}
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  function choose(next?: File) {
    if (!next || busy) return
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(next.type)) {setError('封面仅支持 JPG、PNG、WebP 图片。'); return}
    if (next.size > 10 * 1024 * 1024) {setError('封面图片不能超过 10 MB。'); return}
    setError(''); updateDraft({file: next, removeCover: false})
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy || !ready) return
    const {file: pendingFile, savedId, removeCover: deleteCover, latitude: lat, longitude: lng, ...fields} = currentDraft.current
    const body = {...fields, area: Number(fields.area), latitude: lat === '' ? null : Number(lat), longitude: lng === '' ? null : Number(lng), ...(apiPrefix==='/admin/plots'&&ownerId!==undefined?{owner_id:ownerId}:{})}
    setBusy(true); setError('')
    let detailsSaved = false
    try {
      const saved = await api<Plot>(`${apiPrefix}${savedId ? `/${savedId}` : ''}`, {
        method: savedId ? 'PATCH' : 'POST', body: JSON.stringify(body),
      })
      updateDraft({savedId: saved.id})
      setSavedCoverUrl(saved.cover_url ?? null)
      detailsSaved = true
      if (pendingFile) {
        const upload = new FormData(); upload.append('file', pendingFile)
        const updated = await api<Plot>(`${apiPrefix}/${saved.id}/cover`, {method: 'POST', body: upload})
        setSavedCoverUrl(updated.cover_url ?? null)
        updateDraft({file: null, removeCover: false})
      } else if (deleteCover) {
        const updated = await api<Plot>(`${apiPrefix}/${saved.id}/cover`, {method: 'DELETE'})
        setSavedCoverUrl(updated.cover_url ?? null)
        updateDraft({removeCover: false})
      }
      try {await writePlotDraft(key, null); toast('地块信息已保存。')}
      catch {toast('地块已保存，但浏览器草稿未能清理。')}
      onClose()
    } catch (e) {
      setError(`${detailsSaved ? '地块信息已保存，封面修改未完成，请重试。' : ''}${(e as Error).message}`)
    } finally {
      if (detailsSaved) onChange()
      setBusy(false)
    }
  }

  return <Modal title={plot ? '编辑地块' : '添加地块'} wide onClose={() => void close()}>
    <form className="modal-form plot-editor" onSubmit={save}>
      {error && <div className="plot-editor-error" role="alert">{error}</div>}
      {apiPrefix==='/admin/plots'&&<fieldset disabled={busy}>{ownerField}<p className="plot-draft-status">变更归属会改变用户端可见范围。有关联其他用户检测记录的地块不能直接转移，请先调整关联；不会批量转移历史样本。</p></fieldset>}
      {!ready && <div className="plot-draft-status" role="status">正在恢复草稿…</div>}
      {cacheMessage && <div className="plot-draft-status" role="status"><span>{cacheMessage}</span>{hasDraft && <button type="button" onClick={() => void discard()} disabled={busy}>放弃草稿</button>}</div>}
      {ready && <fieldset disabled={busy}><div className="plot-editor-layout"><section className="plot-editor-details">
        <div className="plot-cover-field"><span>地块封面<span className="quiet">JPG / PNG / WebP · 最大 10 MB</span></span><div className="plot-cover-preview">
          {file && preview ? <img src={preview} alt="地块封面预览"/> : hasCover && savedCoverUrl ? <SecureImage url={savedCoverUrl} alt="当前地块封面"/> : <div className="plot-cover-placeholder"><ImagePlus size={26}/><span>{removeCover ? '保存后将移除当前封面' : '添加一张地块实景'}</span></div>}
          <button type="button" className="plot-cover-select" onClick={() => input.current?.click()}><Upload size={14}/>{file || hasCover ? '更换封面' : '选择封面图片'}</button>
          {file && <button type="button" className="plot-cover-clear" aria-label="取消所选封面" onClick={() => {updateDraft({file: null}); if (input.current) input.current.value = ''}}><X size={15}/></button>}
        </div><input ref={input} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" aria-label="上传地块封面" onChange={event => choose(event.target.files?.[0])}/>
          {savedCoverUrl && <div className="plot-cover-removal">{removeCover ? <><span role="status">已标记删除，保存地块后生效</span><button type="button" onClick={() => updateDraft({removeCover: false})}>撤销删除</button></> : <button type="button" onClick={() => {updateDraft({file: null, removeCover: true}); if (input.current) input.current.value = ''}}><Trash2 size={12}/>删除已有封面</button>}</div>}
        </div>
        <label>地块名称<input name="name" autoComplete="off" required maxLength={100} value={draft.name} onChange={event => updateDraft({name: event.target.value})} placeholder="例如：东区番茄大棚"/></label>
        <div className="form-grid"><label>种植作物<select name="crop" value={draft.crop} onChange={event => updateDraft({crop: event.target.value})}>{crops.map(crop => <option key={crop}>{crop}</option>)}</select></label><label>种植面积 / 亩<input name="area" required type="number" min=".01" max="1000000" step=".01" value={draft.area} onChange={event => updateDraft({area: event.target.value})}/></label></div>
        <label>负责人<input name="manager" maxLength={80} value={draft.manager} onChange={event => updateDraft({manager: event.target.value})}/></label>
      </section><section className="plot-editor-position"><label>地块位置<input name="location" maxLength={200} value={draft.location} onChange={event => updateDraft({location: event.target.value})} placeholder="园区、乡镇或详细地址"/></label>
        <PlotLocationPicker latitude={latitude} longitude={longitude} disabled={busy} onChange={(lat, lng) => updateDraft({latitude: lat, longitude: lng})}/>
      </section></div></fieldset>}
      <div className="modal-actions"><button type="button" className="button outline" disabled={busy} onClick={() => void close()}>关闭</button><button className="button primary" disabled={busy || !ready}>{busy ? '保存中…' : '保存地块'}</button></div>
    </form>
  </Modal>
}
