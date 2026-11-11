from pathlib import Path
import json
import re
import subprocess

folder = Path(__file__).parent
expected = set(json.loads((folder / 'manifest.json').read_text(encoding='utf8'))['paths'])
paths = {p for p in subprocess.check_output(['git', 'diff', '--cached', '--name-only', '-z']).decode('utf8').split('\0') if p}
assert paths == expected, 'Index no longer matches the explicit source manifest.'
known = []
config = Path('backend/.env')
if config.exists():
    for line in config.read_text(encoding='utf-8-sig').splitlines():
        if '=' not in line or line.lstrip().startswith('#'):
            continue
        key, value = line.split('=', 1)
        value = value.strip().strip('\"\'')
        if key.strip() in {'JWT_SECRET', 'CONFIG_ENCRYPTION_KEY', 'LLM_API_KEY', 'SMTP_PASSWORD', 'ADMIN_PASSWORD'} and len(value) >= 16 and not any(x in value.lower() for x in ['demo-secret', 'local-demo', 'example', 'changeme']):
            known.append(value)
access = Path('.runtime/server-admin-access.txt')
if access.exists():
    known.extend(line.split(': ', 1)[1] for line in access.read_text(encoding='utf8').splitlines() if line.startswith('Password: '))
patterns = {
    'private_key': r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
    'provider_token': r'\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{25,}|AKIA[A-Z0-9]{16})\b',
    'jwt_literal': r'\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\b',
}
findings = []
text_count = size = 0
for path in sorted(paths):
    data = subprocess.check_output(['git', 'show', ':' + path])
    size += len(data)
    if b'\0' in data:
        continue
    try:
        content = data.decode('utf8')
    except UnicodeDecodeError:
        continue
    text_count += 1
    findings.extend({'path': path, 'rule': rule} for rule, pattern in patterns.items() if re.search(pattern, content))
    if any(value in content for value in known):
        findings.append({'path': path, 'rule': 'known_private_value'})
subprocess.run(['git', 'diff', '--cached', '--check'], check=True)
report = {'selected_files': len(paths), 'text_files_scanned': text_count, 'staged_bytes': size, 'findings': findings, 'whitespace_check': 'passed', 'manifest_exact_match': True}
(folder / 'staged-audit.json').write_text(json.dumps(report, indent=2), encoding='utf8')
print(json.dumps(report))
assert not findings, 'Review required; no private values printed.'
