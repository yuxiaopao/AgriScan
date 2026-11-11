import {LoaderCircle,RotateCcw} from 'lucide-react'
import type {MapTileStatus} from './mapTiles'

const titles={loading:'底图加载中…',ready:'底图已加载',slow:'底图加载较慢',partial:'部分底图未加载',unavailable:'底图暂时无法加载'}
export default function MapTileFeedback({status,onRetry,disabled=false,compact=false}:{status:MapTileStatus;onRetry:()=>void;disabled?:boolean;compact?:boolean}){
  if(status.state==='ready')return compact?null:<p className="plot-map-ready" role="status">底图已加载，可点击选点或拖动标记。</p>
  return <div className={`plot-map-feedback ${compact?'compact':''}`} role="status" aria-live="polite" aria-atomic="true">
    <div><strong>{status.state==='loading'&&<LoaderCircle size={13} className="spin"/>}{titles[status.state]}</strong>{!compact&&<span>{status.state==='loading'?'请等底图清晰后再选点，也可直接填写经纬度。':'可重新加载底图；经纬度仍可手填和保存。'}</span>}</div>
    {status.state!=='loading'&&<button type="button" disabled={disabled} onClick={onRetry}><RotateCcw size={13}/>重新加载底图</button>}
  </div>
}
