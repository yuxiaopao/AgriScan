import type {Plot} from './types'

export interface PlotDraft {name:string;crop:string;area:string;location:string;manager:string;latitude:string;longitude:string}
export interface PlotBody {name:string;crop:string;area:number;location:string;manager:string;latitude:number|null;longitude:number|null}
export function plotDraft(plot:Plot|null,crop:string,manager:string):PlotDraft {
  return {name:plot?.name??'',crop:plot?.crop??crop,area:plot?String(plot.area):'',location:plot?.location??'',manager:plot?.manager??manager,latitude:plot?.latitude==null?'':String(plot.latitude),longitude:plot?.longitude==null?'':String(plot.longitude)}
}
export function plotBody(draft:PlotDraft,crops:string[]):PlotBody {
  const name=draft.name.trim(),location=draft.location.trim(),manager=draft.manager.trim(),area=Number(draft.area.trim())
  if(!name||name.length>100)throw new Error('请填写地块名称，最多 100 个字。')
  if(!crops.includes(draft.crop))throw new Error('请选择服务支持的作物。')
  if(!Number.isFinite(area)||area<=0||area>1000000)throw new Error('种植面积需大于 0，且不超过 100 万亩。')
  if(location.length>200)throw new Error('地块位置最多填写 200 个字。')
  if(manager.length>80)throw new Error('负责人最多填写 80 个字。')
  const latitude=draft.latitude.trim(),longitude=draft.longitude.trim()
  if(Boolean(latitude)!==Boolean(longitude))throw new Error('请同时填写经纬度，或同时留空。')
  if(latitude&&(!Number.isFinite(Number(latitude))||Math.abs(Number(latitude))>90))throw new Error('纬度需在负 90 至 90 之间。')
  if(longitude&&(!Number.isFinite(Number(longitude))||Math.abs(Number(longitude))>180))throw new Error('经度需在负 180 至 180 之间。')
  return {name,crop:draft.crop,area,location,manager,latitude:latitude?Number(latitude):null,longitude:longitude?Number(longitude):null}
}
