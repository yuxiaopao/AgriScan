"""Transfer a release artifact to this project's server, then atomically verify it."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from pathlib import Path
import shlex
import subprocess
import sys

source = Path(sys.argv[1]).resolve(strict=True)
destination = sys.argv[2]
if not destination.startswith('/srv/agriscan/') or '..' in Path(destination).parts:
    raise SystemExit('Destination must stay inside /srv/agriscan/.')
digest = hashlib.sha256(source.read_bytes()).hexdigest()
local_parts = Path(__file__).resolve().parents[1] / '.runtime/artifact-upload-parts' / digest[:16]
local_parts.mkdir(parents=True, exist_ok=True)
remote_parts = '/srv/agriscan/bootstrap/artifact-parts/' + digest
parts = []
with source.open('rb') as original:
    while block := original.read(5 * 1024 * 1024):
        part = local_parts / f'part-{len(parts):03d}'
        part.write_bytes(block)
        parts.append(part)
options = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15']
flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def run(args, input_text=None, timeout=900):
    try:
        result = subprocess.run(args, input=input_text, capture_output=True, text=True,
                                timeout=timeout, creationflags=flags)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, '', 'SSH operation timed out')
    return result


setup = run(['ssh', *options, 'tencent-server', 'mkdir -p ' + shlex.quote(remote_parts)])
if setup.returncode:
    raise SystemExit(setup.stderr)


def put(part):
    expected = hashlib.sha256(part.read_bytes()).hexdigest()
    remote = remote_parts + '/' + part.name
    for _ in range(3):
        exists = run(['ssh', *options, 'tencent-server', 'sha256sum ' + shlex.quote(remote)])
        if exists.returncode == 0 and exists.stdout.startswith(expected):
            return part.name + ' verified'
        result = run(['scp', *options, str(part), 'tencent-server:' + remote])
        if result.returncode == 0:
            return part.name + ' uploaded'
    raise RuntimeError(part.name + ' did not transfer; completed parts are retained for retry.')


with ThreadPoolExecutor(max_workers=4) as pool:
    for number, future in enumerate(as_completed(pool.submit(put, part) for part in parts), 1):
        print(f'{number}/{len(parts)} {future.result()}', flush=True)
script = f'''from pathlib import Path
import hashlib,os
target=Path({destination!r})
resolved=target.resolve()
if not resolved.is_relative_to(Path('/srv/agriscan').resolve()): raise SystemExit('Unexpected resolved target')
target.parent.mkdir(parents=True,exist_ok=True)
temporary=target.with_name(target.name+'.next')
with temporary.open('wb') as output:
    for index in range({len(parts)}):
        with (Path({remote_parts!r})/f'part-{{index:03d}}').open('rb') as original:
            while data:=original.read(1024*1024): output.write(data)
with temporary.open('rb') as original: actual=hashlib.file_digest(original,'sha256').hexdigest()
if actual!={digest!r}:
    temporary.unlink()
    raise SystemExit('Artifact SHA256 mismatch; published file retained')
temporary.chmod(0o644)
os.replace(temporary,target)
print('Artifact verified and published:',actual,target.stat().st_size)
'''
result = run(['ssh', *options, 'tencent-server', 'python3 -'], input_text=script)
if result.returncode:
    raise SystemExit(result.stderr or result.stdout)
print(result.stdout.strip(), flush=True)
