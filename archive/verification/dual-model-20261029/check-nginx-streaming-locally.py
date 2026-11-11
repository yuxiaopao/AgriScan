"""Local fake-file tests; no SSH, API, Nginx command or real config writes."""
import hashlib,importlib.util,json,os
from pathlib import Path
import stat,sys,tempfile,types
ROOT=Path(__file__).resolve().parent
if os.name=='nt':sys.modules['fcntl']=types.SimpleNamespace()
spec=importlib.util.spec_from_file_location('nginx_streaming_checks',ROOT/'nginx-streaming-server.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
plan=json.loads((ROOT/'nginx-streaming-plan.json').read_text());m.validate(plan)
new=Path('deploy/agriscan-locations.inc').read_bytes();old=new.replace(m.ANCHOR+m.ADDED,m.ANCHOR,1)
assert m.sha(old)==plan['expected_inc_sha256'] and m.sha(new)==plan['expected_patched_sha256']
assert b'proxy_request_buffering off;' not in old.split(m.ANCHOR)[1].split(b'\n}',1)[0]
assert m.patch(old)==new
assert new.replace(m.ANCHOR+m.ADDED,m.ANCHOR,1)==old
checks=['confirmed deployed old API block is RED for streaming; exact two-line candidate is GREEN with all other bytes unchanged']
for raw in (b'location /wrong/api/ {}',old+old,new):
 try:m.patch(raw)
 except m.Refused:pass
 else:raise AssertionError('ambiguous/already changed input accepted')
checks.append('wrong/duplicate/already altered API block refuses mutation')
with tempfile.TemporaryDirectory(dir=ROOT) as directory:
 target=Path(directory)/'fake.inc';target.write_bytes(old);m.INC=target
 info=target.stat();identity=(info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))
 original_chown=getattr(os,'chown',None)
 if os.name=='nt':os.chown=lambda *args:None
 try:
  m.publish(new,m.sha(old),identity,'selftest');assert target.read_bytes()==new
  target.write_bytes(new+b'# external operator\n')
  try:m.publish(old,m.sha(new),identity,'race')
  except m.Refused:pass
  else:raise AssertionError('CAS overwrote external change')
  assert target.read_bytes()==new+b'# external operator\n'
 finally:
  if original_chown is None:delattr(os,'chown')
  else:os.chown=original_chown
checks.append('atomic fake-file CAS publishes exact patch and preserves concurrent edit')
report={'status':'passed','checks':checks,'production_modified':False,'network_called':False}
(ROOT/'nginx-streaming-local-checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
