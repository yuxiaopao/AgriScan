from pathlib import Path
p=Path('E:/AgriScan/mobile/src/DetectPage.tsx')
s=p.read_text(encoding='utf-8')
a=s.index("  return <div className=\"detect-page\">")
b=s.index("    {current!=='camera'&&<><div",a)
s=s[:a]+'''  function clearObservation(){setFile(null);setResult(null);setVideoResult(null);setError('');setMessage('');setDurationError('');setObservedCrop('');setPreviewError(false);setVideoDuration(0);setUncertain(false);setNote('');if(input.current)input.current.value=''}
  const metadata=<div className="capture-information">{!ready&&current==='image'&&<fieldset disabled={locked||complete||uncertain||!model}><label className="capture-crop">采集作物<select value={crop} onChange={event=>setCrop(event.target.value)}>{model?.available_crops.map(item=><option key={item}>{item}</option>)}</select><small className="form-hint">当前只保存照片，请按实际作物选择。</small></label></fieldset>}<details className="capture-options"><summary>地块与采样备注<span>选填</span></summary><fieldset disabled={locked||complete||uncertain}><div className="capture-meta"><label>关联地块<select value={plotId} disabled={!config.features.plots} onChange={event=>setPlotId(event.target.value)}><option value="">暂不关联地块</option>{selectablePlots.map(plot=><option key={plot.id} value={plot.id}>{plot.name} · {plot.crop}</option>)}</select><small className="form-hint">{!config.features.plots?'地块关联暂未开放。':ready?'可留空；选择后，地块作物需与照片识别结果一致。':!selectablePlots.length?'暂无对应作物的地块，可不关联。':'仅显示与采集作物一致的地块。'}</small></label><label className="sample-note">采样备注<input value={note} onChange={event=>setNote(event.target.value)} maxLength={500} placeholder="例如：植株中部叶片，雨后采样"/></label></div></fieldset></details></div>
  const mediaUnavailable=current!=='image'&&(!ready||(!capabilityLoading&&!capabilityError&&!(current==='video'?videoReady:liveReady)))
  return <div className="detect-page"><div className="page-intro"><h1>{observedCrop?`${observedCrop}观察`:current==='video'?'沿着时间观察':current==='camera'?'走近叶片看看':'记录一片叶子'}<Leaf size={21}/></h1><p>{observedCrop?'本次观察已保存，可回看照片、结果与采样备注。':current==='image'?(ready?'选一张清晰的叶片照片，识别作物并保存观察。':'先保存照片与采样备注，当前不会生成病害判断。'):current==='video'?'上传一段巡田视频，分别查看抽样画面的识别结果。':'相机按间隔识别画面，由你选择需要保存的观察。'}</p></div><div className="mode-switch" role="group" aria-label="选择观察方式">{modes.map(item=><button key={item.id} className={current===item.id?'active':''} aria-pressed={current===item.id} disabled={locked||!config.features[item.id==='image'?'image_detection':item.id==='video'?'video_detection':'live_detection']} onClick={()=>navigate(`detect/${item.id}`)}><item.icon size={18}/>{item.label}</button>)}</div>
    {!currentEnabled&&<div className="info-note" role="status">此观察方式暂未开放。已有结果仍可在记录中查看。</div>}
    {current==='image'&&!ready&&<div className="info-note" role="status"><Leaf size={17}/><span>{model?'当前可采集照片，不生成识别结论。':'正在读取识别服务状态…'}</span></div>}
    {current!=='image'&&capabilityLoading&&<p className="capture-message" role="status">正在确认{current==='video'?'视频':'实时'}观察是否可用…</p>}
    {current!=='image'&&capabilityError&&<ErrorNote message={`暂时无法确认媒体服务。${capabilityError}`} retry={()=>setCapabilityRetry(value=>value+1)}/>}
    {mediaUnavailable&&<div className="capture-unavailable"><p>{!ready?'视频与实时观察需要可用的识别服务。':current==='video'?'视频观察暂不可用，请联系管理员检查服务。':'实时观察暂不可用，请联系管理员检查服务。'}</p>{config.features.image_detection&&<button type="button" className="button outline" onClick={()=>navigate('detect/image')}>改用照片观察</button>}</div>}
    <form onSubmit={submit}>{current!=='camera'&&<CaptureProgress sampleOnly={!ready} fileReady={!!file} linked={!!plotId&&config.features.plots} complete={complete}/>} {current==='camera'&&metadata}
''' + s[b:]
# File selection is the first main action; optional metadata follows it.
s=s.replace("disabled={busy||!currentEnabled} onChange={event=>choose", "disabled={busy||!canChoose} onChange={event=>choose")
s=s.replace("disabled={!currentEnabled} onClick={()=>input.current?.click()}", "disabled={!canChoose} onClick={()=>input.current?.click()}")
s=s.replace("setVideoDuration(0);if(input.current)input.current.value=''}}><X", "setVideoDuration(0);setObservedCrop('');setError('');setUncertain(false);if(input.current)input.current.value=''}}><X")
s=s.replace("disabled={busy||!currentEnabled} onClick={()=>input.current?.click()}", "disabled={busy||!canChoose} onClick={()=>input.current?.click()}")
s=s.replace("    {current==='image'&&isNativeAndroid()", "    {metadata}\n    {current==='image'&&isNativeAndroid()")
start=s.index('    <FeedbackButton type=')
end=s.index('    </form>',start)
s=s[:start]+'''    <FeedbackButton type={complete||uncertain?'button':'submit'} onClick={complete?()=>{if(visible)resultPanel.current?.scrollIntoView({behavior:motionReduced()?'instant':'smooth',block:'start'})}:uncertain?()=>navigate('records'):undefined} className="primary full detect-submit" busy={busy} busyLabel={current==='video'?'正在分析视频':ready?'正在识别叶片':'正在保存样本'} complete={complete} completeLabel="已保存，查看这次观察" disabled={!complete&&!uncertain&&(!file||!model||!currentEnabled||!!fileSizeError||(current==='video'&&(!videoReady||!!durationError)))}><ScanLine size={18}/>{uncertain?'到记录中确认保存状态':current==='video'?'分析并保存视频':ready?'识别并保存':'保存采集样本'}</FeedbackButton>{busy&&<button type="button" className="button ghost full" onClick={()=>controller.current?.abort()}>停止等待</button>}{complete&&<button type="button" className="button outline full new-observation" onClick={clearObservation}>记录下一次观察</button>}</>}
''' +s[end:]
s=s.replace('<CameraCapture ready={liveReady}', '<CameraCapture visible={visible} ready={liveReady}')
s=s.replace('<div className="photo-tips"><h3>给小禾一张更清楚的照片</h3><p>保留完整叶片，避开反光与阴影；一次观察一片叶子。{ready?`当前覆盖 ${model.supported_crops.length} 种作物。`:\'\'}所选地块的作物须与{ready?\'识别结果\':\'采集作物\'}一致。</p></div>', '<div className="photo-tips"><h3>{current===\'image\'?\'拍清楚，再记录\':\'慢一点，看得更清楚\'}</h3><p>{current===\'image\'?\'保留完整叶片，避开强烈反光；一次观察一片叶子。\':\'缓慢移动镜头，让叶片保持清晰。抽样观察可能遗漏短暂出现的异常。\'}{ready?`当前可识别 ${model.supported_crops.length} 种作物。`:\'\'}</p></div>')
s=s.replace("{id:'image',label:'图片检测'", "{id:'image',label:'照片'")
s=s.replace("{id:'video',label:'视频检测'", "{id:'video',label:'视频'")
s=s.replace("{id:'camera',label:'实时相机'", "{id:'camera',label:'实时'")
p.write_text(s,encoding='utf-8')
