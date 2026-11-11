import hashlib
import json
from pathlib import Path
import subprocess
folder=Path('.runtime/server-latest-20261029')
package=json.loads((folder/'package.json').read_text())
manifest_sha=hashlib.sha256((folder/'payload-files.json').read_bytes()).hexdigest()
program=(folder/'activate-static.py').read_text(encoding='utf-8')
command=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server',
         '/srv/agriscan/venv/bin/python','-',package['sha256'],package['release_id'],manifest_sha]
result=subprocess.run(command,input=program,encoding='utf-8',stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=900)
for line in result.stdout.splitlines():
    if line.startswith('{'):
        report=json.loads(line)
        (folder/'deployment.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report))
if result.stderr: print(result.stderr)
raise SystemExit(result.returncode)
