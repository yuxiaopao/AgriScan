import json
from pathlib import Path
import subprocess

patches={
'frontend/src/api.ts': [('...options, headers, signal: options.signal', "...options, headers, cache: 'no-store', signal: options.signal")],
'frontend/src/components.tsx': [('fetch(resolved, {headers, signal:', "fetch(resolved, {headers, cache: 'no-store', signal:")],
'mobile/src/api.ts': [('...options, headers, signal}', "...options, headers, cache: 'no-store', signal}"),
('response.status === 401&&token)', 'response.status === 401&&token&&localStorage.getItem(tokenKey(base))===token)')],
'mobile/src/components.tsx': [(' : undefined, signal: controller.signal}', " : undefined, cache: 'no-store', signal: controller.signal}")],
}
for name,changes in patches.items():
    content=subprocess.check_output(['git','show','HEAD:'+name]).decode('utf-8')
    for old,new in changes:
        assert old in content,name
        content=content.replace(old,new,1)
    target=Path('.runtime/isolation-20261029/owned-network')/name
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(content,encoding='utf-8')
Path('.runtime/isolation-20261029/owned-network-files.json').write_text(json.dumps(list(patches),indent=2),encoding='utf-8')
print('Four network-only snapshots created without parallel UI changes')
