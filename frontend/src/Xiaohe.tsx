import {useEffect, useRef, useState, type CSSProperties} from 'react'
import './xiaohe.css'

export type XiaoheState = 'idle' | 'wave' | 'scan' | 'think' | 'success' | 'concern'
const descriptions: Record<XiaoheState, string> = {
  idle: '小禾正在陪你巡田', wave: '小禾向你招手', scan: '小禾正在观察叶片',
  think: '小禾正在思考', success: '小禾已完成整理', concern: '小禾提醒你留意异常',
}
const durations: Record<XiaoheState, number> = {idle: 2.4, wave: 1.2, scan: 1.6, think: 1.8, success: 1.4, concern: 1.8}

/** Generated image frames; only the film strip is moved, never the character artwork. */
export function Xiaohe({state = 'idle', className = '', label, paused = false}: {
  state?: XiaoheState; className?: string; label?: string; paused?: boolean
}) {
  const host = useRef<HTMLSpanElement>(null)
  const [visible, setVisible] = useState(true)
  const [pageVisible, setPageVisible] = useState(!document.hidden)
  const [loaded, setLoaded] = useState('')
  const ready = loaded === state
  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting))
    if (host.current) observer.observe(host.current)
    const change = () => setPageVisible(!document.hidden)
    document.addEventListener('visibilitychange', change)
    return () => {observer.disconnect(); document.removeEventListener('visibilitychange', change)}
  }, [])
  return <span ref={host} role="img" aria-label={label || descriptions[state]}
    className={`xiaohe-sprite ${className}`} data-state={state} data-paused={paused || !visible || !pageVisible}
    style={{'--xiaohe-duration': `${durations[state]}s`} as CSSProperties}>
    {!ready && <img className="xiaohe-fallback" src="/images/xiaohe.png" alt=""/>}
    <img key={state} className="xiaohe-film" src={`/images/xiaohe-motion/${state}.webp`} alt=""
      draggable={false} onLoad={() => setLoaded(state)} onError={() => setLoaded('')}
      style={{visibility: ready ? 'visible' : 'hidden'}}/>
  </span>
}
