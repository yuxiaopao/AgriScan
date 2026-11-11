"""Inventory the latest working UI; stage only the requested static website."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import struct
from urllib.parse import unquote, urlsplit

root=Path.cwd()
report_root=root/'.runtime/server-latest-20261029'
source_files=[]
for surface in ['frontend','admin']:
    source_files.extend(path for path in (root/surface/'src').rglob('*') if path.is_file())
    source_files.extend(path for path in (root/surface).glob('*') if path.is_file() and
                        (path.name in {'index.html','package.json','package-lock.json','vite.config.ts'} or
                         path.name.startswith('tsconfig') and path.suffix=='.json'))
source_files.extend(path for path in (root/'frontend/public').rglob('*') if path.is_file())
source_files.extend(root/'website'/name for name in ['index.html','app.js','style.css'])
source_files.extend(path for path in (root/'website/site-assets').rglob('*') if path.is_file())
source_files=sorted(set(source_files))

def entry(path):
    data=path.read_bytes()
    return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}

snapshot={str(path.relative_to(root)).replace('\\','/'):entry(path) for path in source_files}
for name in snapshot:
    if any(part in {'deliverables','datasets','.runtime','.chart-data','balanced-options','simple-options','meaningful-options','typographic-options','__pycache__','uploads'} for part in Path(name).parts):
        raise RuntimeError('Unexpected non-public source path in release: '+name)
    if Path(name).name.startswith('.env') or Path(name).suffix in {'.pptx','.pt','.onnx','.xlsx','.pyc','.pem','.key'}:
        raise RuntimeError('Unexpected artifact in web release: '+name)
    if Path(name).suffix in {'.ts','.tsx','.js','.html','.css','.json'}:
        content=(root/name).read_text(encoding='utf-8')
        if re.search(r'\bsk-[A-Za-z0-9]{20,}\b',content):
            raise RuntimeError('Unexpected secret-like value in public source: '+name)

class Page(HTMLParser):
    def __init__(self):
        super().__init__();self.links=[];self.ids=set()
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if 'id' in attrs:self.ids.add(attrs['id'])
        for key in ['src','href']:
            if attrs.get(key):self.links.append((tag,key,attrs[key]))

page=Page();page.feed((root/'website/index.html').read_text(encoding='utf-8'))
missing=[];virtual=[];local=[]
for tag,key,url in page.links:
    parsed=urlsplit(url)
    if parsed.scheme or parsed.netloc:continue
    if not parsed.path:
        if parsed.fragment and parsed.fragment not in page.ids:missing.append(url)
        continue
    if parsed.path.startswith('./workspace/') or parsed.path.startswith('./admin/'):
        virtual.append(url);continue
    target=root/'website'/unquote(parsed.path)
    if parsed.path=='./':continue
    if not target.is_file():missing.append(url)
    else:local.append(url)
if missing:raise RuntimeError('Missing website asset/anchor references: '+json.dumps(missing))
for group,base in [('frontend',root/'frontend/public'),('mobile',root/'mobile/public')]:
    for path in (root/group/'src').rglob('*'):
        if path.suffix not in {'.css','.tsx','.ts'}:continue
        text=path.read_text(encoding='utf-8')
        for value in re.findall(r'''["'](/(?:images|brand|fonts)/[^"'`\s${}]+)["']''',text):
            if not (base/value.lstrip('/')).exists():missing.append(group+':'+value)
if missing:raise RuntimeError('Missing public source assets: '+json.dumps(sorted(set(missing))))

mobile_assets={}
for folder in ['mobile/public/fonts','mobile/public/images/ip-icons']:
    for path in sorted((root/folder).rglob('*')):
        if not path.is_file():continue
        data=path.read_bytes()
        if path.suffix=='.png':
            if data[:8]!=b'\x89PNG\r\n\x1a\n' or len(data)<24:raise RuntimeError('Invalid PNG asset: '+str(path))
            width,height=struct.unpack('>II',data[16:24])
            if not width or not height:raise RuntimeError('Empty PNG dimensions: '+str(path))
        if path.suffix=='.woff2' and data[:4]!=b'wOF2':raise RuntimeError('Invalid WOFF2 asset: '+str(path))
        mobile_assets[str(path.relative_to(root)).replace('\\','/')]=entry(path)

website_stage=report_root/'website'
website_stage.mkdir(parents=True,exist_ok=True)
for name in ['index.html','app.js','style.css']:
    shutil.copy2(root/'website'/name,website_stage/name)
for path in (root/'website/site-assets').rglob('*'):
    if not path.is_file():continue
    target=website_stage/path.relative_to(root/'website')
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)

report={'status':'passed','source':'current working tree, including completed UI modules and polish styles',
        'source_files':snapshot,'source_file_count':len(snapshot),
        'website_stage':str(website_stage),'website_local_assets':local,'website_virtual_app_links':virtual,
        'website_downloads_excluded':'Preserve/publish APK and release.json separately; not overwritten by static website staging.',
        'mobile_font_ip_assets':mobile_assets,'missing_assets':[],
        'production_parameters':{'VITE_WEB_BASE':'/agriscan/workspace/','VITE_ADMIN_BASE':'/agriscan/admin/',
                                 'VITE_API_PREFIX':'/agriscan','VITE_WORKSPACE_URL':'/agriscan/workspace/#login','VITE_ADMIN_URL':'/agriscan/admin/'}}
(report_root/'web-source-before.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'source_files':len(snapshot),'mobile_font_ip_assets':len(mobile_assets),
                  'website_stage':str(website_stage),'missing_assets':0}))
