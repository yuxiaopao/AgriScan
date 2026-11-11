"""Local helper checks only; never calls activate, SSH, systemd, MySQL or HTTP."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tarfile
import types
from uuid import uuid4

folder=Path(__file__).resolve().parent
if os.name=='nt':
    sys.modules['fcntl']=types.SimpleNamespace()
    sys.modules['grp']=types.SimpleNamespace()
spec=importlib.util.spec_from_file_location('activation_helpers',folder/'activate-server.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
checks=[]
assert module.seconds('5s')==5 and module.seconds('2min')==120 and module.seconds('3min')==180
checks.append('systemd real duration formats')
for unsafe in ('../private','/absolute','public/../private','public\\secret','./backend/app/main.py'):
    try:
        module.path_name(unsafe)
    except module.ActivationError:
        pass
    else:
        raise AssertionError('Unsafe path accepted')
checks.append('absolute traversal and Windows separators rejected')
def archive(entries):
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w:gz') as bundle:
        for name,kind in entries:
            item=tarfile.TarInfo(name)
            item.type=kind
            if kind==tarfile.REGTYPE:
                item.size=2
                bundle.addfile(item,io.BytesIO(b'{}'))
            else:
                item.linkname='/private'
                bundle.addfile(item)
    stream.seek(0)
    return tarfile.open(fileobj=stream,mode='r:gz')
for entries in ([('public/index.html',tarfile.SYMTYPE)],[('backend/.env',tarfile.REGTYPE)],
                [('public/a',tarfile.REGTYPE),('public/a',tarfile.REGTYPE)],
                [('public/downloads/agriscan-test.apk',tarfile.REGTYPE)]):
    with archive(entries) as bundle:
        try:
            module.members(bundle,'payload-files.json')
        except module.ActivationError:
            pass
        else:
            raise AssertionError('Unsafe archive accepted')
checks.append('symlink duplicate private-env and bundled-APK archive entries rejected')
with archive([('model-classification/model.onnx',tarfile.REGTYPE),('model-classification/manifest.json',tarfile.REGTYPE)]) as bundle:
    assert len(module.members(bundle,'payload-files.json',classifier=True))==2
checks.append('classifier archive accepts only its two exact files')
before=b'A=unchanged\n# keep comment\nB=still-unchanged\n'
line=b'CLASSIFICATION_MODEL_MANIFEST=/srv/agriscan/current/model-classification/manifest.json\n'
after=module.patch_env(before,line)
assert module.without_classification(after)==before
assert module.env_value(after)==module.ENV_VALUE
assert module.patch_env(after,b'')==before
try:
    module.env_value(after+line)
except module.ActivationError:
    pass
else:
    raise AssertionError('Duplicate environment key accepted')
try:
    module.env_value(after+b'export '+line)
except module.ActivationError:
    pass
else:
    raise AssertionError('Export-prefixed duplicate environment key accepted')
checks.append('only classification env line changes and duplicate is rejected')
plan=json.loads((folder/'deployment-plan.example.json').read_text(encoding='utf-8'))
plan.update(patch_sha256='0'*64,payload_manifest_sha256='1'*64,release_id='release-20261029-dual-model-localcheck')
original_path,original_root=module.Path,module.ROOT
module.Path,module.ROOT=PurePosixPath,PurePosixPath('/srv/agriscan')
module.validate_plan(plan)
try:
    module.validate_plan({**plan,'admin_password':'REDACTED_SECRET'})
except module.ActivationError:
    pass
else:
    raise AssertionError('Private/unknown plan field accepted')
module.Path,module.ROOT=original_path,original_root
checks.append('public plan schema rejects credential/unknown fields')
temporary=folder/('activation-selftest-'+uuid4().hex)
temporary.mkdir()
assert temporary.resolve().is_relative_to(folder.resolve())
fake_env=temporary/'production.env.fake'
fake_env.write_bytes(before)
module.ENV=fake_env
original_chown=getattr(os,'chown',None)
if os.name=='nt':
    os.chown=lambda *_args:None
try:
    details=fake_env.stat()
    identity=(details.st_uid,details.st_gid,stat.S_IMODE(details.st_mode))
    module.atomic_env(after,hashlib.sha256(before).hexdigest(),identity,'localcheck')
    assert fake_env.read_bytes()==after
    changed=after+b'EXTERNAL=preserve\n'
    fake_env.write_bytes(changed)
    try:
        module.atomic_env(before,hashlib.sha256(after).hexdigest(),identity,'must-not-overwrite')
    except module.ActivationError:
        pass
    else:
        raise AssertionError('Concurrent env update overwritten')
    assert fake_env.read_bytes()==changed
finally:
    if original_chown is not None:
        os.chown=original_chown
    elif hasattr(os,'chown'):
        delattr(os,'chown')
    fake_env.unlink()
    temporary.rmdir()
checks.append('atomic env CAS preserves a concurrent edit using local fake file only')
report={'status':'passed','checks':checks,'count':len(checks),'activation_executed':False,
        'server_contacted':False,'private_values_read':False}
(folder/'activation-local-checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
