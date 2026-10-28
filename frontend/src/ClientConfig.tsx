import {createContext, useContext, useEffect, useState, type ReactNode} from 'react'
import {api} from './api'

interface ClientConfiguration {
  brand: {app_name: string; tagline: string; announcement: string}
  features: {image_detection: boolean; video_detection: boolean; live_detection: boolean; assistant: boolean; knowledge: boolean; plots: boolean}
  limits: {image_max_mb: number; video_max_mb: number; video_max_seconds: number; video_max_frames: number; frame_interval_ms: number}
  version: number
}
const defaults: ClientConfiguration = {
  brand:{app_name:'禾观 AgriScan',tagline:'看见生长的力量',announcement:''},
  features:{image_detection:true,video_detection:true,live_detection:true,assistant:true,knowledge:true,plots:true},
  limits:{image_max_mb:10,video_max_mb:50,video_max_seconds:60,video_max_frames:8,frame_interval_ms:750},version:0,
}
const ConfigurationContext=createContext(defaults)
export const useClientConfiguration=()=>useContext(ConfigurationContext)
export function ClientConfigurationProvider({children}:{children:ReactNode}) {
  const [config,setConfig]=useState(defaults)
  useEffect(()=>{
    let alive=true, running=false
    const update=async()=>{if(running||document.hidden)return;running=true;try{const value=await api<ClientConfiguration>('/client/config');if(alive)setConfig(value)}catch{/* Retain the last known configuration during a network outage. */}finally{running=false}}
    void update();const interval=window.setInterval(()=>void update(),30000)
    window.addEventListener('focus',update);window.addEventListener('hashchange',update);document.addEventListener('visibilitychange',update)
    return()=>{alive=false;window.clearInterval(interval);window.removeEventListener('focus',update);window.removeEventListener('hashchange',update);document.removeEventListener('visibilitychange',update)}
  },[])
  return <ConfigurationContext.Provider value={config}>{children}</ConfigurationContext.Provider>
}
