import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

release = Path('/srv/agriscan/releases/release-20261029-user-isolation-104127')
current = Path('/srv/agriscan/current')
assert current.resolve(strict=True) == release
target = (current / 'public/downloads').resolve(strict=True)
assert target.is_relative_to(release)
backup = Path('/srv/agriscan/shared/backups/user-isolation-20261029/apk-before')
backup.mkdir(parents=True, mode=0o700, exist_ok=True)
backup.chmod(0o700)
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
names = ('agriscan-test.apk', 'agriscan-test.apk.sha256', 'release.json')
lock_path = backup.parent / '.apk-publish.lock'
with lock_path.open('a') as lock:
    os.chmod(lock_path, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX)
    assert digest(target / names[0]) == 'ab5ed73430cc0aea17b403377ede3f3d7e686cef2346b94aed1cc4d9e7d93f85'
    meta = json.loads((target / names[2]).read_text())
    assert meta['version'] == '1.0.1' and meta['version_code'] == 2
    rows = []
    for name in names:
        old_hash = digest(target / name)
        saved = backup / name
        if saved.exists():
            assert digest(saved) == old_hash, 'Backup already holds different bytes; preserved.'
        else:
            temporary = backup / ('.' + name + '.' + uuid4().hex + '.part')
            shutil.copy2(target / name, temporary)
            temporary.chmod(0o600)
            assert digest(temporary) == old_hash
            os.replace(temporary, saved)
        saved.chmod(0o600)
        rows.append({'name': name, 'sha256': old_hash, 'bytes': saved.stat().st_size,
                     'backup_mode': oct(saved.stat().st_mode & 0o777)})
    assert current.resolve() == release
    print(json.dumps({'status': 'backed_up', 'current_release': str(release),
                      'backup': str(backup), 'backup_mode': oct(backup.stat().st_mode & 0o777), 'files': rows}))
