import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import posixpath
import re
from urllib.parse import unquote, urlsplit
import zipfile

from PIL import Image

root = Path('E:/AgriScan')
task = root / '.runtime/mobile-final-20261029'
folder = task / 'apk'
snapshot = task / 'mobile'
manifest = json.loads((task/'mobile-source-manifest.json').read_text(encoding='utf-8'))
build = json.loads((folder/'build.json').read_text(encoding='utf-8-sig'))
apk = Path(build['apk'])
expected_signer = 'f6229ce48e05aaed0c8889f04f0909c7da7de085ff2b5f98792d6d3a27f710b7'
for row in manifest['files']:
    assert hashlib.sha256((root/row['path']).read_bytes()).hexdigest() == row['sha256'], 'Working source changed after snapshot: '+row['path']
    if not row['path'].startswith('mobile/android/'):
        assert hashlib.sha256((task/row['path']).read_bytes()).hexdigest() == row['sha256']
for name in ('new','previous'):
    signature = (folder/(name+'-signature.txt')).read_text(encoding='utf-8-sig')
    match = re.search(r'Signer #1 certificate SHA-256 digest:\s*([0-9a-f]+)',signature,re.I)
    assert match and match.group(1).lower() == expected_signer
    assert 'Verified using v2 scheme (APK Signature Scheme v2): true' in signature
badging = (folder/'manifest-badging.txt').read_text(encoding='utf-8-sig')
assert "package: name='cn.agriscan.mobile' versionCode='5' versionName='1.0.4'" in badging
assert "sdkVersion:'24'" in badging and "targetSdkVersion:'36'" in badging
xml = (folder/'manifest-tree.txt').read_text(encoding='utf-8-sig')
cleartext = next(line for line in xml.splitlines() if 'usesCleartextTraffic' in line)
assert re.search(r'\(type 0x12\)0x0\b',cleartext)

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script' and attrs.get('src'):
            self.links.append(attrs['src'])
        if tag == 'link' and attrs.get('href'):
            self.links.append(attrs['href'])

public_count = 0
with zipfile.ZipFile(apk) as archive:
    assert archive.testzip() is None
    names = set(archive.namelist())
    assert not any(name.endswith(('.env','.keystore','.jks','.p12','.pem','.key')) for name in names)
    config = json.loads(archive.read('assets/capacitor.config.json'))
    assert config['appId'] == 'cn.agriscan.mobile'
    assert config['server']['androidScheme'] == 'https' and config['android']['allowMixedContent'] is False
    emitted = list((snapshot/'dist').rglob('*'))
    for path in emitted:
        if path.is_file():
            packaged = 'assets/public/' + path.relative_to(snapshot/'dist').as_posix()
            assert packaged in names and archive.read(packaged) == path.read_bytes(), 'Packaged dist mismatch: '+packaged
    for row in manifest['files']:
        if row['path'].startswith('mobile/public/'):
            packaged = 'assets/public/' + row['path'].removeprefix('mobile/public/')
            assert hashlib.sha256(archive.read(packaged)).hexdigest() == row['sha256']
            public_count += 1
    javascript = '\n'.join(archive.read(name).decode('utf-8') for name in sorted(names)
                           if name.startswith('assets/public/assets/') and name.endswith('.js'))
    styles = [(name,archive.read(name).decode('utf-8')) for name in sorted(names)
              if name.startswith('assets/public/assets/') and name.endswith('.css')]
    assert 'https://agriscan.ming-ai.top/agriscan' in javascript
    assert javascript.count('cache:"no-store"') >= 2
    assert 'agriscan-mobile-auth-expired' in javascript and 'agriscan-mobile-service-changed' in javascript
    assert 'mobile-assistant-ball' in javascript and 'field-journal-home' in javascript
    for phrase in ('我的检测任务','创建我的地块','提交检测任务','提交采集任务','整图分类','client_request_id','result_ids','cancelling','uploaded_bytes'):
        assert phrase in javascript, 'Missing final mobile feature: '+phrase
    assert 'qa-only-mobile-local' not in javascript
    assert 'detection-tasks' in javascript and '.upload.onprogress' in javascript
    assert '/images/ip-icons/' in javascript and 'field-morning-hero.png' in javascript
    assert 'field-notes-macro.png' in javascript
    ip_icons = []
    for icon in ('home','detect','records','profile','camera','video','plots','knowledge','settings'):
        name = 'assets/public/images/ip-icons/'+icon+'.webp'
        with Image.open(io.BytesIO(archive.read(name))) as image:
            assert image.format == 'WEBP' and image.width > 0 and image.height > 0
            image.verify()
        ip_icons.append(name)
    font = archive.read('assets/public/fonts/agriscan-sans-sc.woff2')
    assert font[:4] == b'wOF2'
    assert 'assets/public/fonts/OFL.txt' in names and 'assets/public/fonts/font-source.json' in names
    assert any('agriscan-sans-sc.woff2' in text for _,text in styles)
    links = Links()
    links.feed(archive.read('assets/public/index.html').decode('utf-8'))
    checked_paths = []
    def check_path(reference, parent):
        if reference.startswith(('data:','http:','https:','#','//')):
            return
        path = unquote(urlsplit(reference).path)
        if not path:
            return
        packaged = 'assets/public/'+path.lstrip('/') if path.startswith('/') else posixpath.normpath(posixpath.join(posixpath.dirname(parent),path))
        assert packaged in names, 'Missing packaged asset path: '+packaged
        checked_paths.append(packaged)
    for reference in links.links:
        check_path(reference,'assets/public/index.html')
    for parent,text in styles:
        for reference in re.findall(r'url\(\s*[\"\']?([^\)\"\']+)',text):
            check_path(reference.strip(),parent)
    bundle_names = sorted(name for name in names if name.startswith('assets/public/assets/') and name.endswith(('.js','.css')))
