"""Snapshot current mobile sources and its shared task core with repo-relative hashes."""
import hashlib,json
from pathlib import Path

root=Path('E:/AgriScan');task=Path(__file__).resolve().parent;snapshot=task/'mobile'
assert not snapshot.exists(),'Preserve prior snapshots; this final root must be new.'
skip_parts={'node_modules','dist','build','.gradle','.kotlin','.idea','.git','.cxx','captures','out','bin','gen'}
skip_names={'local.properties','key.properties','keystore.properties','google-services.json'}
root_files={'package.json','package-lock.json','tsconfig.json','vite.config.ts','capacitor.config.ts','index.html','.env.example'}
rows=[]
for path in sorted((root/'mobile').rglob('*')):
    relative=path.relative_to(root/'mobile')
    if any(part in skip_parts for part in relative.parts) or path.is_symlink() or not path.is_file():continue
    if relative.parts[0] not in {'src','public','scripts','android'} and str(relative) not in root_files:continue
    if path.name in skip_names or path.suffix.lower() in {'.keystore','.jks','.p12','.pem','.key','.log','.apk','.aab','.tsbuildinfo'}:continue
    if path.name.startswith('.env') and path.name!='.env.example':continue
    if relative.as_posix().startswith(('android/app/src/main/assets/','android/capacitor-cordova-android-plugins/')):continue
    name='mobile/'+relative.as_posix();data=path.read_bytes();target=task/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    rows.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
name='shared/detectionTasks.ts';data=(root/name).read_bytes();digest=hashlib.sha256(data).hexdigest()
assert digest=='ac3e42c703eedc4a94b82aa8141a0fab4415805bdcd1f2b0d3a28c7a6b298a5e','Shared core changed after review; inspect before freezing.'
(task/'shared').mkdir();(task/name).write_bytes(data);rows.append({'path':name,'bytes':len(data),'sha256':digest});rows.sort(key=lambda row:row['path'])
for row in rows:assert hashlib.sha256((root/row['path']).read_bytes()).hexdigest()==row['sha256'],'Source changed during snapshot: '+row['path']
aggregate=hashlib.sha256('\n'.join(row['path']+':'+row['sha256'] for row in rows).encode()).hexdigest()
report={'status':'copied','source_root':str(root),'snapshot_root':str(task),'snapshot':str(snapshot),'path_convention':'All files[].path and source_files keys are repository-relative, including mobile/ and shared/.','source_file_count':len(rows),'source_bytes':sum(row['bytes'] for row in rows),'source_tree_sha256':aggregate,'source_hash_algorithm':'SHA256 of sorted repository-relative path:sha256 lines joined with LF','files':rows,'shared':{'path':name,'bytes':len(data),'sha256':digest,'snapshot':str(task/name)},'private_files_excluded':True,'generated_outputs_excluded':True,'head_only_snapshot':False}
(task/'mobile-source-manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({key:report[key] for key in ['status','snapshot','source_file_count','source_tree_sha256','shared']}))
