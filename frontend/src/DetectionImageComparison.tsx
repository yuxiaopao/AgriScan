import {useEffect, useRef, useState, type ReactNode} from 'react'
import {CircleAlert, FileImage, LoaderCircle, ScanLine} from 'lucide-react'
import {apiResourceUrl,getToken} from './api'
import {confidenceText} from './PredictionScores'
import {Badge} from './components'
import type {Detection} from './types'
import './detection-image-comparison.css'

/** Real model output only. bbox is normalized [left, top, right, bottom], 0–1. */
export interface ModelDetectionBox {label:string;confidence:number;bbox:[number,number,number,number]}

export function validModelBox(box:ModelDetectionBox) {
  return Boolean(box)&&typeof box.label==='string'&&box.label.trim().length>0&&Number.isFinite(box.confidence)&&box.confidence>=0&&box.confidence<=1
    &&Array.isArray(box.bbox)&&box.bbox.length===4&&box.bbox.every(value=>Number.isFinite(value)&&value>=0&&value<=1)
    &&box.bbox[2]>box.bbox[0]&&box.bbox[3]>box.bbox[1]
}

export function containedImageRect(imageWidth:number,imageHeight:number,viewportWidth:number,viewportHeight:number) {
  if(![imageWidth,imageHeight,viewportWidth,viewportHeight].every(value=>Number.isFinite(value)&&value>0))return null
  const scale=Math.min(viewportWidth/imageWidth,viewportHeight/imageHeight)
  const width=imageWidth*scale,height=imageHeight*scale
  return {left:(viewportWidth-width)/2,top:(viewportHeight-height)/2,width,height}
}

function ResultImage({record,originalUrl,detections}:{record:Detection;originalUrl:string;detections:ModelDetectionBox[]}) {
  const host=useRef<HTMLDivElement>(null)
  const [remote,setRemote]=useState({owner:'',url:'',failed:false})
  const [natural,setNatural]=useState({source:'',width:0,height:0})
  const [viewport,setViewport]=useState({width:0,height:0})
  const [decodeError,setDecodeError]=useState('')
  const [reload,setReload]=useState(0)
  const savedUrl=record.image_url??''
  const token=getToken()
  const source=savedUrl?(remote.owner===savedUrl?remote.url:''):originalUrl
  const failed=(savedUrl&&remote.owner===savedUrl&&remote.failed)||(source&&decodeError===source)
  useEffect(()=>{
    if(!savedUrl)return
    let alive=true;let objectUrl='';const controller=new AbortController()
    setRemote({owner:savedUrl,url:'',failed:false})
    const url=new URL(apiResourceUrl(savedUrl),window.location.origin)
    const headers=token&&url.origin===window.location.origin?{Authorization:`Bearer ${token}`}:undefined
    fetch(url,{headers,signal:AbortSignal.any([controller.signal,AbortSignal.timeout(20000)])}).then(response=>{if(!response.ok)throw new Error();return response.blob()})
      .then(blob=>{objectUrl=URL.createObjectURL(blob);if(alive)setRemote({owner:savedUrl,url:objectUrl,failed:false});else URL.revokeObjectURL(objectUrl)})
      .catch(()=>{if(alive)setRemote({owner:savedUrl,url:'',failed:true})})
    return()=>{alive=false;controller.abort();if(objectUrl)URL.revokeObjectURL(objectUrl)}
  },[savedUrl,token,reload])
  useEffect(()=>{
    const element=host.current;if(!element)return
    const measure=()=>setViewport({width:element.clientWidth,height:element.clientHeight})
    measure();const observer=new ResizeObserver(measure);observer.observe(element)
    return()=>observer.disconnect()
  },[])
  const loaded=source&&natural.source===source&&natural.width>0&&natural.height>0
  const rect=loaded?containedImageRect(natural.width,natural.height,viewport.width,viewport.height):null
  const imageWidth=rect?.width??0,imageHeight=rect?.height??0
  const boxes=detections.filter(validModelBox)
  return <div className="comparison-result-stage" ref={host}>
    {source&&<img src={source} alt={`${record.crop}的服务端检测照片`} draggable={false} onLoad={event=>{const image=event.currentTarget;setDecodeError('');setNatural({source,width:image.naturalWidth,height:image.naturalHeight})}} onError={()=>{setDecodeError(source);setNatural({source,width:0,height:0})}}/>}
    {!loaded&&<div className="comparison-image-message" role="status">{failed?<><CircleAlert size={24}/><span>结果照片暂时无法加载</span><small>识别报告仍保留，未在其他图片上叠加位置框。</small>{savedUrl&&<button type="button" className="text-button" onClick={()=>setReload(value=>value+1)}>重新读取照片</button>}</>:<><LoaderCircle size={25} className="spin"/><span>正在读取检测照片…</span></>}</div>}
    {loaded&&rect&&boxes.length>0&&imageWidth>0&&imageHeight>0&&<div className="comparison-annotation-plane" aria-hidden="true" style={{left:rect.left,top:rect.top,width:imageWidth,height:imageHeight}}>
      {boxes.map((box,index)=>{
        const [left,top,right,bottom]=box.bbox
        const labelWidth=Math.min(imageWidth,Math.max(96,Math.min(230,[...box.label].length*13+86)))
        return <div key={`${index}-${box.label}`}>
          <span className="comparison-model-box" style={{left:`${left*100}%`,top:`${top*100}%`,width:`${(right-left)*100}%`,height:`${(bottom-top)*100}%`}}/>
          <span className="comparison-box-label" title={`${box.label} ${confidenceText(box.confidence)}`} style={{left:Math.max(0,Math.min(left*imageWidth,imageWidth-labelWidth)),top:Math.max(0,top*imageHeight-25),maxWidth:labelWidth}}>{box.label}<strong>{confidenceText(box.confidence)}</strong></span>
        </div>
      })}
    </div>}
  </div>
}

