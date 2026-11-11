import {useEffect, useRef, useState, type CSSProperties} from 'react'
import {useCropTheme} from './CropTheme'
import {getCropTheme} from './cropThemes'
import './xiaohe.css'

export type XiaoheState = 'idle' | 'wave' | 'scan' | 'think' | 'success' | 'concern'
const descriptions: Record<XiaoheState, string> = {
  idle: '小禾正在陪你巡田', wave: '小禾向你问好', scan: '小禾正在仔细观察',
  think: '小禾正在思考', success: '小禾已完成整理', concern: '小禾提醒你留意异常',
}
const durations: Record<XiaoheState, number> = {idle: 2.4, wave: 1.6, scan: 1.6, think: 2.2, success: 1.8, concern: 2.6}

/** null opts into the original six action strips for the animation preview. */
export function Xiaohe({state = 'idle', className = '', label, paused = false, crop}: {
  state?: XiaoheState; className?: string; label?: string; paused?: boolean; crop?: string | null
}) {
  const {crop: activeCrop} = useCropTheme()
  const cropTheme = crop === null ? undefined : getCropTheme(crop ?? activeCrop)
  const source = cropTheme ? `/images/xiaohe-crops/${cropTheme.id}.webp` : `/images/xiaohe-motion/${state}.webp`
  const fallback = cropTheme ? `/images/xiaohe-crops/${cropTheme.id}-still.webp` : '/images/xiaohe.png'
  const host = useRef<HTMLSpanElement>(null)
  const [visible, setVisible] = useState(true)
  const [pageVisible, setPageVisible] = useState(!document.hidden)
  const [loaded, setLoaded] = useState('')
  const ready = loaded === source
  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting))
    if (host.current) observer.observe(host.current)
    const change = () => setPageVisible(!document.hidden)
    document.addEventListener('visibilitychange', change)
    return () => {observer.disconnect(); document.removeEventListener('visibilitychange', change)}
  }, [])
  return <span ref={host} role="img" aria-label={label || `${descriptions[state]}${cropTheme ? `，手持${cropTheme.crop}` : ''}`}
    className={`xiaohe-sprite ${className}`} data-state={state} data-crop={cropTheme?.id}
    data-paused={paused || !visible || !pageVisible}
    style={{'--xiaohe-duration': `${durations[state]}s`} as CSSProperties}>
    {!ready && <img className="xiaohe-fallback" src={fallback} alt="" draggable={false}/>}
    <img key={source} className="xiaohe-film" src={source} alt=""
      draggable={false} onLoad={() => setLoaded(source)} onError={() => setLoaded('')}
      style={{visibility: ready ? 'visible' : 'hidden'}}/>
  </span>
}
