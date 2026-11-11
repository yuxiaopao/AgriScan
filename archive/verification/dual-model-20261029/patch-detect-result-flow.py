from pathlib import Path

p=Path('frontend/src/Pages.tsx');s=p.read_text(encoding='utf-8')
def once(old,new):
    global s
    if s.count(old)!=1:raise RuntimeError('Expected unique detection edit: '+old[:70])
    s=s.replace(old,new,1)
once("import DetectionJourney from './DetectionJourney'","import DetectionJourney from './DetectionJourney'\nimport DetectResultView from './DetectResultView'")
once("import {confidenceText, PredictionScores} from './PredictionScores'\n",'')
once("export function DetectPage({plots, model, requireAuth, onChange, toast, onDetected}: {plots: Plot[]; model: ModelInfo; onDetected: (record: Detection) => void} & ProtectedProps) {", "export function DetectPage({plots, model, requireAuth, onChange, toast, onDetected, onViewAdvice}: {plots: Plot[]; model: ModelInfo; onDetected: (record: Detection) => void; onViewAdvice?: (record: Detection) => void} & ProtectedProps) {")
once("  const [result, setResult] = useState<Detection | null>(null)","  const [result, setResult] = useState<Detection | null>(null)\n  const [submitError,setSubmitError]=useState('')\n  const resultHeading=useRef<HTMLHeadingElement>(null)\n  const resultMetadata=useRef<HTMLDetailsElement>(null)\n  const completedUpload=useRef(false)\n  const acceptedToken=useRef<string|null>(null)")
once("  const targetDetection=result?.prediction_model?.task==='detect'\n",'')
once("    if (!modelReady && crops.length && !crops.includes(crop)) {setCrop(crops[0]); setPlotId(''); setResult(null)}", "    if (!result && !modelReady && crops.length && !crops.includes(crop)) {setCrop(crops[0]); setPlotId('')}")
once("  }, [crops, crop, modelReady, setCrop])", "  }, [crops, crop, modelReady, setCrop, result])")
once("  const chooseFile = (next?: File) => {", """  useEffect(()=>{
    if(!result||!acceptedToken.current)return
    const token=acceptedToken.current
    const frame=requestAnimationFrame(()=>{
      if(!mounted.current||getToken()!==token||acceptedToken.current!==token)return
      resultHeading.current?.focus({preventScroll:true})
      resultHeading.current?.scrollIntoView({block:'start',behavior:reducedMotion()?'instant':'smooth'})
    })
    return()=>cancelAnimationFrame(frame)
  },[result?.id])
  const openPicker=()=>{if(busy||pendingUpload.current||!client.features.image_detection)return;if(input.current){input.current.value='';input.current.click()}}
  const removeFile=()=>{if(busy||pendingUpload.current)return;completedUpload.current=false;acceptedToken.current=null;setFile(null);setResult(null);setSubmitError('');if(input.current)input.current.value=''}
  const chooseFile = (next?: File) => {""")
once("    if (busy || !next || !client.features.image_detection) return", "    if (busy || pendingUpload.current || !next || !client.features.image_detection) return")
once("    setFile(next); setResult(null)", "    completedUpload.current=false;acceptedToken.current=null;setFile(next);setResult(null);setSubmitError('')")
once("    if (busy || !file || fileOverLimit || !client.features.image_detection || !requireAuth()) return", "    if (busy || pendingUpload.current || completedUpload.current || !file || fileOverLimit || !client.features.image_detection || !requireAuth()) return")
once("    pendingUpload.current?.abort()\n",'')
once("    setBusy(true); setDragging(false); setResult(null)","    setBusy(true);setDragging(false);setResult(null);setSubmitError('')")
once("      setCrop(saved.crop); setResult(saved); onChange(); onDetected(saved)","""      if(!['healthy','attention','awaiting_model'].includes(saved.status)){
        const message=saved.status==='failed'?'本次检测未完成，照片与备注已保留，可以重试。':'样本已保存，检测尚未完成，请到检测记录查看状态。'
        setSubmitError(message);onChange();toast(message);return
      }
      completedUpload.current=true;acceptedToken.current=requestToken
      if(saved.status!=='awaiting_model')setCrop(saved.crop)
      setResult(saved);onChange();onDetected(saved)""")
once("    catch (error) {if (isCurrent()) toast((error as Error).message)}", "    catch (error) {if (isCurrent()){setSubmitError((error as Error).message);toast((error as Error).message)}}")
journey=next(row for row in s.splitlines() if row.startswith('    <DetectionJourney '))
once(journey,"""    <input ref={input} type="file" disabled={busy||!client.features.image_detection} accept="image/jpeg,image/png,image/webp" className="sr-only" aria-label="选择作物图片" onClick={event=>{event.currentTarget.value=''}} onChange={event=>chooseFile(event.target.files?.[0])}/>
    <DetectionJourney phase={busy?'detecting':result?(result.status==='awaiting_model'?'saved':'complete'):file?'details':'choose'} modelReady={modelReady} canUpload={client.features.image_detection} onUpload={result?()=>scrollTo(resultPanel.current):openPicker} onDetails={()=>{if(result){if(resultMetadata.current){resultMetadata.current.open=true;scrollTo(resultMetadata.current);resultMetadata.current.querySelector('summary')?.focus({preventScroll:true})}}else{scrollTo(details.current);details.current?.querySelector<HTMLElement>('select, textarea')?.focus({preventScroll:true})}}} onResult={()=>{scrollTo(resultHeading.current);resultHeading.current?.focus({preventScroll:true})}}/>
    {result?<DetectResultView record={result} originalUrl={preview} canChoose={client.features.image_detection&&!busy} canAsk={client.features.assistant&&Boolean(onViewAdvice)} headingRef={resultHeading} comparisonRef={resultPanel} metadataRef={resultMetadata} onChooseNext={openPicker} onViewAdvice={()=>{if(mounted.current&&getToken()===acceptedToken.current)onViewAdvice?.(result)}}/>:<>
    {submitError&&<div className="form-error detect-upload-error" role="alert">{submitError}</div>}""")
inner='<input ref={input} type="file" disabled={busy || !client.features.image_detection} accept="image/jpeg,image/png,image/webp" className="sr-only" aria-label="选择作物图片" onChange={event => chooseFile(event.target.files?.[0])}/>'
once(inner,'')
s=s.replace("onClick={() => input.current?.click()}","onClick={openPicker}")
once("onClick={() => {setFile(null); setResult(null); if (input.current) input.current.value = ''}}", "onClick={removeFile}")
line=next(row for row in s.splitlines() if row.startswith('      </div><div className="upload-actions">'))
once(line,"""      </div><div className="upload-actions"><span><ShieldCheck size={14}/>图片用于检测与小禾解读</span><button className="button primary detection-submit" type="submit" aria-busy={busy} disabled={!file||busy||fileOverLimit||!client.features.image_detection}>{busy?<LoaderCircle size={17} className="spin"/>:<CloudUpload size={17}/>} {busy?(modelReady?'正在识别…':'正在保存…'):(modelReady?'识别并保存':'保存检测样本')}</button></div>""")
aside=next(row for row in s.splitlines() if row.startswith('    </form>{result && <aside '))
once(aside,'    </form></div></>}')
s=s.replace(' CheckCircle2,','')
if '<Badge ' not in s:s=s.replace('{Badge, CropIcon,','{CropIcon,')
p.write_text(s,encoding='utf-8')
print('DetectPage now renders distinct input and completed-result views.')
