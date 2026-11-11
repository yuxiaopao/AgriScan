from pathlib import Path
import hashlib
import json
import os
import shutil

stage = Path('/srv/agriscan/bootstrap/domain-migration-20261029-app').resolve(strict=True)
target = Path('/srv/agriscan/current/public/downloads').resolve(strict=True)
backup = Path('/srv/agriscan/shared/backups/domain-migration-20261029-app-1.0.1-code2').resolve(strict=True)
assert target.is_relative_to(Path('/srv/agriscan/releases'))
assert stage.is_relative_to(Path('/srv/agriscan/bootstrap'))
assert backup.is_relative_to(Path('/srv/agriscan/shared/backups'))
names = ('agriscan-test.apk', 'agriscan-test.apk.sha256', 'release.json')
expected_apk = 'ab5ed73430cc0aea17b403377ede3f3d7e686cef2346b94aed1cc4d9e7d93f85'
expected_old = '7b195441f02683ef861aa8b35ed21ef4ebe6593e9de2b914b3c0f82cd24a2135'
digest = lambda file: hashlib.sha256(file.read_bytes()).hexdigest()
assert digest(target / names[0]) == digest(backup / names[0]) == expected_old, 'Published APK changed since backup'
for name in names:
    assert digest(target / name) == digest(backup / name), 'Published metadata changed since backup'
release = json.loads((stage / 'release.json').read_text(encoding='utf8'))
assert release['status'] == 'ready' and release['version'] == '1.0.1' and release['version_code'] == 2
assert release['package_id'] == 'cn.agriscan.mobile'
assert release['api_base_url'] == 'https://agriscan.ming-ai.top/agriscan'
assert release['sha256'] == digest(stage / names[0]) == expected_apk
assert release['size_bytes'] == (stage / names[0]).stat().st_size == 18744600
assert (stage / names[1]).read_text().split() == [expected_apk, names[0]]
prepared = []
for name in names:
    temporary = target / (name + '.domain-20261029-code2.next')
    assert not temporary.exists(), 'Unexpected prepared file; do not overwrite'
    with (stage / name).open('rb') as source, temporary.open('xb') as destination:
        shutil.copyfileobj(source, destination)
        destination.flush()
        os.fsync(destination.fileno())
    temporary.chmod(0o644)
    assert digest(temporary) == digest(stage / name)
    prepared.append((name, temporary))
published = []
try:
    # Metadata is switched last after the APK and checksum are fully prepared.
    for name, temporary in prepared:
        os.replace(temporary, target / name)
        published.append(name)
    rows = [{'name': name, 'bytes': (target / name).stat().st_size, 'sha256': digest(target / name)} for name in names]
    assert rows[0]['sha256'] == expected_apk
except Exception:
    for name in published:
        rollback = target / (name + '.domain-20261029-code2.rollback')
        shutil.copy2(backup / name, rollback)
        os.replace(rollback, target / name)
    raise
finally:
    for _, temporary in prepared:
        temporary.unlink(missing_ok=True)
report = {'status': 'published', 'targetDirectory': str(target), 'backupDirectory': str(backup),
          'atomicFileReplacement': True, 'releaseMetadataPublishedLast': True, 'files': rows,
          'databaseChanged': False, 'nginxChanged': False}
for name in names:
    (stage / name).unlink()
stage.rmdir()
print(json.dumps(report, ensure_ascii=False))
