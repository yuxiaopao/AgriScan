from pathlib import Path
from zipfile import ZipFile
import json,hashlib,posixpath
from lxml import etree as ET

root=Path('E:/AgriScan')
build=root/'.runtime/defense-ppt-build/speech-current';build.mkdir(parents=True,exist_ok=True)
source=root/'deliverables/defense/禾观AgriScan_课程答辩_团队照片姓名版.pptx'
ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
def resolve(base,t):return posixpath.normpath(posixpath.join(posixpath.dirname(base),t)).lstrip('/')
def rels(z,base):
    q=posixpath.join(posixpath.dirname(base),'_rels',posixpath.basename(base)+'.rels')
    return {x.get('Id'):x.get('Target') for x in ET.fromstring(z.read(q))}
mapping=json.loads((root/'.runtime/defense-ppt-build/image-ppt-final/source-order.json').read_text(encoding='utf8'))
bysha={m['sha256']:m['file'] for m in mapping}
pages=[]
with ZipFile(source) as z:
    pr=rels(z,'ppt/presentation.xml')
    pres=ET.fromstring(z.read('ppt/presentation.xml'))
    for i,node in enumerate(pres.xpath('//p:sldId',namespaces=ns),1):
        part=resolve('ppt/presentation.xml',pr[node.get('{'+ns['r']+'}id')]);sr=rels(z,part)
        slide=ET.fromstring(z.read(part));pictures=[]
        for j,blip in enumerate(slide.xpath('//a:blip',namespaces=ns)):
            im=resolve(part,sr[blip.get('{'+ns['r']+'}embed')]);b=z.read(im);sha=hashlib.sha256(b).hexdigest()
            name=f'slide-{i:02}-{j+1}{Path(im).suffix}'
            (build/name).write_bytes(b)
            pictures.append({'path':str(build/name),'sha256':sha,'sourceMatch':bysha.get(sha),'media':im})
        notes=[]
        for rid,t in sr.items():
            if 'notesSlides/' in t:
                n=ET.fromstring(z.read(resolve(part,t)));notes+=n.xpath('//a:t/text()',namespaces=ns)
        pages.append({'slide':i,'part':part,'texts':slide.xpath('//a:t/text()',namespaces=ns),'images':pictures,'notes':notes})
report={'source':str(source),'sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'slideCount':len(pages),'pages':pages}
(build/'source-extraction.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'slideCount':len(pages),'slides':[{'slide':p['slide'],'texts':p['texts'],'imageMatches':[m['sourceMatch'] for m in p['images']]} for p in pages]},ensure_ascii=False))
