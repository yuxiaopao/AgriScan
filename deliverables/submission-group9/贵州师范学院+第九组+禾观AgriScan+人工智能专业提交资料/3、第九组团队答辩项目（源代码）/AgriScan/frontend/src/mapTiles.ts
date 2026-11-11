import L from 'leaflet'

export type MapTileState='loading'|'ready'|'slow'|'partial'|'unavailable'
export interface MapTileStatus {state:MapTileState;loaded:number;failed:number;pending:number}
export const initialMapTileStatus:MapTileStatus={state:'loading',loaded:0,failed:0,pending:0}
const tileUrl=import.meta.env.VITE_MAP_TILE_URL||'https://tile.openstreetmap.org/{z}/{x}/{y}.png'

/** Track the visible image elements: one successful tile must not hide another failed tile. */
export function attachMapTiles(map:L.Map,onStatus:(status:MapTileStatus)=>void,timeoutMs=12000){
  const tiles=new Map<HTMLElement,'loading'|'loaded'|'failed'>()
  let disposed=false,slow=false,timer:ReturnType<typeof setTimeout>|undefined
  function stopTimer(){if(timer!==undefined){clearTimeout(timer);timer=undefined}}
  function publish(){
    if(disposed)return
    let loaded=0,failed=0,pending=0
    for(const state of tiles.values()){if(state==='loaded')loaded++;else if(state==='failed')failed++;else pending++}
    if(pending||!tiles.size){
      if(timer===undefined&&!slow)timer=setTimeout(()=>{timer=undefined;slow=true;publish()},timeoutMs)
    }else{stopTimer();slow=false}
    const state:MapTileState=pending||!tiles.size?(slow?'slow':'loading'):failed?(loaded?'partial':'unavailable'):'ready'
    onStatus({state,loaded,failed,pending})
  }
  function start(event:L.TileEvent){if(disposed)return;tiles.set(event.tile,'loading');publish()}
  function loaded(event:L.TileEvent){if(disposed||!tiles.has(event.tile))return;tiles.set(event.tile,'loaded');publish()}
  function failed(event:L.TileErrorEvent){if(disposed||!tiles.has(event.tile))return;tiles.set(event.tile,'failed');publish()}
  function unloaded(event:L.TileEvent){if(disposed)return;tiles.delete(event.tile);publish()}
  const layer=L.tileLayer(tileUrl,{
    maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors',
  }).on('tileloadstart',start).on('tileload',loaded).on('tileerror',failed).on('tileunload',unloaded)
  function retry(){if(disposed)return;stopTimer();slow=false;tiles.clear();publish();layer.redraw()}
  function dispose(){if(disposed)return;disposed=true;stopTimer();tiles.clear();layer.off('tileloadstart',start).off('tileload',loaded).off('tileerror',failed).off('tileunload',unloaded);map.off('unload',dispose)}
  map.on('unload',dispose)
  publish();layer.addTo(map)
  return {retry,dispose}
}
