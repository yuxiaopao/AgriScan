"""Observe public DNS/HTTP/TLS without changing host or network configuration."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
from tempfile import TemporaryDirectory
import time

import httpx

RUN = 'qa20261028_1935'
HOST = 'flowly-ai.top'
MARKER = 'AgriScanNetworkQA/' + RUN + '-' + str(int(time.time()))
REPORT = Path('/srv/agriscan/shared/logs') / (RUN + '-public-network-server.json')


def command(args, timeout=20):
    try:
        result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
        return {'exit_code': result.returncode, 'stdout': result.stdout.strip(), 'stderr': result.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'error': type(error).__name__}


def dns(item):
    name, kind = item
    result = {'name': name, 'type': kind}
    if shutil.which('dig'):
        result['dig'] = command(['dig', '+time=3', '+tries=1', '+noall', '+answer', name, kind], timeout=5)
    # Independent public resolver JSON; ordinary TLS verification remains enabled.
    for resolver in ('https://dns.alidns.com/resolve', 'https://dns.google/resolve'):
        try:
            response = httpx.get(resolver, params={'name': name, 'type': kind}, trust_env=False, timeout=6)
            response.raise_for_status()
            data = response.json()
            result['public_doh'] = {'resolver': resolver, 'status': data.get('Status'),
                                    'answer': data.get('Answer', []), 'authority': data.get('Authority', [])}
            break
        except Exception as error:
            result.setdefault('resolver_errors', []).append({'resolver': resolver, 'error': type(error).__name__})
    return result


def probe(item):
    scheme, path, resolve = item
    with TemporaryDirectory(prefix='agriscan-network-') as folder:
        body, headers = Path(folder) / 'body', Path(folder) / 'headers'
        args = ['curl', '--silent', '--show-error', '--noproxy', '*', '--connect-timeout', '8',
                '--max-time', '15', '--user-agent', MARKER, '--dump-header', str(headers),
                '--output', str(body), '--write-out', '%{http_code}\n%{remote_ip}\n%{url_effective}\n%{ssl_verify_result}']
        if resolve:
            args.extend(['--resolve', f'{HOST}:{443 if scheme == "https" else 80}:127.0.0.1'])
        args.append(f'{scheme}://{HOST}{path}?qa_network={RUN}')
        data = command(args, timeout=18)
        output = data.pop('stdout', '').splitlines()
        result = {'scheme': scheme, 'path': path, 'vantage': 'server_loopback_control' if resolve else 'server_normal_dns_public', **data}
        for index, key in enumerate(('http_status', 'remote_ip', 'effective_url', 'ssl_verify_result')):
            if len(output) > index:
                result[key] = output[index]
        raw = body.read_bytes() if body.exists() else b''
        text = raw.decode('utf-8', errors='replace')
        result['body_bytes'] = len(raw)
        result['body_sha256'] = hashlib.sha256(raw).hexdigest()
        result['body_markers'] = [word for word in ['AgriScan', '禾观', 'DNSPod', 'dnspod', '备案', '未备案', '拦截', 'qcloud.com', '腾讯云'] if word in text]
        result['headers'] = {}
        if headers.exists():
            for line in headers.read_text(errors='replace').splitlines():
                key, sep, value = line.partition(':')
                if sep and key.lower() in {'server', 'location', 'content-type', 'access-control-allow-origin'}:
                    result['headers'][key.lower()] = value.strip()
        return result


report = {'run_id': RUN, 'vantage': 'tencent-server host; normal system DNS vs loopback controls',
          'started_at': datetime.now(timezone.utc).isoformat(), 'request_marker': MARKER,
          'certificate_verification_disabled': False}
try:
    report['system_resolved_addresses'] = sorted({item[4][0] for item in socket.getaddrinfo(HOST, 443)})
except OSError as error:
    report['system_dns_error'] = type(error).__name__
with ThreadPoolExecutor(max_workers=6) as pool:
    report['dns'] = list(pool.map(dns, [(name, kind) for name in (HOST, 'www.' + HOST) for kind in ('A', 'AAAA', 'CNAME')]))
with ThreadPoolExecutor(max_workers=6) as pool:
    report['requests'] = list(pool.map(probe, [('https', '/agriscan/', False), ('https', '/agriscan/api/health', False),
                                             ('http', '/agriscan/', False), ('https', '/agriscan/', True),
                                             ('https', '/agriscan/api/health', True), ('http', '/agriscan/', True)]))

tls = command(['openssl', 's_client', '-connect', HOST + ':443', '-servername', HOST,
               '-verify_hostname', HOST, '-verify_return_error', '-showcerts'], timeout=15)
match = re.search(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', tls.get('stdout', ''), re.S)
report['tls'] = {'exit_code': tls.get('exit_code'), 'verification_summary': [line.strip() for line in
                 (tls.get('stdout', '') + '\n' + tls.get('stderr', '')).splitlines()
                 if any(word in line for word in ('Verify return code', 'Verification:', 'verify return:', 'Verification error'))]}
if match:
    cert = subprocess.run(['openssl', 'x509', '-noout', '-subject', '-issuer', '-dates', '-ext', 'subjectAltName'],
                          input=match.group(0), capture_output=True, text=True, timeout=5)
    report['tls']['certificate_public_details'] = cert.stdout.strip()

conf = Path('/etc/nginx/conf.d/flowly-share.conf')
text = conf.read_text() if conf.exists() else ''
report['nginx_domain_directives'] = [line.strip() for line in text.splitlines()
                                    if line.strip().startswith(('listen ', 'server_name ', 'ssl_certificate ', 'include /etc/nginx/agriscan-locations.inc'))]
report['nginx_syntax'] = command(['nginx', '-t'])
report['listeners_80_443'] = [line for line in command(['ss', '-ltn']).get('stdout', '').splitlines()
                             if re.search(r':(?:80|443)\s', line)]
report['firewall'] = {}
if shutil.which('firewall-cmd'):
    for label, argument in [('state', '--state'), ('services', '--list-services'), ('ports', '--list-ports')]:
        report['firewall'][label] = command(['firewall-cmd', argument], timeout=5)
if shutil.which('iptables'):
    rules = command(['iptables', '-S', 'INPUT'], timeout=5)
    report['firewall']['input_http_rules'] = [line for line in rules.get('stdout', '').splitlines()
                                             if line.startswith('-P ') or re.search(r'--dport (80|443)(?:\s|$)', line)]

preflight = command(['curl', '--silent', '--show-error', '--noproxy', '*', '--resolve', HOST + ':443:127.0.0.1',
                      '--max-time', '10', '--include', '--request', 'OPTIONS', '--header', 'Origin: https://' + HOST,
                      '--header', 'Access-Control-Request-Method: POST', '--header', 'Access-Control-Request-Headers: authorization,content-type',
                      'https://' + HOST + '/agriscan/api/detections'], timeout=12)
report['source_cors_preflight'] = preflight
report['nginx_upload_directives'] = [line.strip() for line in Path('/etc/nginx/agriscan-locations.inc').read_text().splitlines()
                                    if any(name in line for name in ('client_max_body_size', 'client_body_timeout', 'proxy_read_timeout'))]
report['own_access_log_lines'] = []
for file in (Path('/var/log/nginx/access.log'), Path('/var/log/nginx/flowly-access.log')):
    if file.is_file():
        with file.open('rb') as source:
            source.seek(max(0, file.stat().st_size - 256_000))
            for line in source.read().decode('utf-8', errors='replace').splitlines():
                if MARKER in line:
                    report['own_access_log_lines'].append({'file': str(file), 'line': line[:2000]})
report['finished_at'] = datetime.now(timezone.utc).isoformat()
REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'report': str(REPORT), 'system_resolved_addresses': report.get('system_resolved_addresses'),
                  'requests': report['requests'], 'tls': report['tls'], 'own_access_log_line_count': len(report['own_access_log_lines'])}, ensure_ascii=False, indent=2))
