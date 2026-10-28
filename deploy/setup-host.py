"""Initialize a dedicated AgriScan runtime; retain existing sites and credentials."""
import base64
import os
from pathlib import Path
import pwd
import secrets
import subprocess

ROOT = Path('/srv/agriscan')
SHARED = ROOT / 'shared'
ENV = SHARED / 'production.env'


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


if os.geteuid() != 0:
    raise SystemExit('Run the host setup as root.')
try:
    pwd.getpwnam('agriscan')
except KeyError:
    run('useradd', '--system', '--home-dir', str(ROOT), '--shell', '/sbin/nologin', 'agriscan')
for folder in (ROOT, ROOT / 'releases', SHARED, SHARED / 'uploads', SHARED / 'logs', SHARED / 'backups'):
    folder.mkdir(parents=True, exist_ok=True)
run('chown', 'root:agriscan', str(SHARED), str(SHARED / 'backups'))
for folder in (SHARED / 'uploads', SHARED / 'logs'):
    run('chown', 'agriscan:agriscan', str(folder))
    folder.chmod(0o750)
SHARED.chmod(0o750)
if not ENV.exists():
    database_password = secrets.token_urlsafe(30)
    redis_password = secrets.token_urlsafe(30)
    values = {
        'DATABASE_URL': f'mysql+pymysql://agriscan:{database_password}@127.0.0.1:3306/agriscan?charset=utf8mb4',
        'REDIS_URL': f'redis://:{redis_password}@127.0.0.1:16380/0',
        'UPLOAD_DIR': str(SHARED / 'uploads'), 'DEMO_MODE': 'false',
        'JWT_SECRET': secrets.token_urlsafe(48), 'ADMIN_USERNAME': 'admin',
        'ADMIN_PASSWORD': secrets.token_urlsafe(24),
        'CORS_ORIGINS': 'https://flowly-ai.top,https://www.flowly-ai.top,https://localhost,http://localhost,capacitor://localhost',
        'CONFIG_ENCRYPTION_KEY': base64.urlsafe_b64encode(os.urandom(32)).decode(),
        'REGISTRATION_ENABLED': 'true', 'EMAIL_VERIFICATION_ENABLED': 'false',
        'LLM_ENABLED': 'false', 'LLM_BASE_URL': 'https://api.openai.com/v1', 'LLM_API_KEY': '',
        'LLM_MODEL': '', 'LLM_TIMEOUT': '60', 'MODEL_MAX_UPLOAD_MB': '200',
        'MODEL_MANIFEST': '/srv/agriscan/current/model/manifest.json', 'INFERENCE_THREADS': '2',
    }
    ENV.write_text(''.join(f'{key}={value}\n' for key, value in values.items()), encoding='utf8')
    ENV.chmod(0o640)
    run('chown', 'root:agriscan', str(ENV))
else:
    values = dict(line.split('=', 1) for line in ENV.read_text().splitlines() if line and not line.startswith('#'))
    from urllib.parse import urlsplit, unquote
    database_password = unquote(urlsplit(values['DATABASE_URL']).password)
    redis_password = unquote(urlsplit(values['REDIS_URL']).password)
ENV.chmod(0o640)
run('chown', 'root:agriscan', str(ENV))

mysql_config = Path('/etc/my.cnf.d/agriscan.cnf')
if not mysql_config.exists():
    mysql_config.write_text('[mysqld]\nbind-address=127.0.0.1\ninnodb_buffer_pool_size=128M\nmax_connections=30\nperformance_schema=OFF\ncharacter-set-server=utf8mb4\n', encoding='ascii')
run('systemctl', 'enable', '--now', 'mysqld')
sql = ("CREATE DATABASE IF NOT EXISTS agriscan CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
       f"CREATE USER IF NOT EXISTS 'agriscan'@'127.0.0.1' IDENTIFIED BY '{database_password}';\n"
       "GRANT ALL PRIVILEGES ON agriscan.* TO 'agriscan'@'127.0.0.1';\n")
run('mysql', '--protocol=socket', '--user=root', input=sql.encode(), stdout=subprocess.DEVNULL)
root_client = Path('/root/.my.cnf')
empty_root = subprocess.run(['mysql', '--protocol=socket', '--user=root', '-N', '-e',
    "SELECT COUNT(*) FROM mysql.user WHERE user='root' AND host='localhost' AND plugin='caching_sha2_password' AND authentication_string=''"],
    check=True, capture_output=True, text=True).stdout.strip() == '1'
if empty_root and not root_client.exists():
    root_password = secrets.token_urlsafe(36)
    pending = Path('/root/.agriscan-mysql-client.next')
    pending.write_text('[client]\nuser=root\nprotocol=socket\npassword=' + root_password + '\n', encoding='ascii')
    pending.chmod(0o600)
    try:
        run('mysql', '--protocol=socket', '--user=root',
            input=("ALTER USER 'root'@'localhost' IDENTIFIED BY '" + root_password + "';\n").encode(), stdout=subprocess.DEVNULL)
        os.replace(pending, root_client)
    except BaseException:
        pending.unlink(missing_ok=True)
        raise

redis_root = Path('/etc/agriscan')
redis_root.mkdir(exist_ok=True)
redis_data = Path('/var/lib/agriscan-redis')
redis_data.mkdir(exist_ok=True)
run('chown', 'redis:redis', str(redis_data))
redis_config = redis_root / 'redis.conf'
redis_config.write_text(f'bind 127.0.0.1\nport 16380\nprotected-mode yes\nrequirepass {redis_password}\n'
                        f'dir {redis_data}\nsave 900 1\nmaxmemory 64mb\nmaxmemory-policy allkeys-lru\n'
                        'daemonize no\nsupervised systemd\nlogfile ""\n', encoding='ascii')
redis_config.chmod(0o640)
run('chown', 'root:redis', str(redis_config))
Path('/etc/systemd/system/agriscan-redis.service').write_text('''[Unit]
Description=AgriScan isolated Redis cache
After=network.target
[Service]
User=redis
Group=redis
Type=notify
ExecStart=/usr/bin/redis-server /etc/agriscan/redis.conf
Restart=on-failure
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/var/lib/agriscan-redis
[Install]
WantedBy=multi-user.target
''', encoding='ascii')
Path('/etc/systemd/system/agriscan-api.service').write_text('''[Unit]
Description=AgriScan agricultural detection API
After=network.target mysqld.service agriscan-redis.service
Requires=mysqld.service agriscan-redis.service
[Service]
User=agriscan
Group=agriscan
WorkingDirectory=/srv/agriscan/current/backend
EnvironmentFile=/srv/agriscan/shared/production.env
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/srv/agriscan/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18000 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=on-failure
RestartSec=5
TimeoutStartSec=120
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/srv/agriscan/shared
MemoryHigh=1G
MemoryMax=1400M
LimitNOFILE=4096
[Install]
WantedBy=multi-user.target
''', encoding='ascii')
run('systemctl', 'daemon-reload')
run('systemctl', 'enable', '--now', 'agriscan-redis')
if not (ROOT / 'venv' / 'bin' / 'python').exists():
    run('python3', '-m', 'venv', str(ROOT / 'venv'))
print('Dedicated MySQL database, Redis cache, service units and private production configuration ready. Credentials were not printed.')
