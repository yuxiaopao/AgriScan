import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil

# The local orchestrator prepends a manifest of public paths and checksums.
release = Path('/srv/agriscan/releases/release-20261029-user-isolation-104127')
current = Path('/srv/agriscan/current')
target = release / 'public/downloads'
stage = Path(manifest['stage']).resolve(strict=True)
backup = Path(manifest['backup']['backup']).resolve(strict=True)
assert stage.is_relative_to(Path('/srv/agriscan/bootstrap'))
assert stage.name.startswith('isolation-20261029-apk-code3-')
assert backup == Path('/srv/agriscan/shared/backups/user-isolation-20261029/apk-before')
assert target.resolve(strict=True).is_relative_to(release)
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
names = ('agriscan-test.apk', 'agriscan-test.apk.sha256', 'release.json')
assert [item['name'] for item in manifest['files']] == list(names)
before = {item['name']: item['sha256'] for item in manifest['backup']['files']}
after = {item['name']: item['sha256'] for item in manifest['files']}
metadata = json.loads((stage / 'release.json').read_text())
assert metadata == manifest['release']
assert metadata['version'] == '1.0.2' and metadata['version_code'] == 3
assert metadata['sha256'] == 'e343102879bd91e6a59715ec8fa3a491800520e603dfc1605e938ca25d91a605'
assert metadata['size_bytes'] == (stage / names[0]).stat().st_size == 18744688
assert (stage / names[1]).read_text().split() == [metadata['sha256'], names[0]]
for name in names:
    assert digest(stage / name) == after[name]
    assert digest(backup / name) == before[name]

prepared, published, restored, conflicts = {}, [], [], []
with (backup.parent / '.apk-publish.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    assert current.resolve() == release, 'Current release changed; nothing replaced.'
    assert all(digest(target / name) == before[name] for name in names), 'Published files changed since backup; nothing replaced.'
    transaction = stage.name.rsplit('-', 1)[-1]
    try:
        for name in names:
            temporary = target / ('.' + name + '.' + transaction + '.next')
            assert not temporary.exists()
            with (stage / name).open('rb') as source, temporary.open('xb') as output:
                prepared[name] = temporary
                shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            temporary.chmod(0o644)
            assert digest(temporary) == after[name]
        # APK and checksum become durable before ready metadata is switched.
        for name in names:
            assert current.resolve() == release, 'Current symlink changed during publish.'
            assert digest(target / name) == before[name], 'Concurrent file update detected; preserving it.'
            os.replace(prepared[name], target / name)
            published.append(name)
        assert all(digest(target / name) == after[name] for name in names)
        directory = os.open(target, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        for name in reversed(published):
            # Restore only bytes written by this transaction. Never overwrite
            # a concurrently published third version.
            if digest(target / name) == before[name]:
                continue
            if digest(target / name) != after[name]:
                conflicts.append(name)
                continue
            rollback = target / ('.' + name + '.' + transaction + '.rollback')
            shutil.copy2(backup / name, rollback)
            rollback.chmod(0o644)
            if digest(target / name) != after[name]:
                rollback.unlink()
                conflicts.append(name)
                continue
            os.replace(rollback, target / name)
            assert digest(target / name) == before[name]
            restored.append(name)
        print(json.dumps({'status':'failed','restored_own_files':restored,'concurrent_files_preserved':conflicts}))
        raise
    finally:
        for temporary in prepared.values():
            temporary.unlink(missing_ok=True)
print(json.dumps({'status':'published','current_release':str(release),'target_directory':str(target),
                  'backup_directory':str(backup),'staging_directory':str(stage),
                  'backup_directory_mode':oct(backup.stat().st_mode & 0o777),
                  'atomic_file_replacement':True,'release_metadata_published_last':True,
                  'concurrency_guard':'exclusive flock plus before/after SHA256 compare',
                  'rollback_policy':'restore own SHA256 only; preserve concurrently changed bytes',
                  'files':[{'name':name,'sha256':digest(target/name),'bytes':(target/name).stat().st_size}
                           for name in names], 'database_changed':False,'api_changed':False,'nginx_changed':False}))
