"""Synthetic helper checks and real local manifest comparison; no network/activation."""
import importlib.util,json,os,sys,tempfile,types
from pathlib import Path
ROOT=Path(__file__).resolve().parent
if os.name=='nt':sys.modules['fcntl']=types.SimpleNamespace();sys.modules['grp']=types.SimpleNamespace()
spec=importlib.util.spec_from_file_location('static_final_checks',ROOT/'activate-static-final-server.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
plan=json.loads((ROOT/'static-final-plan.json').read_text());m.validate(plan)
checks=[]
previous=json.loads((ROOT/'first-production-release/payload-files.json').read_text())
latest=json.loads((ROOT/'payload-files.json').read_text())
assert len(latest)==plan['expected_payload_files']==142
old_backend={name:sha for name,sha in previous.items() if name.startswith('backend/app/')}
new_backend={name:sha for name,sha in latest.items() if name.startswith('backend/app/')}
assert old_backend==new_backend and old_backend
for name in ('model-classification/model.onnx','model-classification/manifest.json'):
    assert latest[name]==previous[name]
checks.append('all 142 new payload entries loaded; every backend source hash and classifier artifact matches first activated release')
with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
    base=Path(temporary);old=base/'old';new=base/'new'
    for folder in (old,new):
        for relative,data in [('backend/app/main.py',b'same source'),('model/model.onnx',b'same detector'),('model-classification/model.onnx',b'same classifier')]:
            p=folder/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    before={name:m.tree(old,name) for name in m.UNCHANGED_TREES};m.unchanged_trees(old,new,before)
    checks.append('identical copied backend and both model trees pass without loading a model')
    for folder,value in ((old,b'old compiled cache'),(new,b'new compiled cache')):
        cache=folder/'backend/app/__pycache__/main.cpython-312.pyc';cache.parent.mkdir();cache.write_bytes(value)
        (folder/'backend/app/legacy.pyo').write_bytes(value)
    m.unchanged_trees(old,new,before)
    checks.append('backend __pycache__/pyc/pyo are explicitly ignored while every product file remains strict')
    for relative in ('backend/app/main.py','model/model.onnx','model-classification/model.onnx'):
        file=new/relative;original=file.read_bytes();file.write_bytes(b'changed')
        try:m.unchanged_trees(old,new,before)
        except m.Refused as error:assert str(error)=='backend_or_models_changed_refuse_no_restart'
        else:raise AssertionError('changed API/model accepted')
        file.write_bytes(original)
    checks.append('any backend/detector/classifier byte change rejects static-only activation')
    extra=new/'backend/app/extra.py';extra.write_bytes(b'extra')
    try:m.unchanged_trees(old,new,before)
    except m.Refused:pass
    else:raise AssertionError('extra API source accepted')
    checks.append('extra API file also rejects static-only activation')
    extra.unlink()
    for folder,value in ((old,b'old model cache'),(new,b'changed model cache')):
        cache=folder/'model/__pycache__/model.pyc';cache.parent.mkdir();cache.write_bytes(value)
    model_before={name:m.tree(old,name) for name in m.UNCHANGED_TREES}
    try:m.unchanged_trees(old,new,model_before)
    except m.Refused:pass
    else:raise AssertionError('model tree cache difference was ignored')
    checks.append('model trees do not inherit the backend cache exclusion and remain fully byte strict')
service={'ActiveState':'active','SubState':'running','MainPID':str(plan['expected_api_pid']),'NRestarts':str(plan['expected_api_nrestarts'])};m.runtime_matches(plan,service)
for changed in ({**service,'MainPID':'999'},{**service,'NRestarts':'99'},{**service,'ActiveState':'inactive'}):
    try:m.runtime_matches(plan,changed)
    except m.Refused:pass
    else:raise AssertionError('API restart/crash accepted')
checks.append('PID restart counter and active state CAS reject a changed API')
report={'status':'passed','checks':checks,'count':len(checks),'network_called':False,'activation_executed':False,'api_restart_attempts':0}
(ROOT/'static-final-helper-checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
