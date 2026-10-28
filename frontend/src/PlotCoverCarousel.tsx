import {useEffect, useRef, useState} from 'react'
import {ChevronLeft, ChevronRight, MapPin, Sprout} from 'lucide-react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import {SecureImage} from './components'
import {validCoordinates} from './plotCoordinates'
import type {Plot} from './types'

function PlotCardMap({latitude, longitude}: {latitude: number; longitude: number}) {
  const host = useRef<HTMLDivElement>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    if (!host.current) return
    setFailed(false)
    const map = L.map(host.current, {zoomControl: false, dragging: false, scrollWheelZoom: false,
      touchZoom: false, doubleClickZoom: false, boxZoom: false, keyboard: false}).setView([latitude, longitude], 17)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors',
    }).on('tileerror', () => setFailed(true)).on('tileload', () => setFailed(false)).addTo(map)
    L.marker([latitude, longitude], {keyboard: false, title: '地块精确位置',
      icon: L.divIcon({className: 'plot-map-pin', html: '<span></span>', iconSize: [26, 32], iconAnchor: [13, 32]}),
    }).addTo(map)
    const observer = new ResizeObserver(() => map.invalidateSize({animate: false}))
    observer.observe(host.current)
    return () => {observer.disconnect(); map.remove()}
  }, [latitude, longitude])
  return <><div ref={host} className="plot-card-map" role="img" aria-label={`地块地图：纬度 ${latitude.toFixed(6)}，经度 ${longitude.toFixed(6)}`}/><span className="plot-card-coordinates">纬 {latitude.toFixed(6)} · 经 {longitude.toFixed(6)}</span>{failed && <span className="plot-card-map-error">底图暂不可用，坐标已标记</span>}</>
}

export default function PlotCoverCarousel({plot, index}: {plot: Plot; index: number}) {
  const track = useRef<HTMLDivElement>(null)
  const [page, setPage] = useState(0)
  const currentPage = useRef(0)
  const coordinates = validCoordinates(plot.latitude, plot.longitude)
  useEffect(() => {
    const node = track.current!
    const observer = new ResizeObserver(() => node.scrollTo({left: currentPage.current * node.clientWidth, behavior: 'instant'}))
    observer.observe(node)
    return () => observer.disconnect()
  }, [])
  function navigate(next: number) {
    const node = track.current!
    node.scrollTo({left: Math.max(0, Math.min(1, next)) * node.clientWidth,
      behavior: document.documentElement.classList.contains('reduce-motion') || window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'})
  }
  return <div className="plot-cover-carousel" role="region" aria-label={`${plot.name}封面与地图`}>
    <div className="plot-cover-track" ref={track} onScroll={event => {
      const node = event.currentTarget
      if (!node.clientWidth) return
      const next = Math.max(0, Math.min(1, Math.round(node.scrollLeft / node.clientWidth)))
      currentPage.current = next; setPage(next)
    }}>
      <div className="plot-card-slide" role="group" aria-label="第 1 页：地块封面">
        <div className={`plot-landscape landscape-${index % 4} ${plot.cover_url ? 'has-cover' : ''}`}>
          {plot.cover_url ? <SecureImage url={plot.cover_url} alt={`${plot.name}封面`} className="plot-cover-image"/> : <><div className="landscape-sun"/><div className="field-lines"/></>}
          <span className="plot-crop-label"><Sprout size={13}/>{plot.crop}种植区</span><span className="plot-area">{plot.area}<small>亩</small></span>
        </div>
      </div>
      <div className="plot-card-slide" role="group" aria-label="第 2 页：地块地图">
        {page === 1 && (coordinates ? <PlotCardMap latitude={coordinates[0]} longitude={coordinates[1]}/> : <div className="plot-map-empty"><MapPin size={22}/><span>尚未标记位置</span><small>编辑地块后可添加地图坐标</small></div>)}
      </div>
    </div>
    <button type="button" className="plot-cover-arrow previous" aria-label="上一页：封面" disabled={page === 0} onClick={() => navigate(0)}><ChevronLeft size={17}/></button>
    <button type="button" className="plot-cover-arrow next" aria-label="下一页：地图" disabled={page === 1} onClick={() => navigate(1)}><ChevronRight size={17}/></button>
    <div className="plot-cover-pages"><button type="button" aria-label="显示地块封面" aria-pressed={page === 0} onClick={() => navigate(0)}>封面</button><button type="button" aria-label="显示地块地图" aria-pressed={page === 1} onClick={() => navigate(1)}>地图</button></div>
  </div>
}
