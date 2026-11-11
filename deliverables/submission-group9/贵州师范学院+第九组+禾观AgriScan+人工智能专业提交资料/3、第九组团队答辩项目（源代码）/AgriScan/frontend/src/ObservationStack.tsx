import {useId, useRef, useState, type CSSProperties} from 'react'
import {flushSync} from 'react-dom'
import {ArrowUpRight, ChevronDown, Layers3} from 'lucide-react'
import {Badge, CropIcon} from './components'
import type {Detection} from './types'
import {motionCurve, reducedMotion} from './motion'

export default function ObservationStack({records, onSelect}: {records: Detection[]; onSelect: (record: Detection) => void}) {
  const [expanded, setExpanded] = useState(false)
  const id = useId()
  const host = useRef<HTMLDivElement>(null)
  const items = records.slice(0, 3)
  function toggle() {
    const followers = [host.current?.nextElementSibling, host.current?.parentElement?.nextElementSibling].filter((node): node is HTMLElement => node instanceof HTMLElement)
    const positions = followers.map(node => node.getBoundingClientRect().top)
    flushSync(() => setExpanded(value => !value))
    if (!reducedMotion()) followers.forEach((node, index) => {
      const distance = positions[index] - node.getBoundingClientRect().top
      node.animate([{transform: `translateY(${distance}px)`}, {transform: 'translateY(0)'}], {duration: 650, easing: motionCurve})
    })
  }
  if (!items.length) return null
  return <div ref={host} className={`observation-stack ${expanded ? 'expanded' : ''}`} style={{'--stack-count': items.length} as CSSProperties}>
    <button className="stack-toggle" aria-expanded={expanded} aria-controls={id} onClick={toggle}><Layers3 size={16}/><span>最近的田间观察<small>{expanded ? '点击卡片查看完整记录' : `${items.length} 份记录，展开快速浏览`}</small></span><ChevronDown size={17}/></button>
    <div id={id} className="observation-cards">
      {items.map((record, index) => <button key={record.id} className="observation-card" style={{'--card-index': index} as CSSProperties} tabIndex={expanded || index === 0 ? 0 : -1} aria-hidden={!expanded && index > 0 ? true : undefined} aria-label={expanded ? `查看${record.name}` : `展开${items.length}份最近观察`} onClick={() => expanded ? onSelect(record) : toggle()}>
        <CropIcon crop={record.crop} size={40}/><span><strong>{record.name}</strong><small>{record.plot_name || '未关联地块'} · {record.crop}</small></span><Badge status={record.status}/><ArrowUpRight size={16}/>
      </button>)}
    </div>
  </div>
}
