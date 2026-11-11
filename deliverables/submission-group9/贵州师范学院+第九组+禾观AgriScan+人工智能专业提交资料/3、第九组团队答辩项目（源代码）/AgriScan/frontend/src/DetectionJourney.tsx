import {Check, FileImage, NotebookPen, ScanLine} from 'lucide-react'

export type DetectionPhase='choose'|'details'|'detecting'|'complete'|'saved'|'failed'|'cancelled'|'result_loading'
export default function DetectionJourney({phase,modelReady,canUpload,onUpload,onDetails,onResult}: {
  phase:DetectionPhase;modelReady:boolean;canUpload:boolean;onUpload:()=>void;onDetails:()=>void;onResult:()=>void
}) {
  const complete=phase==='complete'||phase==='saved',busy=phase==='detecting'
  const step=complete||busy||['failed','cancelled','result_loading'].includes(phase)?2:phase==='details'?1:0
  const items = [
    {title:complete?'照片已记录':'选择照片',text:complete?'查看本次原图':phase==='choose'?'拍清叶片与纹理':'图片已就绪',icon:FileImage,action:onUpload,disabled:busy||(!complete&&!canUpload)},
    {title:complete?'信息已保存':'补充记录',text:complete?'查看采集信息':'地块与备注均可选填',icon:NotebookPen,action:onDetails,disabled:busy},
    {title:phase==='complete'?'检测完成':phase==='saved'?'样本已保存':phase==='failed'?'检测未完成':phase==='cancelled'?'任务已取消':phase==='result_loading'?'读取结果':busy?(modelReady?'检测中':'保存中'):(modelReady?'识别与保存':'保存采集样本'),text:complete?'查看本次结果':['failed','cancelled'].includes(phase)?'可重新选择照片':phase==='result_loading'?'正在读取已保存的结果':busy?(modelReady?'正在分析，请稍候':'正在保存，请稍候'):'保留每次观察',icon:ScanLine,action:onResult,disabled:!complete},
  ]
  return <nav className="detection-journey" aria-label="本次检测进度">
    <span className="journey-line" aria-hidden="true"><i style={{transform: `scaleX(${step / 2})`}}/></span>
    {items.map((item, index) => <button key={item.title} type="button" className={`journey-node ${step > index || complete ? 'complete' : ''} ${step === index ? 'current' : ''}`} disabled={item.disabled} aria-current={step === index ? 'step' : undefined} onClick={item.action}><span className="journey-icon">{step > index || complete ? <Check size={18}/> : <item.icon size={18}/>}</span><span><strong>{item.title}</strong><small>{item.text}</small></span></button>)}
  </nav>
}
