import hashlib
import json
from pathlib import Path

root = Path('E:/AgriScan')
source = root / 'mobile'
destination = root / '.runtime/server-latest-20261029/mobile'
assert not destination.exists(), 'Existing snapshot preserved; choose a new explicit snapshot instead.'
destination.mkdir(parents=True)
skip_parts = {'node_modules','dist','build','.gradle','.kotlin','.idea','.git','.cxx','captures','out','bin','gen'}
skip_names = {'local.properties','key.properties','keystore.properties','google-services.json'}
root_files = {'package.json','package-lock.json','tsconfig.json','vite.config.ts','capacitor.config.ts','index.html','.env.example'}
rows = []
for path in sorted(source.rglob('*')):
    relative = path.relative_to(source)
    if any(part in skip_parts for part in relative.parts):
        continue
    if path.is_symlink() or not path.is_file():
        continue
    if relative.parts[0] not in {'src','public','scripts','android'} and str(relative) not in root_files:
        continue
    if path.name in skip_names or path.suffix.lower() in {'.keystore','.jks','.p12','.pem','.key','.log','.apk','.aab','.tsbuildinfo'}:
        continue
    if path.name.startswith('.env') and path.name != '.env.example':
        continue
    if relative.as_posix().startswith(('android/app/src/main/assets/', 'android/capacitor-cordova-android-plugins/')):
        continue
    data = path.read_bytes()
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    rows.append({'path':relative.as_posix(),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
for row in rows:
    assert hashlib.sha256((source/row['path']).read_bytes()).hexdigest() == row['sha256'], 'Source changed while snapshotting.'
aggregate = hashlib.sha256('\n'.join(row['path']+' '+row['sha256'] for row in rows).encode()).hexdigest()
manifest = {'status':'copied','source':str(source),'snapshot':str(destination),'source_file_count':len(rows),
            'source_bytes':sum(row['bytes'] for row in rows),'source_tree_sha256':aggregate,'files':rows,
            'private_files_excluded':True,'generated_outputs_excluded':True,'head_only_snapshot':False}
(destination.parent/'mobile-source-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps({key:manifest[key] for key in ('status','snapshot','source_file_count','source_bytes','source_tree_sha256')}))
