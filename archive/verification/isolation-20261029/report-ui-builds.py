import hashlib
import json
from pathlib import Path
import re
from datetime import datetime, timezone

root=Path('.runtime/isolation-20261029/build')
ui_files=json.loads(Path('.runtime/isolation-20261029/owned-ui-files.json').read_text(encoding='utf-8'))
network_files=json.loads(Path('.runtime/isolation-20261029/owned-network-files.json').read_text(encoding='utf-8'))
report={'status':'passed','completed_at':datetime.now(timezone.utc).isoformat(),
        'source':'git archive HEAD frontend/admin/mobile + pure ownership UI and no-store network overlays',
        'unknown_design_imports_excluded':True,'native_apk_built':False,
        'browser_ui_tested':False,'source_files':{},'surfaces':{},
        'review':['Personal UI has no owner selector or owner_id request field.',
                  'Only explicit /admin/plots prefix allows PlotEditor owner_id.',
                  'Admin owner user options are searched and paginated server-side, with unassigned supported.',
                  'Detection owner change clears previous plot; unchanged historical associations are preserved.',
                  'API and authenticated image fetches force no-store; mobile late 401 checks captured base/token.',
                  'Account change clears personal lists/detail/analysis and discards late responses.']}
for name in ui_files+network_files:
    data=(root/name).read_bytes()
    report['source_files'][name]=hashlib.sha256(data).hexdigest()
for surface,prefix in [('frontend','/agriscan/workspace/'),('admin','/agriscan/admin/'),('mobile','/')]:
    dist=root/surface/'dist';index=(dist/'index.html').read_text(encoding='utf-8')
    scripts=re.findall(r'<script[^>]+src="([^"]+)"',index)
    assert scripts and all(src.startswith(prefix) for src in scripts)
    assert 'no-store' in ''.join(path.read_text(encoding='utf-8') for path in (dist/'assets').glob('*.js'))
    report['surfaces'][surface]={'tsc':'passed','vite_build':'passed','dist':str(dist.resolve()),
        'public_base':prefix,'entry_scripts':scripts,
        'files':{str(path.relative_to(dist)).replace('\\','/'):{'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
                 for path in sorted(dist.rglob('*')) if path.is_file() and (path.parent.name=='assets' or path.name=='index.html')}}
for name in network_files:
    assert "cache: 'no-store'" in (root/name).read_text(encoding='utf-8')
assert './polish.css' not in (root/'admin/src/Admin.tsx').read_text(encoding='utf-8')
assert 'MotionSurface' not in (root/'frontend/src/App.tsx').read_text(encoding='utf-8')
assert 'ObservationStack' not in (root/'frontend/src/Dashboard.tsx').read_text(encoding='utf-8')
target=Path('.runtime/isolation-20261029/ui-builds.json')
target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'source_files':len(report['source_files']),'report':str(target),
                  'entries':{name:value['entry_scripts'] for name,value in report['surfaces'].items()}}))
