import {useEffect, useState} from 'react'
import {ChevronLeft, ChevronRight} from 'lucide-react'
import {api} from './api'

interface OwnerUser {id:string;name:string;username:string;is_active:boolean}
interface UserPage {items:OwnerUser[];total:number;page:number;page_size:number}
interface Props {
  value:string;onChange:(value:string)=>void;label?:string;selectedLabel?:string
  emptyLabel?:string;disabled?:boolean
}

/** Server-paginated account selection; never silently drops accounts after page 1. */
export default function OwnerPicker({value,onChange,label='归属用户',selectedLabel,emptyLabel,disabled=false}:Props){
  const [search,setSearch]=useState(''),[delayed,setDelayed]=useState(''),[page,setPage]=useState(1)
  const [data,setData]=useState<UserPage|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState(''),[retry,setRetry]=useState(0)
  const [chosen,setChosen]=useState<{id:string;label:string}|null>(null)
  useEffect(()=>{const timer=window.setTimeout(()=>setDelayed(search),250);return()=>window.clearTimeout(timer)},[search])
  useEffect(()=>{
    const controller=new AbortController();setLoading(true);setError('');setData(null)
    const params=new URLSearchParams({page:String(page),page_size:'30',search:delayed})
    api<UserPage>('/admin/users?'+params,{signal:AbortSignal.any([controller.signal,AbortSignal.timeout(20000)])})
      .then(result=>{if(!controller.signal.aborted)setData(result)})
      .catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:'用户选项读取失败。')})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false)})
    return()=>controller.abort()
  },[page,delayed,retry])
  const pages=Math.max(1,Math.ceil((data?.total??0)/30))
  useEffect(()=>{if(data&&page>pages)setPage(pages)},[data,page,pages])
  return <div className="adm-owner-picker">
    <input aria-label={`查找${label}`} placeholder="查找姓名或用户名…" value={search} disabled={disabled} onChange={event=>{setSearch(event.target.value);setPage(1)}}/>
    <select aria-label={label} value={value} disabled={disabled||loading} onChange={event=>{const selected=data?.items.find(user=>user.id===event.target.value);if(selected)setChosen({id:selected.id,label:`${selected.name} · @${selected.username}`});onChange(event.target.value)}}>
      {emptyLabel&&<option value="">{emptyLabel}</option>}
      <option value="unassigned">历史待分配</option>
      {value&&value!=='unassigned'&&!data?.items.some(user=>user.id===value)&&<option value={value}>{chosen?.id===value?chosen.label:(selectedLabel||'已选择的用户')}</option>}
      {data?.items.map(user=><option value={user.id} key={user.id}>{user.name} · @{user.username}{user.is_active?'':'（已停用）'}</option>)}
    </select>
    {loading?<small role="status">正在读取用户…</small>:error?<small role="alert">{error}<button type="button" disabled={disabled} onClick={()=>setRetry(old=>old+1)}>重试</button></small>:<div className="adm-owner-pages"><small>共 {data?.total??0} 位用户</small>{pages>1&&<><button type="button" aria-label={`${label}上一页`} disabled={disabled||page<=1} onClick={()=>setPage(old=>old-1)}><ChevronLeft size={13}/></button><span>{page}/{pages}</span><button type="button" aria-label={`${label}下一页`} disabled={disabled||page>=pages} onClick={()=>setPage(old=>old+1)}><ChevronRight size={13}/></button></>}</div>}
  </div>
}