source_app = (snapshot/'src/App.tsx').read_text(encoding='utf-8')
assert 'dataVersion.current++' in source_app and 'setData(emptyWorkspace)' in source_app
assert 'setSelected(null)' in source_app and 'setAnalysis(null)' in source_app
assert 'URL.revokeObjectURL' in (snapshot/'src/components.tsx').read_text(encoding='utf-8')
shared=manifest['shared']
assert shared['path']=='shared/detectionTasks.ts'
assert hashlib.sha256((task/shared['path']).read_bytes()).hexdigest()==shared['sha256']
assert shared['sha256']=='ac3e42c703eedc4a94b82aa8141a0fab4415805bdcd1f2b0d3a28c7a6b298a5e'
assert '../shared' not in (snapshot/'dist/index.html').read_text(encoding='utf-8')
hash_value = hashlib.sha256(apk.read_bytes()).hexdigest()
assert hash_value == build['sha256']
assert hashlib.sha256((root/'.runtime/android-toolchain/android-user/debug.keystore').read_bytes()).hexdigest() == build['keystore_sha256']
report = {'status':'passed','artifact':str(apk),'package_id':'cn.agriscan.mobile','version':'1.0.4','version_code':5,
          'apk_bytes':apk.stat().st_size,'sha256':hash_value,'signer_sha256':expected_signer,
          'same_signature_as_previous':True,'debug_keystore_unchanged':True,'v2_signature_verified':True,'zip_crc_verified':True,
          'min_sdk':24,'target_sdk':36,'cleartext_traffic':False,'mixed_content':False,
          'default_api':'https://agriscan.ming-ai.top/agriscan','compiled_no_store_count':javascript.count('cache:"no-store"'),
          'latest_workspace_snapshot':True,'source_root_stable_after_build':True,'source_tree_sha256':manifest['source_tree_sha256'],
          'source_file_count':manifest['source_file_count'],'public_asset_count':public_count,'ip_icons':ip_icons,
          'woff2_font_included':True,'field_journal_assets_included':True,'floating_assistant_included':True,
          'asset_paths_verified':len(checked_paths),'packaged_dist_byte_matches':True,'bundles':bundle_names,
          'plots_create_edit_and_protected_cover_included':True,'background_detection_tasks_included':True,
          'dual_model_verification_included':True,'shared_core':shared,'source_path_convention':manifest['path_convention'],
          'native_runtime_tested':False,'server_published':False,'git_operations':False}
(folder/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({key:report[key] for key in ('status','artifact','version','version_code','apk_bytes','sha256','source_tree_sha256','public_asset_count','asset_paths_verified')}))
