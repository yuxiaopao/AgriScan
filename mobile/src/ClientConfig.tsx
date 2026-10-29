import {createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode} from 'react'
import {api, ApiError, getServiceBase} from './api'
import {isNativeAndroid} from './native'

export interface ClientConfig {
  version:number
  brand:{app_name:string;tagline:string;announcement:string}
  features:{image_detection:boolean;video_detection:boolean;live_detection:boolean;assistant:boolean;knowledge:boolean;plots:boolean}
  limits:{image_max_mb:number;video_max_mb:number;video_max_seconds:number;video_max_frames:number;frame_interval_ms:number}
}
const defaults:ClientConfig={version:0,brand:{app_name:'禾观 AgriScan',tagline:'看见生长的力量',announcement:''},features:{image_detection:true,video_detection:true,live_detection:true,assistant:true,knowledge:true,plots:true},limits:{image_max_mb:10,video_max_mb:50,video_max_seconds:60,video_max_frames:8,frame_interval_ms:750}}
const Context=createContext<{config:ClientConfig;refreshConfig:()=>Promise<void>;configError:string}>({config:defaults,refreshConfig:async()=>{},configError:''})
function normalize(input:Partial<ClientConfig>):ClientConfig {
  const brand={...defaults.brand};const features={...defaults.features};const limits={...defaults.limits}
  for(const key of Object.keys(brand) as (keyof typeof brand)[])if(typeof input.brand?.[key]==='string')brand[key]=input.brand[key]
  for(const key of Object.keys(features) as (keyof typeof features)[])if(typeof input.features?.[key]==='boolean')features[key]=input.features[key]
  for(const key of Object.keys(limits) as (keyof typeof limits)[]){const value=input.limits?.[key];if(typeof value==='number'&&Number.isFinite(value)&&value>0)limits[key]=value}
  return{version:typeof input.version==='number'?input.version:0,brand,features,limits}
}
export function ClientConfigProvider({children}:{children:ReactNode}) {
  const [config,setConfig]=useState(defaults);const [configError,setConfigError]=useState('');const request=useRef(0);const mounted=useRef(true)
  const refreshConfig=useCallback(async()=>{
    const version=++request.current;const service=getServiceBase()
    if(isNativeAndroid()&&!service){setConfig(defaults);setConfigError('');return}
    try{const value=await api<Partial<ClientConfig>>('/client/config');if(mounted.current&&request.current===version&&service===getServiceBase()){setConfig(normalize(value));setConfigError('')}}
    catch(e){if(mounted.current&&request.current===version&&service===getServiceBase()){if(e instanceof ApiError&&e.status===404){setConfig(defaults);setConfigError('')}else setConfigError('应用配置暂未更新，当前保留上次设置。')}}
  },[])
  useEffect(()=>{
    mounted.current=true;void refreshConfig()
    const visible=()=>{if(!document.hidden)void refreshConfig()};const changed=()=>{setConfig(defaults);void refreshConfig()}
    document.addEventListener('visibilitychange',visible);window.addEventListener('focus',visible);window.addEventListener('agriscan-mobile-service-changed',changed)
    return()=>{mounted.current=false;request.current++;document.removeEventListener('visibilitychange',visible);window.removeEventListener('focus',visible);window.removeEventListener('agriscan-mobile-service-changed',changed)}
  },[refreshConfig])
  useEffect(()=>{document.title=config.brand.app_name},[config.brand.app_name])
  return <Context.Provider value={{config,refreshConfig,configError}}>{children}</Context.Provider>
}
export const useClientConfig=()=>useContext(Context)
