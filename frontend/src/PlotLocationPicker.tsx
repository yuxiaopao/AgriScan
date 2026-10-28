import {useEffect, useRef, useState} from 'react'
import {LocateFixed, MapPin} from 'lucide-react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

interface Props {latitude: string; longitude: string; onChange: (latitude: string, longitude: string) => void}

export default function PlotLocationPicker({latitude, longitude, onChange}: Props) {
  const host = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const marker = useRef<L.Marker | null>(null)
  const change = useRef(onChange)
  change.current = onChange
  const initial = useRef({latitude, longitude})
  const [tileError, setTileError] = useState(false)
  const [locationError, setLocationError] = useState('')
  const [locating, setLocating] = useState(false)

  useEffect(() => {
    if (!host.current) return
    const selected = initial.current.latitude !== '' && initial.current.longitude !== ''
    const center: L.LatLngTuple = selected ? [Number(initial.current.latitude), Number(initial.current.longitude)] : [35.86, 104.2]
    const instance = L.map(host.current, {scrollWheelZoom: false}).setView(center, selected ? 17 : 4)
    map.current = instance
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors',
    }).on('tileerror', () => setTileError(true)).on('tileload', () => setTileError(false)).addTo(instance)
    instance.on('click', (event: L.LeafletMouseEvent) => {
      const point = event.latlng.wrap()
      change.current(point.lat.toFixed(6), point.lng.toFixed(6))
    })
    instance.getContainer().querySelector('.leaflet-control-zoom-in')?.setAttribute('aria-label', '放大地图')
    instance.getContainer().querySelector('.leaflet-control-zoom-out')?.setAttribute('aria-label', '缩小地图')
    const observer = new ResizeObserver(() => instance.invalidateSize({animate: false}))
    observer.observe(host.current)
    return () => {observer.disconnect(); instance.remove(); map.current = null; marker.current = null}
  }, [])

  useEffect(() => {
    const instance = map.current
    if (!instance) return
    const lat = Number(latitude), lng = Number(longitude)
    const valid = latitude !== '' && longitude !== '' && Number.isFinite(lat) && Number.isFinite(lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180
    if (!valid) {marker.current?.remove(); marker.current = null; return}
    if (!marker.current) {
      marker.current = L.marker([lat, lng], {
        draggable: true, title: '地块位置标记（可拖动）',
        icon: L.divIcon({className: 'plot-map-pin', html: '<span></span>', iconSize: [26, 32], iconAnchor: [13, 32]}),
      }).on('dragend', () => {
        const point = marker.current!.getLatLng().wrap()
        change.current(point.lat.toFixed(6), point.lng.toFixed(6))
      }).addTo(instance)
      instance.setView([lat, lng], Math.max(instance.getZoom(), 16), {animate: false})
    } else marker.current.setLatLng([lat, lng])
    if (!instance.getBounds().contains([lat, lng])) instance.panTo([lat, lng], {animate: false})
  }, [latitude, longitude])

  function locate() {
    if (!navigator.geolocation) {setLocationError('当前浏览器不支持定位，请点击地图选点。'); return}
    setLocating(true); setLocationError('')
    navigator.geolocation.getCurrentPosition(position => {
      setLocating(false)
      if (!map.current) return
      const {latitude: lat, longitude: lng} = position.coords
      change.current(lat.toFixed(6), lng.toFixed(6))
      map.current.setView([lat, lng], 17)
    }, () => {setLocating(false); setLocationError('未能获取当前位置，请允许定位或在地图上选点。')}, {enableHighAccuracy: true, timeout: 10000})
  }

  return <div className="plot-location-picker">
    <div className="plot-map-toolbar"><span><MapPin size={14}/>在地图上标记地块</span><button type="button" onClick={locate} disabled={locating}><LocateFixed size={14}/>{locating ? '定位中…' : '使用当前位置'}</button></div>
    <div ref={host} className="plot-location-map" role="region" aria-label="地块位置地图"/>
    {tileError && <p className="plot-map-message" role="status">底图暂时无法加载，仍可填写经纬度后保存。</p>}
    {locationError && <p className="plot-map-message" role="status">{locationError}</p>}
    <div className="plot-coordinate-fields"><label>纬度<input name="latitude" type="number" min="-90" max="90" step="any" required={longitude !== ''} value={latitude} placeholder="例如 26.572145" onChange={event => onChange(event.target.value, longitude)}/></label><label>经度<input name="longitude" type="number" min="-180" max="180" step="any" required={latitude !== ''} value={longitude} placeholder="例如 106.713841" onChange={event => onChange(latitude, event.target.value)}/></label></div>
    <div className="plot-coordinate-note"><span>WGS84 坐标 · 点击地图或拖动标记调整</span>{(latitude || longitude) && <button type="button" onClick={() => onChange('', '')}>清除标记</button>}</div>
  </div>
}
