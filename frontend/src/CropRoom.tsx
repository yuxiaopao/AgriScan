import {Check, Palette, ScanLine} from 'lucide-react'
import {useCropTheme} from './CropTheme'
import {getCropTheme} from './cropThemes'
import {Xiaohe} from './Xiaohe'
import type {CSSProperties} from 'react'

export function CropRoom({crops, availableCrops, busy, onSelect}: {
  crops: string[]; availableCrops: string[]; busy: boolean; onSelect: (crop: string) => void
}) {
  const {crop, theme} = useCropTheme()
  const choices = [...new Set([...availableCrops, ...crops])]
  return <section className="crop-room" aria-label="选择作物检测室">
    <div className="crop-room-intro">
      <div className="crop-room-copy"><span className="crop-room-eyebrow"><ScanLine size={13}/> YOUR CROP, YOUR SPACE</span>
        <h2>{crop}<span>检测室</span></h2><p>{theme.tagline}</p>
        <span className="crop-theme-label"><Palette size={13}/>{theme.name}<i/>主题与小禾随作物切换</span>
      </div>
      <div className="crop-room-art"><span className="crop-room-orbit"/><Xiaohe state={busy ? 'scan' : 'idle'} crop={crop}/><span className="crop-room-caption">小禾 · {crop}观察员</span></div>
    </div>
    <div className="crop-room-selector"><div className="crop-room-selector-heading"><strong>今天观察哪一种作物？</strong><span>{busy ? '检测进行中，完成后可切换' : '点击进入对应检测室'}</span></div>
      <div className="crop-room-options" role="group" aria-label="作物检测室">{choices.map(item => {
        const itemTheme = getCropTheme(item)
        const supported = crops.includes(item)
        return <button key={item} type="button" aria-pressed={crop === item} disabled={busy || !supported}
          aria-label={`${item}检测室${supported ? '' : '，当前模型未支持'}`}
          title={supported ? `切换到${item}检测室 · ${itemTheme?.name ?? '田园主题'}` : '当前模型尚未支持该作物，接入对应权重后开放'}
          onClick={() => onSelect(item)} style={{'--option-accent': itemTheme?.accent, '--option-soft': itemTheme?.soft} as CSSProperties}>
          <span className="crop-room-emoji" aria-hidden="true">{itemTheme?.icon ?? '🌱'}</span><span>{item}</span>{crop === item ? <Check size={13}/> : !supported ? <small>待接入</small> : null}
        </button>
      })}</div>
    </div>
    <span className="sr-only" role="status">当前为{crop}检测室，已应用{theme.name}主题。</span>
  </section>
}
