"""Fake bootstrap tests only. No SSH/network or real bootstrap path writes."""
import hashlib,importlib.util,json
from pathlib import Path
import tempfile
ROOT=Path(__file__).resolve().parent

def load(name,file):
 spec=importlib.util.spec_from_file_location(name,ROOT/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
s=load('preseed_server_checks','preseed-artifact-server.py');local=load('preseed_local_checks','preseed-artifact-local.py')
checks=[]
with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
 base=Path(temporary);boot=base/'bootstrap';parts=boot/'artifact-parts';parts.mkdir(parents=True)
 old=b'A'*s.CHUNK+b'B'*s.CHUNK+b'old-tail';new=b'A'*s.CHUNK+b'C'*s.CHUNK+b'new-tail'
 old_sha=hashlib.sha256(old).hexdigest();cached=parts/old_sha;cached.mkdir()
 for index,start in enumerate(range(0,len(old),s.CHUNK)):(cached/f'part-{index:03d}').write_bytes(old[start:start+s.CHUNK])
 source=base/'new.apk';source.write_bytes(new)
 plan=local.compare(source,cached,old_sha,'/srv/agriscan/bootstrap/old.apk')
 assert [p['index'] for p in plan['reuse_parts']]==[0]
 s.BOOT=boot;s.PARTS=parts
 before={str(path.relative_to(boot)):path.read_bytes() for path in boot.rglob('*') if path.is_file()}
 read=s.execute(plan,False);assert read['status']=='prepared_read_only' and not (parts/plan['new_sha256']).exists()
 assert before=={str(path.relative_to(boot)):path.read_bytes() for path in boot.rglob('*') if path.is_file()}
 checks.append('5MiB same-index compare and read-only inspection create no target directory')
 result=s.execute(plan,True);target=parts/plan['new_sha256']/'part-000'
 assert result['status']=='passed' and target.read_bytes()==old[:s.CHUNK]
 assert result['copied_parts'][0]['source']=='old_parts'
 checks.append('copy only verified matching part into new full SHA directory')
 assert s.execute(plan,True)['already_valid_parts']==[0]
 checks.append('existing correct target is reused idempotently')
 target.write_bytes(b'concurrent incomplete upload')
 try:s.execute(plan,True)
 except s.Refused as error:assert str(error)=='existing_target_part_conflict_preserved'
 else:raise AssertionError('conflicting destination overwritten')
 assert target.read_bytes()==b'concurrent incomplete upload'
 checks.append('conflicting/concurrent uploader part is preserved, never overwritten')
 # Force fallback to a complete, read-only old bootstrap file while retaining all
 # fake paths under the temporary local workspace.
 cached.rename(parts/'disabled-old-cache')
 published=boot/'old.apk';published.write_bytes(old)
 original_path=s.Path
 s.Path=lambda value:published if value=='/srv/agriscan/bootstrap/old.apk' else original_path(value)
 newer=b'A'*s.CHUNK+b'B'*s.CHUNK+b'different-tail';source.write_bytes(newer)
 oldlocal=parts/'disabled-old-cache'
 alternate=local.compare(source,oldlocal,old_sha,'/srv/agriscan/bootstrap/old.apk')
 fallback=s.execute(alternate,True)
 assert fallback['status']=='passed' and len(fallback['copied_parts'])==2
 assert all(part['source']=='old_bootstrap_apk' for part in fallback['copied_parts'])
 assert published.read_bytes()==old
 checks.append('full old APK fallback verifies old whole SHA and copies chunks without modifying published bootstrap APK')
 for bad in ({**plan,'new_sha256':'../escape'},{**plan,'old_bootstrap_apk':'/srv/agriscan/shared/production.env'},
             {**plan,'reuse_parts':[{**plan['reuse_parts'][0],'index':-1}]},
             {**plan,'reuse_parts':[{**plan['reuse_parts'][0],'sha256':'0'*64}]}):
  try:s.execute(bad,True)
  except s.Refused:pass
  else:raise AssertionError('unsafe scope/source accepted')
 checks.append('traversal/private source/invalid index/wrong chunk SHA all refuse before publication')
report={'status':'passed','checks':checks,'count':len(checks),'production_written':False,'network_called':False}
(ROOT/'preseed-helper-checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
