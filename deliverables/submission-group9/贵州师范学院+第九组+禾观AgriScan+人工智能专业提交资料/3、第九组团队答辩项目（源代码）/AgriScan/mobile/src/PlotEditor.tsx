import {useRef,useState,type FormEvent} from 'react'
import {api,ApiError} from './api'
import {ErrorNote,SecureImage,Sheet} from './components'
import {useClientConfig} from './ClientConfig'
import {useObjectUrl} from './hooks'
import {IpIcon} from './IpIcon'
import {plotBody,plotDraft,type PlotDraft} from './plotDraft'
import type {Plot} from './types'
import {usePlotScope} from './usePlotScope'

export default function PlotEditor({plot,crops,manager,onSaved,onClose,onCheck}:{plot:Plot|null;crops:string[];manager:string;onSaved:(plot:Plot)=>void;onClose:()=>void;onCheck:()=>void}){
  const {config}=useClientConfig(),scope=usePlotScope()
  const enabled=useRef(config.features.plots);enabled.current=config.features.plots
  const [draft,setDraft]=useState(()=>plotDraft(plot,crops[0]??'',manager)),[cover,setCover]=useState<File|null>(null)
  const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[metadataSaved,setMetadataSaved]=useState(false),[uncertain,setUncertain]=useState(false)
  const saved=useRef<Plot|null>(plot),metadataCommitted=useRef(false),input=useRef<HTMLInputElement>(null)
  const preview=useObjectUrl(cover),maxImage=Math.min(10,config.limits.image_max_mb)
  const update=(key:keyof PlotDraft,value:string)=>{setDraft(old=>({...old,[key]:value}));setError('')}
  function chooseCover(file?:File){
    if(!file||busy||!scope.current()||!enabled.current)return
    if(!['image/jpeg','image/png','image/webp'].includes(file.type)){setError('封面请使用 JPG、PNG 或 WebP 图片。');return}
    if(file.size>maxImage*1024*1024){setError(`封面不能超过 ${maxImage} MB，请重新选择。`);return}
    setCover(file);setError('')
  }
  async function uploadCover(controller:AbortController){
    if(!cover||!saved.current||!enabled.current)return false
    const body=new FormData();body.append('file',cover)
    const result=await api<Plot>(`/plots/${saved.current.id}/cover`,{method:'POST',body,signal:controller.signal},60000)
    if(!scope.current()||scope.request.current!==controller)return false
    saved.current=result;onSaved(result);return true
  }
  async function submit(event:FormEvent){
    event.preventDefault()
    if(scope.request.current||!scope.current()||!enabled.current||uncertain)return
    let body
    try{if(!metadataCommitted.current)body=plotBody(draft,crops)}catch(reason){setError((reason as Error).message);return}
    const controller=new AbortController();scope.request.current=controller;setBusy(true);setError('');setNotice('')
    let phase:'metadata'|'cover'='metadata'
    try{
      if(!metadataCommitted.current){
        const result=await api<Plot>(saved.current?`/plots/${saved.current.id}`:'/plots',{method:saved.current?'PATCH':'POST',body:JSON.stringify(body),signal:controller.signal})
        if(!scope.current()||scope.request.current!==controller)return
        // Persist the returned ID before attempting the independent cover upload.
        saved.current=result;metadataCommitted.current=true;setMetadataSaved(true);onSaved(result)
      }
      phase='cover'
      if(cover){
        if(!enabled.current){setNotice('地块信息已保存。编辑已暂停，封面可在恢复后补传。');return}
        await uploadCover(controller)
        if(!scope.current()||scope.request.current!==controller)return
      }
      onClose()
    }catch(reason){
      if(!scope.current()||scope.request.current!==controller)return
      if(phase==='cover')setNotice('地块信息已保存，封面尚未上传。重试只补传封面，不会再创建地块。')
      else if(!plot&&(!(reason instanceof ApiError)||reason.status>=500)){setUncertain(true);setNotice('本次创建结果尚未确认。请先刷新地块列表核对，避免重复创建。')}
      setError((reason as Error).message)
    }finally{if(scope.request.current===controller){scope.request.current=null;if(scope.current())setBusy(false)}}
  }
  if(!scope.valid)return null
  return <Sheet title={plot?'编辑我的地块':'创建我的地块'} onClose={onClose} dismissible={!busy}>
    <form className="mobile-plot-editor" onSubmit={submit} noValidate aria-busy={busy}>
      <p className="plot-form-intro">地块保存在当前账户，之后可在检测时关联。</p>
      {!config.features.plots&&<p className="info-note" role="status">管理员已暂停地块编辑。已有信息仍保留，可稍后继续。</p>}
      <fieldset disabled={busy||metadataSaved||!config.features.plots||uncertain}>
        <label>地块名称<input autoComplete="off" value={draft.name} maxLength={100} onChange={event=>update('name',event.target.value)} placeholder="例如：东侧苹果园" required/></label>
        <div className="plot-form-pair"><label>种植作物<select value={draft.crop} onChange={event=>update('crop',event.target.value)} disabled={Boolean(plot?.detections)}>{crops.map(crop=><option key={crop}>{crop}</option>)}</select></label><label>种植面积（亩）<input type="number" inputMode="decimal" min="0" max="1000000" step="any" value={draft.area} onChange={event=>update('area',event.target.value)} placeholder="例如：2.5" required/></label></div>
        {!!plot?.detections&&<p className="form-hint">已有观察记录的地块保留原作物类型。</p>}
        <label>地块位置<input value={draft.location} maxLength={200} onChange={event=>update('location',event.target.value)} placeholder="村组、路口或便于找到的位置"/></label>
        <label>负责人<input value={draft.manager} maxLength={80} onChange={event=>update('manager',event.target.value)} placeholder="负责日常巡田的人"/></label>
        <details className="plot-coordinate-fields"><summary>经纬度位置（选填）</summary><p>同时填写经纬度，或都留空；清空两项可移除已有坐标。</p><div className="plot-form-pair"><label>纬度<input inputMode="decimal" value={draft.latitude} onChange={event=>update('latitude',event.target.value)} placeholder="负 90 至 90"/></label><label>经度<input inputMode="decimal" value={draft.longitude} onChange={event=>update('longitude',event.target.value)} placeholder="负 180 至 180"/></label></div></details>
      </fieldset>
      <section className="plot-cover-editor" aria-label="地块封面"><h3>地块封面<span>选填，也可以稍后添加</span></h3>{preview?<img src={preview} alt="待上传的地块封面"/>:plot?.cover_url?<SecureImage url={plot.cover_url} alt="当前地块封面"/>:<div className="plot-cover-empty"><IpIcon name="plots"/><span>拍一张种植区，回来时更容易找到。</span></div>}<input ref={input} type="file" className="visually-hidden" accept="image/jpeg,image/png,image/webp" aria-label="选择地块封面" disabled={busy||!config.features.plots||uncertain} onClick={event=>{event.currentTarget.value=''}} onChange={event=>chooseCover(event.target.files?.[0])}/><div><button className="button outline" type="button" disabled={busy||!config.features.plots||uncertain} onClick={()=>input.current?.click()}>{cover?'更换所选封面':plot?.cover_url?'更换封面':'选择封面'}</button>{cover&&<button className="text-button" type="button" disabled={busy} onClick={()=>{setCover(null);setError('')}}>取消本次封面</button>}</div><p className="form-hint">支持 JPG、PNG、WebP，最大 {maxImage} MB。</p></section>
      {notice&&<p className="info-note" role="status">{notice}</p>}<ErrorNote message={error}/>
      <div className="plot-editor-actions">{uncertain?<button className="button primary full" type="button" onClick={onCheck}>刷新列表并核对</button>:<button className="button primary full" disabled={busy||!config.features.plots}>{busy?(metadataSaved?'正在上传封面…':'正在保存地块…'):metadataSaved?(cover?'重试上传封面':'完成'):plot?'保存地块修改':'创建地块'}</button>}{metadataSaved&&<button className="button ghost full" type="button" disabled={busy} onClick={onClose}>完成，稍后补充封面</button>}</div>
    </form>
  </Sheet>
}
