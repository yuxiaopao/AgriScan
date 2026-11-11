import {useEffect,useRef,useState} from 'react'
import {getServiceBase,getToken} from './api'

/** Form data and response callbacks belong to exactly one account session and service. */
export function usePlotScope(){
  const scope=useRef({token:getToken(),base:getServiceBase()})
  const alive=useRef(true),request=useRef<AbortController|null>(null)
  const [valid,setValid]=useState(Boolean(scope.current.token))
  const current=()=>alive.current&&Boolean(scope.current.token)&&getToken()===scope.current.token&&getServiceBase()===scope.current.base
  useEffect(()=>{
    alive.current=true
    const check=()=>{if(!current()){request.current?.abort();setValid(false)}}
    window.addEventListener('storage',check);window.addEventListener('focus',check);window.addEventListener('agriscan-mobile-auth-expired',check);window.addEventListener('agriscan-mobile-service-changed',check)
    return()=>{alive.current=false;request.current?.abort();window.removeEventListener('storage',check);window.removeEventListener('focus',check);window.removeEventListener('agriscan-mobile-auth-expired',check);window.removeEventListener('agriscan-mobile-service-changed',check)}
  },[])
  return {valid:valid&&current(),current,request}
}
