"""Freeze only reviewed backend changes and changed web build files."""
from datetime import datetime, timezone, timedelta
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PARENT = '/srv/agriscan/releases/release-20261029-dual-model-190833'
def digest(raw):
    return hashlib.sha256(raw).hexdigest()
def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
release_id = 'release-' + stamp + '-registration-hotfix'
previous = json.loads((ROOT/'.runtime/dual-model-20261029/payload-files.json').read_text('utf-8-sig'))
payload = {}
for name in ('schemas.py', 'extensions.py', 'admin.py'):
    relative = 'backend/app/' + name
    payload[relative] = (ROOT/relative).read_bytes()
entries = {}
for surface, target in (('frontend', 'workspace'), ('admin', 'admin')):
    build = OUT/surface/'dist'
    for path in sorted(build.rglob('*')):
        if path.is_file():
            relative = 'public/' + target + '/' + path.relative_to(build).as_posix()
            raw = path.read_bytes()
            if previous.get(relative) != digest(raw):
                payload[relative] = raw
    html = (build/'index.html').read_text('utf-8')
    entries[target+'_entries'] = re.findall(r'(?:src|href)="([^"]+\.(?:js|css))"', html)
sources = subprocess.check_output(['git', 'ls-files', 'backend/app', 'frontend', 'admin', 'mobile/src', 'shared'], cwd=ROOT, encoding='utf-8').splitlines()
sources += ['shared/accountValidation.ts', 'shared/apiErrors.ts']
source_hashes = {name: digest((ROOT/name).read_bytes()) for name in sorted(set(sources)) if (ROOT/name).is_file()}
info = {'release_id': release_id, 'parent_release': PARENT,
        'scope': 'registration identifier and Chinese validation hotfix; API/workspace/admin',
        'base_commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,encoding='ascii').strip(),
        'apk_unchanged': True, 'sources': source_hashes, **entries}
payload['hotfix-info.json'] = encoded(info)
manifest = encoded({name: digest(raw) for name, raw in sorted(payload.items())})
payload['hotfix-files.json'] = manifest
archive = OUT/'registration-hotfix.tar.gz'
with tarfile.open(archive, 'w:gz') as bundle:
    for name, raw in sorted(payload.items()):
        entry = tarfile.TarInfo(name)
        entry.size = len(raw)
        entry.mode = 0o644
        entry.mtime = 0
        bundle.addfile(entry, io.BytesIO(raw))
(OUT/'hotfix-info.json').write_bytes(payload['hotfix-info.json'])
(OUT/'hotfix-files.json').write_bytes(manifest)
result = {'run_id': 'registration-hotfix-' + stamp, 'release_id': release_id,
          'patch_archive_path': '/srv/agriscan/bootstrap/registration-hotfix-' + stamp + '.tar.gz',
          'patch_sha256': digest(archive.read_bytes()),
          'payload_manifest_sha256': digest(manifest), 'expected_payload_files': len(payload)-1,
          'archive_local': str(archive), 'archive_bytes': archive.stat().st_size}
(OUT/'package.json').write_bytes(encoded(result))
print(json.dumps({key: value for key, value in result.items() if key != 'archive_local'}))
