import json, hashlib
from pathlib import Path
from PIL import Image

root=Path('E:/AgriScan')
design=root/'design/mobile-field-journal'
names=['home','detect','records','profile','camera','video','plots','knowledge','settings']
labels=['首页','图片检测','观察记录','个人中心与小禾','实时相机','视频检测','地块档案','田间笔记','账户与连接']
records={}
manifests=['ip-icon-prompts-a.json','ip-icon-prompts-b.json','ip-icon-prompts-root.json']
for filename in manifests:
    doc=json.loads((design/filename).read_text(encoding='utf-8'))
    for item in doc.get('assets',doc.get('icons',[])):
        records[item['name']]=item
assets=[]
for name,label in zip(names,labels):
    item=records[name]
    path=root/f'mobile/public/images/ip-icons/{name}.webp'
    with Image.open(path) as image:
        assert image.size==(192,192) and image.mode=='RGBA'
        assert image.getchannel('A').getextrema()==(0,255)
    assets.append({'name':name,'label':label,'path':path.relative_to(root).as_posix(),'size':[192,192],'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'prompt':item['prompt'],'source_copy':item.get('projectSource',item.get('source_path',item.get('source_copy')))})
index={'method':'Built-in image_gen','date':'2026-10-29','reference':'mobile/public/images/xiaohe.png','format':'Transparent RGBA WebP','total_bytes':sum(item['bytes'] for item in assets),'source_manifests':manifests,'assets':assets}
(design/'ip-icons.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Validated',len(assets),'transparent icons;',index['total_bytes'],'bytes total')
