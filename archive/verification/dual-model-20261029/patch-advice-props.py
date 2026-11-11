from pathlib import Path
p=Path('frontend/src/App.tsx');s=p.read_text(encoding='utf-8')
old='onDetected={client.features.assistant ? queueDetection : () => {}}/>'
assert s.count(old)==1
s=s.replace(old,'onDetected={client.features.assistant ? queueDetection : () => {}} onViewAdvice={requestAdvice}/>',1)
old='detectionRequests={detectionRequests} onDetectionHandled={handledDetection}/>'
assert s.count(old)==1
s=s.replace(old,'detectionRequests={detectionRequests} onDetectionHandled={handledDetection} adviceRequest={adviceRequest} onAdviceHandled={handledAdvice}/>',1)
p.write_text(s,encoding='utf-8')
print('Result advice opens the already queued/cached analysis explicitly.')
