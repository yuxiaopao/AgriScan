from pathlib import Path
import re
p=Path('E:/AgriScan/mobile/src/WorkspacePages.tsx')
s=p.read_text(encoding='utf-8')
s=s.replace('article.crop).filter(Boolean)))],[articles])','article.crop).filter(Boolean))],[articles])')
s=re.sub(r'\(\{awaiting_model:.*?\}\[record.status\]\)', 'recordDescriptions[record.status]', s)
s=s.replace('if(health.status', 'if(!health||health.status')
p.write_text(s,encoding='utf-8')
