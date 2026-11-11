from desktop_ops import *
import sys
import re
state=json.loads((ROOT/'recording.json').read_text(encoding='utf-8'))
entry={'at':round(time.time()-state['started_at'],3),'label':sys.argv[1]}
log=(ROOT/'recorder-ffmpeg.log').read_text(encoding='utf-8',errors='replace')[-2500:]
times=re.findall(r'time=(\d+):(\d+):(\d+\.\d+)',log)
if times:
    h,m,s=times[-1];entry['video_at']=round(int(h)*3600+int(m)*60+float(s),3)
with (ROOT/'timeline.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(entry,ensure_ascii=False)+'\n')
print(json.dumps(entry,ensure_ascii=False))
