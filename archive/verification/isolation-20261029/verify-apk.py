"""Inspect only the owned snapshot APK and public debug certificate metadata."""
import hashlib
import json
from pathlib import Path
import re
import zipfile

root = Path('E:/AgriScan')
folder = root / '.runtime/isolation-20261029/apk'
build = json.loads((folder / 'build.json').read_text(encoding='utf-8-sig'))
apk = Path(build['apk'])
expected_signer = 'f6229ce48e05aaed0c8889f04f0909c7da7de085ff2b5f98792d6d3a27f710b7'
signatures = {}
for name in ('new', 'previous'):
    text = (folder / (name + '-signature.txt')).read_text(encoding='utf-8-sig')
    found = re.search(r'Signer #1 certificate SHA-256 digest:\s*([0-9a-f]+)', text, re.I)
    assert found and found.group(1).lower() == expected_signer, 'Signing certificate mismatch; artifact must not be published.'
    assert 'Verified using v2 scheme (APK Signature Scheme v2): true' in text
    signatures[name] = found.group(1).lower()
badging = (folder / 'manifest-badging.txt').read_text(encoding='utf-8-sig')
assert "package: name='cn.agriscan.mobile' versionCode='3' versionName='1.0.2'" in badging
assert "sdkVersion:'24'" in badging and "targetSdkVersion:'36'" in badging
manifest = (folder / 'manifest-tree.txt').read_text(encoding='utf-8-sig')
cleartext = next(line for line in manifest.splitlines() if 'usesCleartextTraffic' in line)
assert re.search(r'\(type 0x12\)0x0\b', cleartext), 'Cleartext traffic was not disabled.'

with zipfile.ZipFile(apk) as archive:
    assert archive.testzip() is None
    config = json.loads(archive.read('assets/capacitor.config.json'))
    assert config['appId'] == 'cn.agriscan.mobile'
    assert config['server']['androidScheme'] == 'https'
    assert config['android']['allowMixedContent'] is False
    names = archive.namelist()
    assert not any(name.endswith(('.env', '.keystore', '.jks')) for name in names)
    bundles = [name for name in names if re.fullmatch(r'assets/public/assets/index-[^/]+\.js', name)]
    assert len(bundles) == 1
    javascript = archive.read(bundles[0]).decode('utf-8')
    assert 'https://agriscan.ming-ai.top/agriscan' in javascript
    assert javascript.count('cache:"no-store"') >= 2
    assert 'agriscan-mobile-auth-expired' in javascript
    assert 'agriscan-mobile-service-changed' in javascript
    for emitted in (root / '.runtime/isolation-20261029/build/mobile/dist/assets').glob('*.js'):
        assert archive.read('assets/public/assets/' + emitted.name) == emitted.read_bytes()

source = root / '.runtime/isolation-20261029/build/mobile/src'
app = (source / 'App.tsx').read_text(encoding='utf-8')
components = (source / 'components.tsx').read_text(encoding='utf-8')
api = (source / 'api.ts').read_text(encoding='utf-8')
assert 'dataVersion.current++' in app and 'setData(emptyWorkspace)' in app
assert 'setSelected(null)' in app and 'setAnalysis(null)' in app
assert 'cache: \'no-store\'' in api and 'cache: \'no-store\'' in components
assert 'URL.revokeObjectURL' in components
checksum = hashlib.sha256(apk.read_bytes()).hexdigest()
assert checksum == build['sha256']
keystore = root / '.runtime/android-toolchain/android-user/debug.keystore'
assert hashlib.sha256(keystore.read_bytes()).hexdigest() == build['keystore_sha256']
report = {
    'status': 'passed', 'artifact': str(apk), 'version': '1.0.2', 'version_code': 3,
    'package_id': 'cn.agriscan.mobile', 'apk_bytes': apk.stat().st_size, 'sha256': checksum,
    'signer_sha256': expected_signer, 'previous_signer_matches': signatures['previous'] == signatures['new'],
    'v2_signature_verified': True, 'debug_keystore_unchanged': True, 'zip_crc_verified': True,
    'min_sdk': 24, 'target_sdk': 36, 'cleartext_traffic': False, 'mixed_content': False,
    'compiled_api_base': 'https://agriscan.ming-ai.top/agriscan',
    'compiled_cache_no_store_occurrences': javascript.count('cache:"no-store"'),
    'packaged_javascript_matches_fresh_snapshot_build': True,
    'compiled_bundle': bundles[0], 'source_inputs': build['source_inputs'],
    'snapshot_source_session_reset_checks': True, 'source_blob_revocation_check': True,
    'native_runtime_tested': False, 'server_published': False, 'git_operations': False,
}
(folder / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({key: report[key] for key in ('status', 'artifact', 'version', 'version_code', 'apk_bytes', 'sha256', 'signer_sha256')}))
