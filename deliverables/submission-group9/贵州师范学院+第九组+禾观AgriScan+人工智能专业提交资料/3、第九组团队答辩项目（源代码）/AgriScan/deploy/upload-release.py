"""Upload an owned release over parallel SSH streams, checking the final SHA256."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from pathlib import Path
import subprocess
import sys
import time

archive = Path(sys.argv[1]).resolve(strict=True)
part_dir = archive.parent / 'upload-parts'
part_dir.mkdir(exist_ok=True)
parts = []
with archive.open('rb') as source:
    index = 0
    while data := source.read(5 * 1024 * 1024):
        target = part_dir / f'part-{index:03d}'
        target.write_bytes(data)
        parts.append(target)
        index += 1
options = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15']
flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def command(args, timeout=900):
    try:
        return subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout, creationflags=flags)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, '', 'SSH operation timed out; completed parts retained')


setup = command(['ssh', *options, 'tencent-server', 'mkdir -p /srv/agriscan/bootstrap/release-parts'])
if setup.returncode:
    raise SystemExit(setup.stderr)


def upload(part):
    expected = hashlib.sha256(part.read_bytes()).hexdigest()
    remote = '/srv/agriscan/bootstrap/release-parts/' + part.name
    present = command(['ssh', *options, 'tencent-server', 'sha256sum ' + remote])
    if present.returncode == 0 and present.stdout.startswith(expected):
        return part.name + ' already verified'
    for attempt in range(3):
        result = command(['scp', *options, str(part), 'tencent-server:' + remote])
        if result.returncode == 0:
            return part.name + ' uploaded'
        time.sleep(2 + attempt)
    raise RuntimeError(part.name + ': ' + result.stderr[:200])


with ThreadPoolExecutor(max_workers=6) as pool:
    futures = [pool.submit(upload, part) for part in parts]
    for index, future in enumerate(as_completed(futures), 1):
        print(f'{index}/{len(parts)}: {future.result()}', flush=True)
expected = hashlib.sha256(archive.read_bytes()).hexdigest()
merge = command(['ssh', *options, 'tencent-server', 'cat /srv/agriscan/bootstrap/release-parts/part-* > /srv/agriscan/bootstrap/agriscan-release.tar.gz.next && sha256sum /srv/agriscan/bootstrap/agriscan-release.tar.gz.next'])
if merge.returncode or not merge.stdout.startswith(expected):
    raise SystemExit('Assembled release SHA256 mismatch; activation refused.')
result = command(['ssh', *options, 'tencent-server', 'mv /srv/agriscan/bootstrap/agriscan-release.tar.gz.next /srv/agriscan/bootstrap/agriscan-release.tar.gz'])
if result.returncode:
    raise SystemExit(result.stderr)
print('Release transferred and SHA256 verified:', expected, flush=True)
