from pathlib import Path
from zipfile import ZipFile
import hashlib,json,re
from docx import Document
from pypdf import PdfReader

root=Path('E:/AgriScan');build=root/'.runtime/defense-ppt-build'
docx=root/'deliverables/defense/禾观AgriScan_课程答辩题库_48题含参考回答.docx'
pptx=root/'deliverables/defense/禾观AgriScan_课程答辩_图片终版24页.pptx'
d=Document(docx)
questions=[p.text for p in d.paragraphs if p.style.name=='Question']
assert len(questions)==48
assert [int(re.match(r'Q(\d+)',t).group(1)) for t in questions]==list(range(1,49))
text='\n'.join(p.text for p in d.paragraphs)
for label in ['参考回答','可能追问','追问回答','表达边界']:
    assert len([p for p in d.paragraphs if p.text.startswith(label+'  ')])==48,label
reader=PdfReader(build/'question-bank-native.pdf')
assert len(reader.pages)==23
plan=json.loads((build/'question-bank-page-plan.json').read_text(encoding='utf8'))
for i,pg in enumerate(plan['pages'],2):
    page_text=reader.pages[i].extract_text()
    assert [int(v) for v in re.findall(r'Q(\d{2})',page_text)]==pg['questions'],(i+1,pg)
    assert page_text.count('参考回答')==len(pg['questions'])
    assert page_text.count('追问回答')==len(pg['questions'])
assert not any('\ufffd' in page.extract_text() for page in reader.pages)
files=[]
for p in [pptx,docx]:
    with ZipFile(p) as z: assert z.testzip() is None
    files.append({'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
report={'files':files,'pptSlides':24,'pptOriginalImagesBytesPreserved':24,'wordPages':23,'questions':48,'followups':48,'wordQuestionsHaveCompleteSamePageAnswers':True,'wordRenderer':'Microsoft Word PDF export and packaged render_docx rasterize pipeline','visualQA':'All 23 Word pages inspected; unchanged pages pixel-identical after last wording revision; slide visual QA split 01-12 and 13-24.'}
(build/'final-deliverable-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'pptSlides':24,'wordPages':23,'questions':48,'followups':48,'samePageAnswers':True,'validPackages':2}))
