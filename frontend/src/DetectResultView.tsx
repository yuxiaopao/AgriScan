import {useState,type RefObject} from 'react'
import {ArrowRight,CheckCircle2,FileImage,MessageCircle,Upload} from 'lucide-react'
import {Badge,Modal,SecureImage} from './components'
import DetectionImageComparison from './DetectionImageComparison'
import {confidenceText,PredictionScores} from './PredictionScores'
import type {Detection} from './types'
import './detect-result.css'

interface Props {
  record:Detection;originalUrl:string;canChoose:boolean;canAsk:boolean
  headingRef:RefObject<HTMLHeadingElement|null>;comparisonRef:RefObject<HTMLElement|null>;metadataRef:RefObject<HTMLDetailsElement|null>
  onChooseNext:()=>void;onViewAdvice:()=>void
}
export default function DetectResultView({record,originalUrl,canChoose,canAsk,headingRef,comparisonRef,metadataRef,onChooseNext,onViewAdvice}:Props){
  const [originalOpen,setOriginalOpen]=useState(false)
  const savedOnly=record.status==='awaiting_model'
  const targetDetection=record.prediction_model?.task==='detect'
  return <div className="detect-result-view">
    <section className="panel detect-complete-heading">
      <div><span className="detect-complete-state">{savedOnly?<FileImage size={18}/>:<CheckCircle2 size={18}/>} {savedOnly?'采集信息已保存':'本次检测完成'}</span><h2 ref={headingRef} tabIndex={-1}>{savedOnly?'样本已保存':`${record.crop}检测完成`}</h2><p>{savedOnly?'当前未生成模型判断，原图与采集信息已存入记录。':record.prediction_model?.verification?'原图、识别结果与分类复核状态已保存，可以开始查看结果。':'原图与识别结果已保存，可以开始查看结果。'}</p></div>
      <div className="detect-complete-actions"><button type="button" className="button primary" disabled={!canChoose} onClick={onChooseNext}><Upload size={16}/>{savedOnly?'再采集一张':'再检测一张'}</button><button type="button" className="button outline" disabled={!canAsk} onClick={onViewAdvice}><MessageCircle size={16}/>查看小禾建议</button><a className="text-button" href="#records">查看检测记录<ArrowRight size={15}/></a></div>
    </section>
    <div className="detect-complete-grid">
      <section className="panel detect-complete-comparison" ref={comparisonRef} aria-label="本次检测原图与识别图">
        <DetectionImageComparison originalUrl={originalUrl} record={record} busy={false} modelReady={!savedOnly} detections={record.boxes}
          original={<div className="completed-original">{originalUrl?<img src={originalUrl} alt="本次检测的原始上传照片"/>:record.image_url?<SecureImage url={record.image_url} alt="本次检测的原始上传照片"/>:<span>原图暂不可用</span>}<button type="button" className="button outline small" disabled={!record.image_url&&!originalUrl} onClick={()=>setOriginalOpen(true)}><FileImage size={15}/>查看原图</button></div>}/>
      </section>
      <aside className="panel detect-complete-summary" aria-label={savedOnly?'采集样本信息':'本次检测结论与双模型复核'}><h3>{savedOnly?'采集样本':'检测结果'}</h3><Badge status={record.status}/><dl className="completed-primary-result"><div><dt>{savedOnly?'采集作物':'检测识别作物'}</dt><dd>{record.crop}</dd></div><div><dt>病害 / 健康状态</dt><dd>{record.result||'等待模型接入'}</dd></div>{!savedOnly&&<div><dt>{targetDetection?'目标检测原始分数':'分类原始分数'}</dt><dd>{confidenceText(record.confidence)}</dd></div>}</dl><PredictionScores record={record}/><p className="completed-advice-note">{canAsk?'小禾图片解读在后台处理。点击“查看小禾建议”查看进度或建议，不影响查看本次结果。':'小禾建议暂不可用，本次保存的图片与结果仍可查看。'}</p></aside>
    </div>
    <details ref={metadataRef} className="panel detect-complete-metadata"><summary>样本与采集信息 · 已保存</summary><dl><div><dt>样本编号</dt><dd>{record.id}</dd></div><div><dt>照片名称</dt><dd>{record.name}</dd></div><div><dt>所属地块</dt><dd>{record.plot_name||'未关联地块'}</dd></div><div><dt>采集时间</dt><dd>{new Date(record.created_at).toLocaleString('zh-CN')}</dd></div><div><dt>采样备注</dt><dd>{record.note||'未填写'}</dd></div></dl></details>
    {originalOpen&&<Modal title="原始上传照片" wide onClose={()=>setOriginalOpen(false)}><div className="completed-original-modal">{record.image_url?<SecureImage url={record.image_url} alt="服务端保存的原始检测照片"/>:<img src={originalUrl} alt="原始上传照片"/>}<p>{record.name}</p></div></Modal>}
  </div>
}
