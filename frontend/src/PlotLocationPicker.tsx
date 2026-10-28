import {useEffect, useRef, useState} from 'react'
import {LocateFixed, MapPin} from 'lucide-react'
import L from 'leaflet'
import {validCoordinates} from './plotCoordinates'
import 'leaflet/dist/leaflet.css'

interface Props {latitude: string; longitude: string; disabled?: boolean; onChange: (latitude: string, longitude: string) => void}

export default function PlotLocationPicker({latitude, longitude, disabled = false, onChange}: Props) {
  const host = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const marker = useRef<L.Marker | null>(null)
  const change = useRef(onChange)
  change.current = onChange
  const disabledRef = useRef(disabled)
  disabledRef.current = disabled
  const locationRequest = useRef(0)
  const initial = useRef({latitude, longitude})
  const [tileError, setTileError] = useState(false)
  const [locationError, setLocationError] = useState('')
  const [locating, setLocating] = useState(false)

  function manualChange(lat: string, lng: string) {
    if (disabledRef.current) return
    locationRequest.current++
    setLocating(false)
    change.current(lat, lng)
  }

  useEffect(() => {
    if (!host.current) return
    const selected = validCoordinates(initial.current.latitude, initial.current.longitude)
    const instance = L.map(host.current, {scrollWheelZoom: false}).setView(selected ?? [35.86, 104.2], selected ? 17 : 4)
    map.current = instance
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors',
    }).on('tileerror', () => setTileError(true)).on('tileload', () => setTileError(false)).addTo(instance)
    instance.on('click', (event: L.LeafletMouseEvent) => {
      if (disabledRef.current) return
      const point = event.latlng.wrap()
      manualChange(point.lat.toFixed(6), point.lng.toFixed(6))
    })
    instance.getContainer().querySelector('.leaflet-control-zoom-in')?.setAttribute('aria-label', '放大地图')
    instance.getContainer().querySelector('.leaflet-control-zoom-out')?.setAttribute('aria-label', '缩小地图')
    const observer = new ResizeObserver(() => instance.invalidateSize({animate: false}))
    observer.observe(host.current)
    return () => {locationRequest.current++; observer.disconnect(); instance.remove(); map.current = null; marker.current = null}
  }, [])

  useEffect(() => {
    const instance = map.current
    if (!instance) return
    const selected = validCoordinates(latitude, longitude)
    if (!selected) {marker.current?.remove(); marker.current = null; return}
    const [lat, lng] = selected
    if (!marker.current) {
      marker.current = L.marker([lat, lng], {
        draggable: !disabledRef.current, title: '地块位置标记（可拖动）',
        icon: L.divIcon({className: 'plot-map-pin', html: '<span></span>', iconSize: [26, 32], iconAnchor: [13, 32]}),
      }).on('dragend', () => {
        if (disabledRef.current || !marker.current) return
        const point = marker.current!.getLatLng().wrap()
        manualChange(point.lat.toFixed(6), point.lng.toFixed(6))
      }).addTo(instance)
      instance.setView([lat, lng], Math.max(instance.getZoom(), 16), {animate: false})
    } else marker.current.setLatLng([lat, lng])
    if (!instance.getBounds().contains([lat, lng])) instance.panTo([lat, lng], {animate: false})
  }, [latitude, longitude])

  useEffect(() => {
    const instance = map.current
    if (!instance) return
    if (disabled) {locationRequest.current++; setLocating(false)}
    for (const handler of [instance.dragging, instance.doubleClickZoom, instance.boxZoom, instance.keyboard, instance.touchZoom, marker.current?.dragging]) {
      if (disabled) handler?.disable()
      else handler?.enable()
    }
    instance.getContainer().setAttribute('aria-disabled', String(disabled))
    instance.getContainer().querySelectorAll('.leaflet-control-zoom a').forEach(control => control.setAttribute('tabindex', disabled ? '-1' : '0'))
  }, [disabled, latitude, longitude])

  function locate() {
    if (disabledRef.current || locating) return
    if (!navigator.geolocation) {setLocationError('当前浏览器不支持定位，请点击地图选点。'); return}
    const request = ++locationRequest.current
    const instance = map.current
    setLocating(true); setLocationError('')
    navigator.geolocation.getCurrentPosition(position => {
      if (request !== locationRequest.current || disabledRef.current || !instance || map.current !== instance) return
      setLocating(false)
      const {latitude: lat, longitude: lng} = position.coords
      if (!validCoordinates(lat, lng)) {setLocationError('定位坐标无效，请在地图上选点。'); return}
      change.current(lat.toFixed(6), lng.toFixed(6))
      instance.setView([lat, lng], 17)
    }, () => {
      if (request !== locationRequest.current || disabledRef.current || !instance || map.current !== instance) return
      setLocating(false); setLocationError('未能获取当前位置，请允许定位或在地图上选点。')
    }, {enableHighAccuracy: true, timeout: 10000})
  }

  return <div className="plot-location-picker">
    <div className="plot-map-toolbar"><span><MapPin size={14}/>在地图上标记地块</span><button type="button" onClick={locate} disabled={disabled || locating}><LocateFixed size={14}/>{locating ? '定位中…' : '使用当前位置'}</button></div>
    <div ref={host} className="plot-location-map" role="region" aria-label="地块位置地图" aria-disabled={disabled}/>
    {tileError && <p className="plot-map-message" role="status">底图暂时无法加载，仍可填写经纬度后保存。</p>}
    {locationError && <p className="plot-map-message" role="status">{locationError}</p>}
    <div className="plot-coordinate-fields"><label>纬度<input name="latitude" type="number" min="-90" max="90" step="any" disabled={disabled} required={longitude !== ''} value={latitude} placeholder="例如 26.572145" onChange={event => manualChange(event.target.value, longitude)}/></label><label>经度<input name="longitude" type="number" min="-180" max="180" step="any" disabled={disabled} required={latitude !== ''} value={longitude} placeholder="例如 106.713841" onChange={event => manualChange(latitude, event.target.value)}/></label></div>
    <div className="plot-coordinate-note"><span>WGS84 坐标 · 点击地图或拖动标记调整</span>{(latitude || longitude) && <button type="button" disabled={disabled} onClick={() => manualChange('', '')}>清除标记</button>}</div>
  </div>
}
