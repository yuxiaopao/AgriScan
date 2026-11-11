from pathlib import Path
import hashlib
import json
import shutil

source = Path('/srv/agriscan/current/public/downloads').resolve(strict=True)
assert source.is_relative_to(Path('/srv/agriscan/releases'))
target = Path('/srv/agriscan/shared/backups/domain-migration-20261029-app-1.0.1-code2')
names = ('agriscan-test.apk', 'agriscan-test.apk.sha256', 'release.json')
expected = '7b195441f02683ef861aa8b35ed21ef4ebe6593e9de2b914b3c0f82cd24a2135'
assert hashlib.sha256((source / names[0]).read_bytes()).hexdigest() == expected, 'Existing production artifact changed; stop before replacing'
target.mkdir(mode=0o700, parents=False, exist_ok=False)
rows = []
for name in names:
    original = source / name
    shutil.copy2(original, target / name)
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    assert hashlib.sha256((target / name).read_bytes()).hexdigest() == digest
    rows.append({'name': name, 'bytes': original.stat().st_size, 'sha256': digest})
report = {'backupDirectory': str(target), 'sourceDirectory': str(source), 'verifiedFiles': rows, 'databaseChanged': False, 'nginxChanged': False}
(target / 'backup-manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
print(json.dumps(report, ensure_ascii=False))
