import {useEffect,useRef,useState} from 'react'
import {DetectionTaskManager,type DetectionTaskInput,type ManagedDetectionTask} from '../../shared/detectionTasks'
import {api,endpoint,getServiceBase,getToken,setToken} from './api'
import type {Detection,User} from './types'

export type {ManagedDetectionTask,DetectionTaskInput}
export interface TaskRuntime {
  jobs:readonly ManagedDetectionTask[];available:boolean
  enqueue:(input:DetectionTaskInput)=>string;cancel:(key:string)=>Promise<void>;dispose:()=>void
  results:(job:ManagedDetectionTask,signal:AbortSignal)=>Promise<Detection[]>
}
export const taskFinished=(job:ManagedDetectionTask)=>['completed','cancelled','failed'].includes(job.status)

export function useDetectionTasks(user:User|null,onCompleted:(job:ManagedDetectionTask)=>void):TaskRuntime {
  const token=getToken(),base=getServiceBase(),username=user?.username??''
  const identity=JSON.stringify([username,token,base])
  const currentIdentity=useRef(identity);currentIdentity.current=identity
  const completed=useRef(onCompleted);completed.current=onCompleted
  const holder=useRef<{identity:string;manager:DetectionTaskManager}|null>(null)
  const cache=useRef(new Map<string,Detection[]>())
  const [state,setState]=useState<{identity:string;jobs:readonly ManagedDetectionTask[]}>({identity:'',jobs:[]})
  useEffect(()=>{
    cache.current.clear();setState({identity,jobs:[]})
    if(!user||!token)return
    let active=true
    const isCurrent=()=>active&&currentIdentity.current===identity&&getToken()===token&&getServiceBase()===base
    const manager=new DetectionTaskManager({apiBaseUrl:new URL(endpoint(''),window.location.href).href,token,isCurrent,onUnauthorized:()=>{if(isCurrent()){setToken(null);window.dispatchEvent(new Event('agriscan-mobile-auth-expired'))}}})
    holder.current={identity,manager}
    const seen=new Set<string>()
    const unsubscribe=manager.subscribe(jobs=>{
      if(!isCurrent())return
      setState({identity,jobs})
      for(const job of jobs)if(job.status==='completed'&&!seen.has(job.key)){seen.add(job.key);completed.current(job)}
    })
    const invalidate=()=>{if(!isCurrent()){manager.dispose();cache.current.clear();if(active)setState({identity:'',jobs:[]})}}
    window.addEventListener('storage',invalidate);window.addEventListener('focus',invalidate);window.addEventListener('agriscan-mobile-service-changed',invalidate);window.addEventListener('agriscan-mobile-auth-expired',invalidate)
    return()=>{active=false;unsubscribe();manager.dispose();if(holder.current?.manager===manager)holder.current=null;cache.current.clear();window.removeEventListener('storage',invalidate);window.removeEventListener('focus',invalidate);window.removeEventListener('agriscan-mobile-service-changed',invalidate);window.removeEventListener('agriscan-mobile-auth-expired',invalidate)}
  },[identity])
  const current=()=>holder.current?.identity===identity&&Boolean(token)&&getToken()===token&&getServiceBase()===base
  return {
    jobs:state.identity===identity?state.jobs:[],available:Boolean(user&&token&&holder.current?.identity===identity),
    enqueue(input){if(!current())throw new Error('检测任务尚未连接，请稍候或重新登录。');return holder.current!.manager.enqueue(input)},
    async cancel(key){if(!current())return;await holder.current!.manager.cancel(key)},
    dispose(){holder.current?.manager.dispose();holder.current=null;cache.current.clear();setState({identity:'',jobs:[]})},
    async results(job,signal){
      if(!current()||job.status!=='completed'||!job.task)throw new Error('当前任务还没有可查看的结果。')
      if(!job.task.result_ids.length)throw new Error('任务未返回观察记录，请刷新记录列表确认。')
      const existing=cache.current.get(job.key);if(existing)return existing
      const rows=await Promise.all(job.task.result_ids.map(id=>api<Detection>(`/detections/${encodeURIComponent(id)}`,{signal})))
      if(!current()||signal.aborted)throw new Error('账户或服务已变化，已停止读取结果。')
      cache.current.set(job.key,rows);return rows
    },
  }
}
