import hashlib,json,tarfile
from pathlib import Path
folder=Path('.runtime/server-latest-20261029')
files={'public/index.html':folder/'website/index.html',
       'release-info.json':folder/'release-info.json','payload-files.json':folder/'payload-files.json'}
archive=folder/'latest-website-cachefix.tar.gz'
with tarfile.open(archive,'w:gz') as bundle:
    for name,path in files.items():bundle.add(path,arcname=name,recursive=False)
info=json.loads((folder/'release-info.json').read_text())
report={'archive':str(archive),'bytes':archive.stat().st_size,
        'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'manifest_sha256':hashlib.sha256((folder/'payload-files.json').read_bytes()).hexdigest(),
        'release_id':info['release_id']}
(folder/'cachefix-package.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
