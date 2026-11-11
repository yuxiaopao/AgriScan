import json,subprocess
from pathlib import Path
folder=Path('.runtime/server-latest-20261029')
package=json.loads((folder/'cachefix-package.json').read_text())
source=(folder/'activate-cachefix.py').read_text(encoding='utf-8')
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server',
                       '/srv/agriscan/venv/bin/python','-',package['sha256'],package['manifest_sha256'],package['release_id']],
                      input=source,encoding='utf-8',stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=300)
for line in result.stdout.splitlines():
    if line.startswith('{'):
        report=json.loads(line)
        (folder/'cachefix-deployment.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report))
if result.stderr:print(result.stderr)
raise SystemExit(result.returncode)