/** Future detection adapters can pass actual boxes; classification never derives them. */
export default function DetectionImageComparison({original,originalUrl,record,busy,modelReady,detections=[]}:{
  original:ReactNode;originalUrl:string;record:Detection|null;busy:boolean;modelReady:boolean;detections?:ModelDetectionBox[]
}) {
  const boxes=detections.filter(validModelBox)
  const pending=record?.status==='awaiting_model'
  return <section className="detection-image-comparison" aria-label="上传原图与识别结果对照">
    <div className="comparison-column comparison-original"><div className="comparison-column-heading"><h3><FileImage size={16}/>原始上传图</h3><span>完整画面</span></div>{original}<p className="comparison-column-note">保留原始构图，完整显示叶片与采样细节。</p></div>
    <div className="comparison-column comparison-processed"><div className="comparison-column-heading"><h3><ScanLine size={16}/>{boxes.length?'模型定位结果':'识别结果图'}</h3><span>{busy?'分析中':record?boxes.length?'真实模型标注':pending?'等待模型':'分类标签':'等待识别'}</span></div>
      {record?<ResultImage key={record.id} record={record} originalUrl={originalUrl} detections={boxes}/>:<div className="comparison-result-stage comparison-pending" role="status">{busy?<><LoaderCircle size={32} className="spin"/><h4>正在分析这张叶片照片</h4><p>作物与结果返回后，会在这里展示。</p></>:<><ScanLine size={36} strokeWidth={1.2}/><h4>识别后，在这里查看结果</h4><p>{modelReady?'上传照片并点击“识别并保存”，自动识别作物与叶片状况。':'上传照片并保存样本，正式模型接入后才能进行识别。'}</p></>}</div>}
      {record&&<div className="comparison-result-summary" aria-live="polite"><div><strong>{record.crop}</strong><Badge status={record.status}/></div><p>{record.result||'样本已保存，等待模型接入'}</p><dl><dt>{boxes.length||record.prediction_model?.task==='detect'?'检测目标置信度':'分类置信度'}</dt><dd>{confidenceText(record.confidence)}</dd></dl></div>}
      {record&&boxes.length>0?<div className="comparison-box-legend"><strong>模型实际输出 {boxes.length} 个检测目标框</strong>{boxes.map((box,index)=><span key={`${index}-${box.label}`}>{index+1}. {box.label}<small>{confidenceText(box.confidence)}</small></span>)}</div>:record&&!pending?<p className="comparison-column-note comparison-location-note"><CircleAlert size={14}/>{record.prediction_model?.task&&record.prediction_model.task!=='classify'?'模型本次未返回检测目标框。':'分类模型未输出位置框。'}右图显示原始照片与识别标签，不表示病斑边界已被定位。</p>:<p className="comparison-column-note">{pending?'当前仅保存样本，不生成病害判断或位置框。':'只展示模型真实输出的位置数据，不生成示意目标框。'}</p>}
      {record&&detections.length!==boxes.length&&<p className="comparison-column-note">部分位置数据无效，已忽略。</p>}
    </div>
  </section>
}
