import {useEffect,useRef,useState} from 'react'
import {getServiceBase,getToken} from './api'

export function validEmail(value:string){return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim())&&value.trim().length<=254}
export function resetError(email:string,code:string,password:string,confirm:string){
  if(!validEmail(email))return '请填写有效的邮箱地址。'
  if(!/^\d{6}$/.test(code))return '请输入 6 位数字验证码。'
  if(password.length<10||password.length>128)return '新密码需要 10 至 128 位字符。'
  if(password!==confirm)return '两次密码不一致，请重新输入确认密码。'
  return ''
}

/** Requests and sensitive form contents belong to one service and account session. */
export function useAccountScope(requireLogin=false){
  const identity=useRef({base:getServiceBase(),token:getToken(),route:window.location.hash})
  const alive=useRef(true),request=useRef<AbortController|null>(null)
  const [valid,setValid]=useState(true)
  function current(){return alive.current&&window.location.hash===identity.current.route&&getServiceBase()===identity.current.base&&getToken()===identity.current.token&&(!requireLogin||Boolean(identity.current.token))}
  function begin(){if(!current()||request.current)return null;const controller=new AbortController();request.current=controller;return controller}
  function finish(controller:AbortController){if(request.current===controller)request.current=null}
  useEffect(()=>{
    alive.current=true
    const check=()=>{if(!current()){request.current?.abort();setValid(false)}}
    const events=['storage','focus','hashchange','popstate','agriscan-mobile-service-changed','agriscan-mobile-auth-expired']
    events.forEach(event=>window.addEventListener(event,check));check()
    return()=>{alive.current=false;request.current?.abort();request.current=null;events.forEach(event=>window.removeEventListener(event,check))}
  },[])
  return {valid:valid&&current(),current,begin,finish}
}

/** An elapsed wall-clock deadline remains correct after the app returns to foreground. */
export function useMailCooldown(){
  const [until,setUntil]=useState(0),[now,setNow]=useState(Date.now())
  const seconds=Math.max(0,Math.ceil((until-now)/1000))
  useEffect(()=>{if(!until)return;const tick=()=>setNow(Date.now());tick();const timer=window.setInterval(tick,1000);window.addEventListener('focus',tick);return()=>{window.clearInterval(timer);window.removeEventListener('focus',tick)}},[until])
  return {seconds,start:()=>{const time=Date.now();setNow(time);setUntil(time+60000)}}
}
