"""Verify and activate one owned release, preserving the pre-existing Flowly site."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import time
from urllib.request import urlopen

root = Path('/srv/agriscan')
archive = root / 'bootstrap/agriscan-release.tar.gz'
expected = sys.argv[1]
if hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest() != expected:
    raise SystemExit('Release SHA256 mismatch; existing deployment retained.')
release = root / 'releases' / ('release-' + time.strftime('%Y%m%d-%H%M%S'))
release.mkdir(parents=True, exist_ok=False)


def extract(source):
    with tarfile.open(source, 'r:gz') as bundle:
        for member in bundle.getmembers():
            destination = (release / member.name).resolve()
            if not destination.is_relative_to(release.resolve()) or not (member.isfile() or member.isdir()):
                raise RuntimeError('Unsafe release member rejected.')
        bundle.extractall(release)


extract(archive)
final_backend = root / 'bootstrap/agriscan-backend-final.tar.gz'
if final_backend.exists():
    extract(final_backend)
if hashlib.file_digest((release / 'model/model.onnx').open('rb'), 'sha256').hexdigest() != 'ff623c94555ade8c08a425caee3fe6fba5465ebc61ebd81ee502376bca8d4773':
    raise SystemExit('Detector SHA256 mismatch.')
for folder, _, files in os.walk(release):
    Path(folder).chmod(0o755)
    for name in files:
        (Path(folder) / name).chmod(0o644)

current = root / 'current'
if current.exists() and not current.is_symlink():
    raise SystemExit('Unmanaged current directory exists; preserved.')
previous = current.resolve() if current.is_symlink() else None
next_link = root / '.current.next'
if next_link.is_symlink():
    next_link.unlink()
next_link.symlink_to(release, target_is_directory=True)
os.replace(next_link, current)
subprocess.run(['systemctl', 'enable', '--now', 'agriscan-api'], check=True)
subprocess.run(['systemctl', 'restart', 'agriscan-api'], check=True)
ready = False
for _ in range(60):
    try:
        with urlopen('http://127.0.0.1:18000/api/health', timeout=2) as response:
            if response.status == 200:
                ready = True
                break
    except Exception:
        time.sleep(2)
if not ready:
    if previous:
        next_link.symlink_to(previous, target_is_directory=True)
        os.replace(next_link, current)
        subprocess.run(['systemctl', 'restart', 'agriscan-api'], check=True)
    raise SystemExit('API did not become healthy; inspect agriscan-api journal. Existing Flowly was not changed.')

sites = Path('/var/www/sites')
sites.mkdir(parents=True, exist_ok=True)
public_link = sites / 'agriscan'
if public_link.exists() and not public_link.is_symlink():
    raise SystemExit('Unmanaged website directory exists; preserved.')
if not public_link.is_symlink():
    public_link.symlink_to(current / 'public', target_is_directory=True)

config = Path('/etc/nginx/conf.d/flowly-share.conf')
original = config.read_text(encoding='utf8')
include = '    include /etc/nginx/agriscan-locations.inc;\n'
if include not in original:
    updated = original
    found = False
    for match in re.finditer(r'(?m)^server\s*\{', original):
        start = match.start()
        opening = original.index('{', start)
        depth, end = 1, opening + 1
        while depth:
            if original[end] == '{':
                depth += 1
            elif original[end] == '}':
                depth -= 1
            end += 1
        block = original[start:end]
        if re.search(r'listen\s+443\s+ssl', block) and re.search(r'server_name\s+flowly-ai\.top\s+www\.flowly-ai\.top\s*;', block):
            offset = block.index('    location ')
            updated = original[:start + offset] + include + '\n' + original[start + offset:]
            found = True
            break
    if not found:
        raise SystemExit('Expected HTTPS domain server block not found; Nginx preserved.')
    backup = root / 'shared/backups' / ('nginx-before-agriscan-' + time.strftime('%Y%m%d-%H%M%S') + '.conf')
    shutil.copy2(config, backup)
    backup.chmod(0o600)
    config.write_text(updated, encoding='utf8')
    validation = subprocess.run(['nginx', '-t'], capture_output=True, text=True)
    if validation.returncode:
        config.write_text(original, encoding='utf8')
        raise SystemExit('Nginx validation failed; original configuration restored: ' + validation.stderr)
subprocess.run(['nginx', '-t'], check=True)
subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
print('Activated release:', release)
print('HTTPS website: https://flowly-ai.top/agriscan/')
print('Existing Flowly root and /app.apk retained. Credentials remain in /srv/agriscan/shared/production.env.')
