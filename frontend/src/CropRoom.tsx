import {Check, Palette, ScanLine} from 'lucide-react'
import {useCropTheme} from './CropTheme'
import {getCropTheme} from './cropThemes'
import {revealCropTheme} from './motion'
import {Xiaohe} from './Xiaohe'
import type {CSSProperties} from 'react'

export function CropRoom({crops, availableCrops, busy, automatic, onSelect}: {
  crops: string[]; availableCrops: string[]; busy: boolean; automatic: boolean; onSelect: (crop: string) => void
}) {
  const {crop, theme} = useCropTheme()
  const choices = [...new Set([...availableCrops, ...crops])]
  return <section className="crop-room" aria-label={automatic ? '浏览作物检测室主题' : '选择作物检测室'}>
    <div className="crop-room-intro">
      <div className="crop-room-copy"><span className="crop-room-eyebrow"><ScanLine size={13}/> YOUR CROP, YOUR SPACE</span>
        <h2>{crop}<span>检测室</span></h2><p>{theme.tagline}</p>
        <span className="crop-theme-label"><Palette size={13}/>{theme.name}<i/>主题与小禾随作物切换</span>
      </div>
      <div className="crop-room-art"><span className="crop-room-orbit"/><Xiaohe state={busy ? 'scan' : 'idle'} crop={crop}/><span className="crop-room-caption">小禾 · {crop}观察员</span></div>
    </div>
    <div className="crop-room-selector"><div className="crop-room-selector-heading"><strong>{automatic ? '浏览作物主题' : '今天采集哪一种作物？'}</strong><span>{busy ? '检测进行中，完成后可切换' : automatic ? '无需预选作物' : '点击进入对应检测室'}</span></div>
      <p className="crop-room-help">{automatic ? `上传叶片照片后，点击识别即可自动判断作物并进入相应检测室。下方按钮仅浏览主题；当前模型覆盖 ${crops.length} 种作物。` : '当前未启用识别模型，请选择作物采集样本，保存后等待模型接入。'}</p>
      <div className="crop-room-options" role="group" aria-label={automatic ? '作物主题' : '作物检测室'}>{choices.map(item => {
        const itemTheme = getCropTheme(item)
        const supported = crops.includes(item)
        return <button key={item} type="button" aria-pressed={crop === item} disabled={busy || (!automatic && !supported)}
          aria-label={`${item}${automatic ? '主题' : '检测室'}${supported ? '' : automatic ? '，仅主题，模型未支持' : '，当前模型未支持'}`}
          title={automatic ? `浏览${item}主题 · ${itemTheme?.name ?? '田园主题'}${supported ? '；不影响自动识别' : '；当前模型尚未覆盖该作物'}` : supported ? `切换到${item}检测室 · ${itemTheme?.name ?? '田园主题'}` : '当前模型尚未支持该作物，接入对应权重后开放'}
          onClick={event => {if (crop !== item) {const box = event.currentTarget.getBoundingClientRect(); revealCropTheme(itemTheme?.soft || '#f1f5ed', {x: box.left + box.width / 2, y: box.top + box.height / 2}); onSelect(item)}}} style={{'--option-accent': itemTheme?.accent, '--option-soft': itemTheme?.soft} as CSSProperties}>
          <span className="crop-room-emoji" aria-hidden="true">{itemTheme?.icon ?? '🌱'}</span><span>{item}</span>{crop === item && <Check size={13}/>} {!supported && <small>{automatic ? '仅主题' : '待接入'}</small>}
        </button>
      })}</div>
    </div>
    <span className="sr-only" role="status">当前为{crop}检测室，已应用{theme.name}主题。{automatic ? '主题选择不限制照片中的作物识别。' : ''}</span>
  </section>
}
