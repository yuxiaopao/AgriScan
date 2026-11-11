"""Add one owned AgriScan virtual host; retain Flowly, data, model and secrets."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
import time
from uuid import uuid4

DOMAIN = 'agriscan.ming-ai.top'
EXPECTED_IP = '162.14.71.77'
ROOT = Path('/srv/agriscan')
ENV = ROOT / 'shared/production.env'
VHOST = Path('/etc/nginx/conf.d/zz-agriscan.conf')
FLOWLY = Path('/etc/nginx/conf.d/flowly-share.conf')
INCLUDE = Path('/etc/nginx/agriscan-locations.inc')
WEBROOT = Path('/var/www/certbot')
CERT = Path('/etc/letsencrypt/live') / DOMAIN
REPORT = ROOT / 'shared/logs/domain-migration-20261029-server.json'
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
BACKUP = ROOT / 'shared/backups' / ('domain-migration-20261029-' + STAMP)
HEADER = '# Managed AgriScan domain: ' + DOMAIN + '\n'


class MigrationError(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise MigrationError(message)


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def command(args, timeout=30):
    result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
    return {'exit_code': result.returncode, 'stdout': result.stdout.strip(), 'stderr': result.stderr.strip()}


def checked(args, timeout=30):
    result = command(args, timeout)
    require(result['exit_code'] == 0, 'Command failed: ' + args[0])
    return result


def atomic_write(target, data, mode=0o644, uid=None, gid=None):
    temporary = target.with_name(target.name + '.agriscan-domain-' + uuid4().hex + '.next')
    try:
        with temporary.open('xb') as output:
            output.write(data)
        temporary.chmod(mode)
        if uid is not None:
            os.chown(temporary, uid, gid)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def save(report):
    atomic_write(REPORT, json.dumps(report, ensure_ascii=False, indent=2).encode(), 0o600)


def nginx_reload():
    result = command(['nginx', '-t'])
    require(result['exit_code'] == 0, 'Nginx validation failed; inspect the saved diagnostic.')
    checked(['systemctl', 'reload', 'nginx'])
    # systemctl returns after HUP; new workers may still be loading certificates.
    time.sleep(0.5)
    return result


def http(url, method='GET', headers=()):
    with TemporaryDirectory(prefix='agriscan-domain-check-') as folder:
        body = Path(folder) / 'body'
        header_file = Path(folder) / 'headers'
        args = ['curl', '--silent', '--show-error', '--noproxy', '*', '--connect-timeout', '10',
                '--max-time', '30', '--request', method, '--output', str(body), '--dump-header', str(header_file),
                '--write-out', '%{http_code}\n%{remote_ip}\n%{ssl_verify_result}', url]
        for header in headers:
            args.extend(['--header', header])
        result = command(args, timeout=35)
        values = result['stdout'].splitlines()
        selected = {}
        if header_file.exists():
            for line in header_file.read_text(errors='replace').splitlines():
                key, separator, value = line.partition(':')
                if separator and key.lower() in {'location', 'content-type', 'server', 'access-control-allow-origin'}:
                    selected[key.lower()] = value.strip()
        raw = body.read_bytes() if body.exists() else b''
        data = {'url': url, 'method': method, 'exit_code': result['exit_code'],
                'status': int(values[0]) if values and values[0].isdigit() else 0,
                'remote_ip': values[1] if len(values) > 1 else None,
                'ssl_verify_result': values[2] if len(values) > 2 else None,
                'headers': selected, 'body_bytes': len(raw), 'body_sha256': hashlib.sha256(raw).hexdigest(),
                'error': result['stderr']}
        return data, raw


def health():
    result, raw = http('http://127.0.0.1:18000/api/health')
    require(result['status'] == 200, 'Local API health failed.')
    value = json.loads(raw)
    require(value == {'status': 'ok', 'database': 'connected', 'redis': 'connected',
                      'mode': 'production', 'model': 'ready'}, 'Production API is degraded.')
    return value


def service():
    result = checked(['systemctl', 'show', 'agriscan-api',
                      '--property=MainPID,NRestarts,ActiveState,SubState'])
    return dict(line.split('=', 1) for line in result['stdout'].splitlines() if '=' in line)


def non_cors_hash(raw):
    return hashlib.sha256(b''.join(line for line in raw.splitlines(keepends=True)
                                   if not line.startswith(b'CORS_ORIGINS='))).hexdigest()


def cors_origins(raw):
    lines = [line for line in raw.decode().splitlines() if line.startswith('CORS_ORIGINS=')]
    require(len(lines) == 1, 'Expected exactly one CORS_ORIGINS entry.')
    return [item.strip() for item in lines[0].partition('=')[2].strip().strip('\"\'').split(',') if item.strip()]


def http_server(final=False):
    fallback = 'return 301 https://$host$request_uri;' if final else 'return 503;'
    return HEADER + f'''server {{
    listen 80;
    listen [::]:80;
    server_name {DOMAIN};
    access_log /var/log/nginx/agriscan.access.log;
    error_log /var/log/nginx/agriscan.error.log warn;
    location ^~ /.well-known/acme-challenge/ {{
        root {WEBROOT};
        default_type text/plain;
        try_files $uri =404;
    }}
    location / {{ {fallback} }}
}}
'''


def final_config():
    return http_server(final=True) + f'''
server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name {DOMAIN};
    ssl_certificate {CERT}/fullchain.pem;
    ssl_certificate_key {CERT}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    access_log /var/log/nginx/agriscan.access.log;
    error_log /var/log/nginx/agriscan.error.log warn;
    include /etc/nginx/agriscan-locations.inc;
    location = / {{ return 302 /agriscan/; }}
    location / {{ return 404; }}
}}
'''


def main():
    require(os.geteuid() == 0, 'Run this owned migration as root.')
    require(INCLUDE.is_file() and ENV.is_file() and WEBROOT.is_dir(), 'Required existing AgriScan paths are missing.')
    if VHOST.exists():
        require(VHOST.read_text().startswith(HEADER), 'Existing unrelated agriscan.conf preserved; migration refused.')
    report = {'domain': DOMAIN, 'expected_ip': EXPECTED_IP, 'started_at': datetime.now(timezone.utc).isoformat(),
              'certificate_verification_disabled': False, 'backup': str(BACKUP), 'changes': [], 'stage': 'preflight'}
    old_vhost = VHOST.read_bytes() if VHOST.exists() else None
    old_env = ENV.read_bytes()
    env_stat = ENV.stat()
    before_flowly = digest(FLOWLY)
    before_include = digest(INCLUDE)
    report['preserved_before'] = {'flowly_config_sha256': before_flowly, 'agriscan_include_sha256': before_include,
                                  'non_cors_environment_sha256': non_cors_hash(old_env)}
    report['cors_before'] = cors_origins(old_env)
    report['service_before'] = service()
    report['health_before'] = health()
    old_root, _ = http('https://flowly-ai.top/')
    require(old_root['status'] == 200, 'Old Flowly root was not healthy before migration.')
    report['old_flowly_root_before'] = old_root
    model = ROOT / 'current/model/model.onnx'
    report['model_sha256_before'] = digest(model)
    config_before, raw = http('http://127.0.0.1:18000/api/client/config')
    report['client_config_before'] = {'status': config_before['status'], 'sha256': config_before['body_sha256'],
                                      'version': json.loads(raw)['version']}
    public_dns = checked(['dig', '+time=3', '+tries=1', '+short', DOMAIN, 'A'])
    require(set(public_dns['stdout'].splitlines()) == {EXPECTED_IP}, 'Public DNS A does not point exclusively to the AgriScan server.')
    report['dns_public_a'] = public_dns['stdout'].splitlines()
    ns = checked(['dig', '+time=3', '+tries=1', '+short', 'ming-ai.top', 'NS'])
    report['dns_authoritative'] = []
    for server in ns['stdout'].splitlines()[:2]:
        result = checked(['dig', '+time=3', '+tries=1', '+norecurse', '+noall', '+answer', '+comments', '@' + server, DOMAIN, 'A'])
        require('flags: qr aa;' in result['stdout'] and EXPECTED_IP in result['stdout'], 'Authoritative DNS answer mismatch.')
        report['dns_authoritative'].append({'server': server, 'result': result})
    require(len(report['dns_authoritative']) >= 1, 'No authoritative DNS answer was verified.')
    report['dns_aaaa'] = checked(['dig', '+time=3', '+tries=1', '+short', DOMAIN, 'AAAA'])['stdout'].splitlines()
    require(not report['dns_aaaa'], 'Unexpected AAAA needs validation before HTTP-01 issuance.')
    BACKUP.mkdir(mode=0o700)
    shutil.copy2(ENV, BACKUP / 'production.env')
    (BACKUP / 'production.env').chmod(0o600)
    if old_vhost is not None:
        atomic_write(BACKUP / 'agriscan.conf', old_vhost, 0o600)
    report['previous_vhost_exists'] = old_vhost is not None
    save(report)
    probe = WEBROOT / '.well-known/acme-challenge' / ('agriscan-routing-' + uuid4().hex)
    changed_env_sha = None
    deployed = False
    try:
        report['stage'] = 'http01_routing'
        print('STAGE: verify public HTTP-01 routing', flush=True)
        atomic_write(VHOST, http_server().encode())
        report['nginx_http_validation'] = nginx_reload()
        probe.parent.mkdir(parents=True, exist_ok=True)
        payload = ('AgriScan HTTP01 routing ' + uuid4().hex).encode()
        atomic_write(probe, payload)
        routing, raw = http('http://' + DOMAIN + '/.well-known/acme-challenge/' + probe.name)
        report['http01_public_probe'] = routing
        require(routing['exit_code'] == 0 and routing['status'] == 200 and raw == payload,
                'HTTP-01 public request did not reach the new webroot; inspect DNS, interception and response status.')
        report['stage'] = 'certificate_issue'
        save(report)
        print('STAGE: issue trusted certificate through the existing Certbot webroot', flush=True)
        issue = command(['certbot', 'certonly', '--webroot', '-w', str(WEBROOT), '--cert-name', DOMAIN,
                         '-d', DOMAIN, '--non-interactive', '--agree-tos', '--keep-until-expiring'], timeout=180)
        report['certificate_issue'] = issue
        require(issue['exit_code'] == 0 and (CERT / 'fullchain.pem').is_file(),
                'Certbot HTTP-01 issuance failed; see certificate_issue diagnostic.')
        report['certificate_public_details'] = checked(['openssl', 'x509', '-in', str(CERT / 'fullchain.pem'),
            '-noout', '-subject', '-issuer', '-dates', '-ext', 'subjectAltName'])['stdout']
        report['stage'] = 'https_vhost'
        save(report)
        print('STAGE: activate independent HTTPS virtual host', flush=True)
        atomic_write(VHOST, final_config().encode())
        report['nginx_https_validation'] = nginx_reload()
        report['changes'].append(str(VHOST))
        # Check chain and hostname before touching the API environment.
        report['https_activation_attempts'] = []
        for attempt in range(10):
            first_tls, _ = http('https://' + DOMAIN + '/agriscan/')
            report['https_activation_attempts'].append(first_tls)
            if first_tls['exit_code'] == 0 and first_tls['status'] == 200 and first_tls['ssl_verify_result'] == '0':
                break
            time.sleep(1)
        report['https_first_check'] = first_tls
        require(first_tls['exit_code'] == 0 and first_tls['status'] == 200 and first_tls['ssl_verify_result'] == '0',
                'The new website did not pass normal-DNS TLS validation.')
        report['stage'] = 'cors'
        origins = list(report['cors_before'])
        if 'https://' + DOMAIN not in origins:
            origins.append('https://' + DOMAIN)
            require(ENV.read_bytes() == old_env, 'Production environment changed concurrently; no overwrite was attempted.')
            lines = old_env.splitlines(keepends=True)
            replacement = ('CORS_ORIGINS=' + ','.join(origins) + '\n').encode()
            updated = b''.join(replacement if line.startswith(b'CORS_ORIGINS=') else line for line in lines)
            require(non_cors_hash(updated) == non_cors_hash(old_env), 'Unexpected non-CORS environment edit.')
            atomic_write(ENV, updated, env_stat.st_mode & 0o777, env_stat.st_uid, env_stat.st_gid)
            changed_env_sha = digest(ENV)
            checked(['systemctl', 'restart', 'agriscan-api'], timeout=45)
            report['changes'].append(str(ENV) + ':CORS_ORIGINS')
            for attempt in range(30):
                try:
                    report['health_after'] = health()
                    break
                except Exception:
                    time.sleep(1)
            else:
                raise MigrationError('API did not recover after its CORS environment restart.')
        else:
            report['health_after'] = health()
        report['cors_after'] = cors_origins(ENV.read_bytes())
        require(set(report['cors_before']).issubset(report['cors_after']), 'An original CORS origin was removed.')
        report['stage'] = 'verification'
        report['normal_dns_requests'] = []
        for path, expected in [('/', 301), ('/agriscan/', 301)]:
            result, _ = http('http://' + DOMAIN + path)
            require(result['status'] == expected and result['headers'].get('location') == 'https://' + DOMAIN + path,
                    'HTTP did not redirect to the same HTTPS domain/path.')
            report['normal_dns_requests'].append(result)
        for path, expected in [('/', 302), ('/agriscan/', 200), ('/agriscan/workspace/', 200),
                               ('/agriscan/admin/', 200), ('/agriscan/downloads/release.json', 200),
                               ('/agriscan/api/health', 200), ('/agriscan/api/client/config', 200),
                               ('/agriscan/api/auth/me', 401)]:
            result, _ = http('https://' + DOMAIN + path)
            require(result['status'] == expected and result['exit_code'] == 0 and result['ssl_verify_result'] == '0',
                    'New-domain HTTPS route verification failed: ' + path)
            if path == '/':
                require(result['headers'].get('location') == 'https://' + DOMAIN + '/agriscan/', 'HTTPS root did not 302 to /agriscan/.')
            report['normal_dns_requests'].append(result)
        report['cors_preflights'] = []
        for origin in ['https://' + DOMAIN, 'https://flowly-ai.top', 'capacitor://localhost']:
            result, _ = http('https://' + DOMAIN + '/agriscan/api/detections', method='OPTIONS', headers=[
                'Origin: ' + origin, 'Access-Control-Request-Method: POST',
                'Access-Control-Request-Headers: authorization,content-type'])
            require(result['status'] == 200 and result['headers'].get('access-control-allow-origin') == origin,
                    'A required CORS origin did not pass preflight.')
            report['cors_preflights'].append({'origin': origin, 'result': result})
        report['service_after'] = service()
        report['model_sha256_after'] = digest(model)
        require(report['model_sha256_after'] == report['model_sha256_before'], 'Model artifact changed unexpectedly.')
        report['preserved_after'] = {'flowly_config_sha256': digest(FLOWLY), 'agriscan_include_sha256': digest(INCLUDE),
                                     'non_cors_environment_sha256': non_cors_hash(ENV.read_bytes())}
        require(report['preserved_after'] == report['preserved_before'], 'An out-of-scope file changed.')
        after_root, _ = http('https://flowly-ai.top/')
        report['old_flowly_root_after'] = after_root
        require(after_root['status'] == 200 and after_root['body_sha256'] == old_root['body_sha256'], 'Existing Flowly root changed.')
        config_after, raw = http('http://127.0.0.1:18000/api/client/config')
        report['client_config_after'] = {'status': config_after['status'], 'sha256': config_after['body_sha256'],
                                         'version': json.loads(raw)['version']}
        require(report['client_config_after'] == report['client_config_before'], 'Runtime configuration changed during the migration.')
        deployed = True
        report['stage'] = 'renewal_test'
        save(report)
        print('STAGE: verify the existing renewal timer and a staging renewal', flush=True)
        report['renewal_timer_enabled'] = checked(['systemctl', 'is-enabled', 'certbot-renew.timer'])['stdout']
        report['certificate_renewal_dry_run'] = command(['certbot', 'renew', '--cert-name', DOMAIN,
            '--dry-run', '--non-interactive', '--no-random-sleep-on-renew'], timeout=180)
        report['renewal_unit'] = checked(['systemctl', 'cat', 'certbot-renew.service'])['stdout']
        require('certbot renew' in report['renewal_unit'] and 'systemctl reload nginx' in report['renewal_unit'],
                'Existing renewal service lacks the expected renewal/reload hook.')
        report['status'] = 'passed' if report['certificate_renewal_dry_run']['exit_code'] == 0 else 'deployed_renewal_test_failed'
        report['stage'] = 'complete'
    except Exception as error:
        report['status'] = 'failed'
        report['failure_type'] = type(error).__name__
        report['failure'] = str(error) if isinstance(error, MigrationError) else 'Unexpected runtime error; see server diagnostics.'
        if not deployed:
            if old_vhost is None:
                if VHOST.exists() and VHOST.read_text().startswith(HEADER):
                    VHOST.unlink()
            else:
                atomic_write(VHOST, old_vhost)
            if changed_env_sha is not None and digest(ENV) == changed_env_sha:
                atomic_write(ENV, old_env, env_stat.st_mode & 0o777, env_stat.st_uid, env_stat.st_gid)
                command(['systemctl', 'restart', 'agriscan-api'], timeout=45)
            report['rollback_nginx_validation'] = command(['nginx', '-t'])
            if report['rollback_nginx_validation']['exit_code'] == 0:
                report['rollback_nginx_reload'] = command(['systemctl', 'reload', 'nginx'])
    finally:
        probe.unlink(missing_ok=True)
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        save(report)
    print(json.dumps({'status': report['status'], 'stage': report['stage'], 'report': str(REPORT),
                      'backup': str(BACKUP), 'failure': report.get('failure'),
                      'certificate_public_details': report.get('certificate_public_details'),
                      'service_after': report.get('service_after'), 'cors_after': report.get('cors_after')}, indent=2))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
