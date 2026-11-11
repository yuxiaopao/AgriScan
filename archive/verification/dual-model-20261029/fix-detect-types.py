from pathlib import Path
p=Path('frontend/src/Pages.tsx');s=p.read_text(encoding='utf-8')
s=s.replace('{ArrowRight, ArrowUpRight, BookOpen, Check, CircleAlert,','{ArrowUpRight, BookOpen, Check, CheckCircle2, CircleAlert,')
old='record={result} busy={busy} modelReady={modelReady} detections={result?.boxes}'
assert s.count(old)==1
s=s.replace(old,'record={null} busy={busy} modelReady={modelReady}',1)
p.write_text(s,encoding='utf-8')
print('Input view has no previous result; original settings icon import retained.')
