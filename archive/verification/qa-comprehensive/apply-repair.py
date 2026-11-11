"""Apply only the four explicitly authorized AgriScan repair surfaces."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import time
from urllib.parse import quote
from urllib.request import urlopen


ROOT = Path('/srv/agriscan')
BOOTSTRAP = ROOT / 'bootstrap'
PLAN = BOOTSTRAP / 'qa20261028_1935-repair-plan.json'
REPORT = ROOT / 'shared/logs/qa20261028_1935-repair-deployment.json'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def allowed(name):
    path = Path(name)
    return (not path.is_absolute() and '..' not in path.parts and '\\' not in name
            and (name in {'backend/app/admin.py', 'public/app.js'}
                 or name.startswith(('public/workspace/', 'public/admin/'))))


def load_manifest():
    data = json.loads((BOOTSTRAP / 'repair-manifest.json').read_text())
    assert data['run_id'] == 'qa20261028_1935'
    release = (ROOT / 'current').resolve(strict=True)
    assert str(release) == data['expected_release']
    assert release.parent == ROOT / 'releases'
    assert len({row['path'] for row in data['files']}) == len(data['files'])
    for row in data['files']:
        assert allowed(row['path']) and 0 < row['size'] < 30_000_000
        destination = release / row['path']
        assert destination.parent.resolve().is_relative_to(release)
        assert not destination.is_symlink()
    return data, release


def https(path):
    result = subprocess.run(['curl', '--silent', '--show-error', '--noproxy', '*', '--fail',
                             '--connect-timeout', '10', '--max-time', '60', '--resolve',
                             'flowly-ai.top:443:127.0.0.1', 'https://flowly-ai.top' + quote(path)],
                            capture_output=True, timeout=65)
    assert result.returncode == 0, 'Verified source HTTPS failed: ' + path
    return result.stdout


def status():
    result = subprocess.run(['systemctl', 'show', 'agriscan-api',
                             '--property=ActiveState,SubState,MainPID,NRestarts,MemoryCurrent,MemoryPeak'],
                            capture_output=True, text=True, timeout=10, check=True)
    return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['plan', 'apply'])
    parser.add_argument('--archive-sha256')
    args = parser.parse_args()
    manifest, release = load_manifest()
    if args.mode == 'plan':
        changed = []
        for row in manifest['files']:
            target = release / row['path']
            old = digest(target) if target.is_file() else None
            if old != row['sha256']:
                changed.append({**row, 'old_sha256': old})
        data = {'run_id': manifest['run_id'], 'release': str(release), 'changed': changed,
                'unchanged_files': len(manifest['files']) - len(changed)}
        PLAN.write_text(json.dumps(data, indent=2))
        print(json.dumps(data, indent=2))
        return

    plan = json.loads(PLAN.read_text())
    assert plan['release'] == str(release)
    archive = BOOTSTRAP / 'qa20261028_1935-repair.tar.gz'
    assert digest(archive) == args.archive_sha256
    expected = {row['path']: row for row in plan['changed']}
    replacements = {}
    with tarfile.open(archive, 'r:gz') as source:
        members = source.getmembers()
        assert len(members) == len(expected) and {member.name for member in members} == set(expected)
        for member in members:
            assert member.isfile() and allowed(member.name) and member.size == expected[member.name]['size']
            data = source.extractfile(member).read()
            assert hashlib.sha256(data).hexdigest() == expected[member.name]['sha256']
            replacements[member.name] = data
    for row in expected.values():
        target = release / row['path']
        assert (digest(target) if target.is_file() else None) == row['old_sha256'], 'Concurrent file change; deployment refused.'
    if 'backend/app/admin.py' in replacements:
        compile(replacements['backend/app/admin.py'], 'admin.py', 'exec')

    backup = ROOT / 'shared/backups' / ('qa20261028_1935-repair-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(mode=0o700)
    for name, row in expected.items():
        if row['old_sha256'] is not None:
            saved = backup / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(release / name, saved)
            assert digest(saved) == row['old_sha256']
    report = {'run_id': manifest['run_id'], 'release': str(release), 'backup': str(backup),
              'started_at': datetime.now(timezone.utc).isoformat(), 'files': plan['changed'],
              'unchanged_files': plan['unchanged_files'], 'service_before': status(), 'write_order': []}
    (backup / 'manifest.json').write_text(json.dumps(report, indent=2))
    REPORT.write_text(json.dumps(report, indent=2))
    # New static assets become readable before either HTML entry point changes.
    order = sorted(expected, key=lambda name: (name in {'public/workspace/index.html', 'public/admin/index.html'}, name))
    try:
        for name in order:
            target = release / name
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + '.qa20261028_1935.next')
            with temporary.open('xb') as output:
                output.write(replacements[name])
            temporary.chmod(0o644)
            os.replace(temporary, target)
            assert digest(target) == expected[name]['sha256']
            report['write_order'].append(name)
        if 'backend/app/admin.py' in replacements:
            subprocess.run(['systemctl', 'restart', 'agriscan-api'], check=True, timeout=45)
        for attempt in range(30):
            try:
                with urlopen('http://127.0.0.1:18000/api/health', timeout=2) as response:
                    health = json.load(response)
                if health == {'status': 'ok', 'database': 'connected', 'redis': 'connected', 'mode': 'production', 'model': 'ready'}:
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise RuntimeError('API did not become healthy after the authorized restart.')
        assert json.loads(https('/agriscan/api/health')) == health
        for name in order:
            if name.startswith('public/'):
                path = '/agriscan/' + name.removeprefix('public/')
                served = https(path)
                assert hashlib.sha256(served).hexdigest() == expected[name]['sha256'], 'Nginx served a mismatched repair file.'
        report['health'] = health
        report['verified_https_files'] = [name for name in order if name.startswith('public/')]
        report['service_after'] = status()
        assert report['service_after']['ActiveState'] == 'active' and report['service_after']['SubState'] == 'running'
        report['status'] = 'passed'
    except Exception as error:
        report['status'] = 'failed'
        report['failure'] = type(error).__name__
        raise
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        REPORT.write_text(json.dumps(report, indent=2))
    print(json.dumps({'status': report['status'], 'report': str(REPORT), 'backup': str(backup),
                      'changed_files': len(expected), 'write_order': report['write_order'],
                      'service_after': report['service_after']}, indent=2))


if __name__ == '__main__':
    main()
