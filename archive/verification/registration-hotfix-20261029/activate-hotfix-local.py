"""Validate locally by default; explicit read/apply dispatch reviewed stdin helper."""
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
from queue import Empty, Queue
import shlex
import subprocess
from threading import Thread
from time import monotonic

FOLDER = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=FOLDER/'deployment-plan.json')
    parser.add_argument('--output', default='deployment.json')
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--read-server', action='store_true')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--timeout', type=int, default=1900)
    args = parser.parse_args()
    if args.apply and (args.inspect or args.read_server):
        parser.error('Apply cannot be combined with read-only inspection.')
    if args.read_server and not args.inspect:
        parser.error('--read-server requires --inspect.')
    output = FOLDER/args.output
    if output.parent != FOLDER or not args.output.endswith('.json') or output.exists():
        parser.error('Output must be a NEW JSON basename in this helper directory.')
    source = (FOLDER/'activate-hotfix-server.py').read_text(encoding='utf-8')
    ast.parse(source)
    digest = hashlib.sha256(source.encode()).hexdigest()
    if args.inspect:
        remote_args = ['--inspect']
        summary = dict(status='validated_local_only', mode='inspect', script_sha256=digest)
    else:
        plan = json.loads(args.plan.read_text(encoding='utf-8'))
        # Load definitions without the platform-specific flock import. This
        # executes only declarations and constant setup, never main/SSH/apply.
        module = ast.parse(source)
        module.body = [node for node in module.body if not
            (isinstance(node, ast.Import) and any(alias.name == 'fcntl' for alias in node.names))]
        namespace = {'__name__':'local_plan_validation'}
        exec(compile(module, '<reviewed-plan-validation>', 'exec'), namespace)
        namespace['PROTECTED'] = [PurePosixPath(path.as_posix()) for path in namespace['PROTECTED']]
        namespace['validate'](plan)
        remote_args = ['--plan-base64', base64.b64encode(json.dumps(plan).encode()).decode(), '--apply']
        summary = dict(status='validated_local_only', mode='apply', script_sha256=digest,
            run_id=plan['run_id'], release_id=plan['release_id'], expected_current=plan['expected_current'],
            patch_sha256=plan['patch_sha256'])
    if not args.apply and not args.read_server:
        print(json.dumps(summary)); return 0
    if args.apply and args.timeout < 1800:
        parser.error('Apply timeout must allow drain, graceful start and rollback: >=1800 seconds.')
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15',
        '-o', 'ServerAliveCountMax=8', 'tencent-server', '/srv/agriscan/venv/bin/python - '+shlex.join(remote_args)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    messages = Queue()
    def read_output():
        for line in process.stdout:
            messages.put(line.rstrip('\n'))
        messages.put(None)
    Thread(target=read_output, daemon=True).start()
    process.stdin.write(source); process.stdin.close()
    deadline = monotonic()+(args.timeout if args.apply else 90)
    result = None
    while True:
        remaining = deadline-monotonic()
        if remaining <= 0:
            process.terminate()
            raise SystemExit('SSH deadline reached. Inspect current service, Nginx and server hotfix report before retrying; remote completion is unknown.')
        try:
            line = messages.get(timeout=min(1, remaining))
        except Empty:
            continue
        if line is None:
            break
        if line.startswith(('STAGE ', 'PRECHECK_FAILED ')):
            print(line, flush=True)
        elif line.startswith('RESULT '):
            result = json.loads(line.removeprefix('RESULT '))
    code = process.wait(timeout=15)
    if result is None:
        raise SystemExit('No unique safe server report received. Raw SSH/Python output was withheld; inspect server state before retrying.')
    result.update(server_script_sha256=digest, ssh_exit_code=code)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(dict(status=result['status'], mode='apply' if args.apply else 'inspect', report=str(output))))
    return 0 if code == 0 and result['status'] in ('passed', 'read_only_observed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
