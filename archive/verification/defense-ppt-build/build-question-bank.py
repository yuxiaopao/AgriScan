import json, re, math
from pathlib import Path
from datetime import date
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT=Path('E:/AgriScan')
BUILD=ROOT/'.runtime/defense-ppt-build'
OUT=ROOT/'deliverables/defense/禾观AgriScan_课程答辩题库_48题含参考回答.docx'
qa=json.loads((BUILD/'qa-evidence.json').read_text(encoding='utf-8-sig'))+json.loads((BUILD/'qa-product.json').read_text(encoding='utf-8-sig'))
qa=sorted(qa,key=lambda q:q['id'])
assert [q['id'] for q in qa]==list(range(1,49))
for q in qa:
    if q['id']==23:q['answer']=q['answer'].replace('最新回归曾复现','2026年10月28日的回归曾复现')
    if q['id']==37:q['answer']=q['answer'].replace('最新后端回归有','2026年10月28日的后端回归记录有')
    if q['id']==20:q['followup']['answer']=q['followup']['answer'].replace('经过临床或田间校准','经过田间校准')
    if q['id']==9:q['answer']='我们的分工方案是：A负责统筹、后端接口和数据库；B负责数据、模型评测与ONNX；C负责桌面前端、小禾IP和交互；D负责Android、测试与部署。这样能覆盖完整链路，也便于按模块产物说明贡献。每个模块先约定接口和交付内容，再通过一次完整用户流程共同验收。'
    if q['id']==10:q['answer']='建议A负责业务接口、认证、数据库和结果落库，B负责数据划分、模型评测、预处理契约与ONNX产物。模型接入是共同接口：B说明输入尺寸、类别顺序、输出语义和校验值，A按契约实现调用与保存。联调时双方核对原始输出、接口响应和保存记录，区分模型判断与接口适配的问题。'
    if q['id']==12:q['answer']='我们可以用具体产物说明贡献：后端对应接口和数据库变更，模型对应数据与评估报告，桌面端对应页面与IP素材，移动端对应手机工程和验收记录。个人回答应讲清负责范围、解决的问题和协同部分，并与实际提交及过程材料核对。共同完成的环节共同说明，工作量比例只在有记录支持时报告。'
    if q['id']==39:q['answer']='复盘时优先改进模块间的契约与交叉验收：模型端交付输入、类别和分数语义，后端交付明确状态与错误，客户端保留失败后的输入并准确展示。遇到跨模块问题，先形成可复现样例，再比对输入和输出定位根因。讨论以具体产物和验证结果为依据，并把经验补充到接口说明与回归场景中。'
sources=[]
for q in qa:
    for s in q['sources']:
        assert (ROOT/s).exists(),s
        if s not in sources:sources.append(s)
source_ids={s:f'S{i+1:02}' for i,s in enumerate(sources)}
(BUILD/'qa-complete.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')

doc=Document()
sec=doc.sections[0]
sec.page_width=Inches(8.5);sec.page_height=Inches(11)
sec.top_margin=Inches(.72);sec.bottom_margin=Inches(.72)
sec.left_margin=Inches(.82);sec.right_margin=Inches(.82)
sec.header_distance=Inches(.28);sec.footer_distance=Inches(.30)

def style_font(style,size,bold=False,color='000000'):
    style.font.name='Microsoft YaHei';style.font.size=Pt(size);style.font.bold=bold;style.font.italic=False;style.font.underline=False;style.font.color.rgb=RGBColor.from_string(color)
    rpr=style.element.get_or_add_rPr();rfonts=rpr.rFonts
    if rfonts is None:rfonts=OxmlElement('w:rFonts');rpr.insert(0,rfonts)
    for a in ['ascii','hAnsi','eastAsia','cs']:rfonts.set(qn('w:'+a),'Microsoft YaHei')
    for a in ['asciiTheme','hAnsiTheme','eastAsiaTheme','cstheme']:
        rfonts.attrib.pop(qn('w:'+a),None)

for n,sz,b in [('Normal',11,False),('Title',25,True),('Subtitle',12,False),('Heading 1',17,True),('Heading 2',13,True),('Heading 3',11.5,True)]:
    style_font(doc.styles[n],sz,b)
    pf=doc.styles[n].paragraph_format
    pf.space_before=Pt(0 if n in ['Normal','Title','Subtitle'] else 9)
    pf.space_after=Pt(5 if n=='Normal' else 10)
    pf.line_spacing=Pt(16 if n=='Normal' else sz+7)
    snap=OxmlElement('w:snapToGrid');snap.set(qn('w:val'),'0');style_ppr=doc.styles[n].element.get_or_add_pPr();style_ppr.append(snap)
    for p in list(doc.styles[n].element.xpath('./w:pPr/w:pBdr')):p.getparent().remove(p)
for name,size,bold in [('Question',12,True),('Source',8.5,False),('SectionContinuation',17,True)]:
    st=doc.styles.add_style(name,1);st.base_style=doc.styles['Normal'];style_font(st,size,bold,'555555' if name=='Source' else '000000')
    st.paragraph_format.space_before=Pt(10 if name=='Question' else 0)
    st.paragraph_format.space_after=Pt(6 if name=='Question' else 4)
doc.styles['Question'].paragraph_format.keep_with_next=True
doc.styles['Question'].paragraph_format.line_spacing=Pt(18)
doc.styles['Source'].paragraph_format.space_after=Pt(13)
doc.styles['Source'].paragraph_format.line_spacing=Pt(12)
doc.styles['SectionContinuation'].paragraph_format.space_after=Pt(12)
doc.styles['SectionContinuation'].paragraph_format.line_spacing=Pt(24)

def runfont(run,size=None,bold=None):
    run.font.name='Microsoft YaHei'
    rpr=run._element.get_or_add_rPr();rf=rpr.rFonts
    if rf is None:rf=OxmlElement('w:rFonts');rpr.insert(0,rf)
    rf.set(qn('w:eastAsia'),'Microsoft YaHei')
    if size:run.font.size=Pt(size)
    if bold is not None:run.font.bold=bold

def para(text='',style=None,keep=False):
    p=doc.add_paragraph(text,style=style)
    p.paragraph_format.keep_together=True
    p.paragraph_format.keep_with_next=keep
    for r in p.runs:runfont(r)
    return p

def labelled(label,text,keep=True,size=11):
    p=para('',keep=keep);r=p.add_run(label+'  ');runfont(r,size,True);r=p.add_run(text);runfont(r,size,False)
    return p

def page_heading(text,style='Heading 1'):
    p=para(text,style);p.paragraph_format.page_break_before=True
    return p

def table(headers,rows,widths):
    t=doc.add_table(rows=1,cols=len(headers));t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
    for col,w in zip(t.columns,widths):col.width=Inches(w)
    for i,h in enumerate(headers):t.rows[0].cells[i].text=h
    for row in rows:
        cells=t.add_row().cells
        for c,v in zip(cells,row):c.text=str(v)
    for ri,row in enumerate(t.rows):
        for ci,c in enumerate(row.cells):
            c.width=Inches(widths[ci]);c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            pr=c._tc.get_or_add_tcPr()
            sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'243B4A' if ri==0 else ('F2F5F7' if ri%2==0 else 'FFFFFF'));pr.append(sh)
            borders=OxmlElement('w:tcBorders')
            for edge in ['top','left','bottom','right','insideH','insideV']:
                e=OxmlElement('w:'+edge);e.set(qn('w:val'),'single');e.set(qn('w:sz'),'4');e.set(qn('w:color'),'D9D9D9');borders.append(e)
            pr.append(borders)
            mar=OxmlElement('w:tcMar')
            for edge in ['top','left','bottom','right']:
                e=OxmlElement('w:'+edge);e.set(qn('w:w'),'85');e.set(qn('w:type'),'dxa');mar.append(e)
            pr.append(mar)
            for p in c.paragraphs:
                p.paragraph_format.space_before=Pt(0);p.paragraph_format.space_after=Pt(0);p.paragraph_format.line_spacing=1.12
                p.paragraph_format.keep_with_next=False
                if ci==0 and len(headers)>2:p.alignment=WD_ALIGN_PARAGRAPH.CENTER
                for r in p.runs:
                    runfont(r,10,ri==0);r.font.color.rgb=RGBColor.from_string('FFFFFF' if ri==0 else '000000')
        pr=row._tr.get_or_add_trPr();cant=OxmlElement('w:cantSplit');pr.append(cant)
    repeat=OxmlElement('w:tblHeader');t.rows[0]._tr.get_or_add_trPr().append(repeat)
    para('').paragraph_format.space_after=Pt(2)
    return t

footer=sec.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.RIGHT
r=footer.add_run('禾观 AgriScan 课程答辩题库    ');runfont(r,8.5)
r=footer.add_run();fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');r._r.addnext(fld)

para('禾观 AgriScan 课程答辩题库','Title')
para('48 道主问题和 48 道追问参考回答','Subtitle')
para('这份题库用于禾观 AgriScan 课程项目答辩，围绕项目介绍、四人团队、实现过程、结果、课程收获和创新改进展开。参考回答以已完成的分类实验、检测模型接入和三端业务为依据，可用来练习主答与现场追问。')
para('每题先回答结论，再补充一项具体证据。主答建议控制在 40 至 60 秒，追问用 15 至 30 秒展开。个人贡献应替换为本人实际完成的工作，并准备相应模块、提交或演示步骤。')
para('内容导航','Heading 1')
table(['部分','题号','对应 PPT 页'],[
 ['一 项目介绍','Q01 至 Q08','03 至 06'],
 ['二 团队介绍','Q09 至 Q12','07'],
 ['三 实现过程','Q13 至 Q28','08 至 13 及 17'],
 ['四 结果与验证','Q29 至 Q36','14 至 18'],
 ['五 课程收获','Q37 至 Q40','19'],
 ['六 创新与改进方向','Q41 至 Q48','20 至 21'],
], [2.8,1.55,2.5])
para('复习顺序','Heading 1')
para('先练 Q01、Q04、Q05，讲清项目定位与数据。再练 Q13、Q20、Q29、Q33、Q34，区分分类、检测和置信度。最后练 Q09、Q35、Q41、Q48，准备团队贡献、验证证据和改进优先级。')
para('回答结构','Heading 1')
para('每题包含参考回答、可能追问和追问回答。“表达边界”提示容易混淆的指标或尚未实现的功能；资料编号对应文末的项目文件索引，方便答辩前核对。')

page_heading('关键口径速查')
table(['项目','可直接回答的事实'],[
 ['分类数据','PlantVillage 实际整理 54,305 张图像，14 种作物，38 个健康与病害类别。'],
 ['数据划分','训练 37,821 张，验证 5,485 张，独立测试 10,999 张。'],
 ['分类成绩','独立测试 Top-1 为 99.67%，宏平均 F1 为 99.56%，36 张分类错误。'],
 ['分类训练','224×224 输入，batch 32，AdamW，学习率 0.0005，AMP，训练 40 轮，验证选中第 37 轮。'],
 ['检测模型','接入另行提供的 YOLO26m Detect 权重，640×640 输入；尚无独立检测 mAP。'],
 ['一致性校验','分类导出最大绝对差约 2.98×10⁻⁷；检测五图校验用于类别、分数及坐标一致性。'],
 ['演示分数','84.60% 是苹果样例中单目标置信度，不是准确率、患病概率或病斑面积。'],
 ['后端验证','2026 年 10 月 28 日记录为 192 项通过、1 项跳过；该记录有明确时间与范围。'],
 ['IP 与范围','小禾有 17 套界面作物主题；模型支持 14 种作物。当前没有 RAG、病斑分割和病程预测。'],
], [1.2,5.65])
para('四人建议分工','Heading 2')
table(['成员','建议负责内容'],[
 ['成员 A','项目统筹、后端接口、数据库与联调'],
 ['成员 B','数据整理、分类实验、评测与 ONNX 部署'],
 ['成员 C','桌面前端、交互设计与小禾 IP'],
 ['成员 D','Android 端、测试、部署与演示保障'],
], [.9,5.95])
para('以上是四人团队的建议安排。成员姓名和实际贡献尚未提供，正式答辩请按真实完成情况调整。',keep=False)

groups=[
 ('一 项目介绍',[[1,2,3],[4,5,6],[7,8]]),
 ('二 团队介绍',[[9,10],[11,12]]),
 ('三 实现过程',[[13,14,15],[16,17,18],[19,20],[21,22,23],[24,25,26],[27,28]]),
 ('四 结果与验证',[[29,30,31],[32,33,34],[35,36]]),
 ('五 课程收获',[[37,38],[39,40]]),
 ('六 创新与改进方向',[[41,42,43],[44,45,46],[47,48]]),
]
qmap={q['id']:q for q in qa}
page_plan=[]
for title,pages in groups:
    for pi,ids in enumerate(pages):
        page_heading(title if pi==0 else title+' 续', 'Heading 1' if pi==0 else 'SectionContinuation')
        page_plan.append({'section':title,'questions':ids})
        for id in ids:
            q=qmap[id]
            p=para(f"Q{id:02}  {q['question']}",'Question',keep=True)
            mark=OxmlElement('w:bookmarkStart');mark.set(qn('w:id'),str(id));mark.set(qn('w:name'),f'Q{id:02}');p._p.insert(0,mark)
            end=OxmlElement('w:bookmarkEnd');end.set(qn('w:id'),str(id));p._p.append(end)
            labelled('参考回答',q['answer'])
            labelled('可能追问',q['followup']['question'])
            labelled('追问回答',q['followup']['answer'])
            labelled('表达边界',q['boundary'],size=10.5)
            para('复习等级 '+q['priority']+'    核对资料 '+'  '.join(source_ids[s] for s in q['sources']),'Source',keep=False)

page_heading('项目资料索引')
para('以下为项目目录 E:\\AgriScan 中的相对路径。训练报告用于说明分类实验；检测候选目录用于说明另行提供权重的接入与一致性校验；后端验收报告保留原记录日期。')
for i,s in enumerate(sources):
    p=para('',keep=False)
    p.paragraph_format.space_after=Pt(7)
    r=p.add_run(source_ids[s]+'  ');runfont(r,9.5,True)
    # Soft break opportunities keep long relative paths inside the text column.
    r=p.add_run(s.replace('/', '/\u200b').replace('-', '-\u200b'));runfont(r,9.5)

doc.core_properties.title='禾观 AgriScan 课程答辩题库'
doc.core_properties.subject='48道主问题及追问参考回答'
doc.core_properties.author='AgriScan 项目团队'
doc.core_properties.keywords='AgriScan 禾观 课程答辩 题库 PlantVillage ONNX'
OUT.parent.mkdir(parents=True,exist_ok=True)
doc.save(OUT)
(BUILD/'question-bank-page-plan.json').write_text(json.dumps({'pages':page_plan,'sources':source_ids},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'path':str(OUT),'questions':len(qa),'followups':len(qa),'sourceFiles':len(sources),'qaPages':len(page_plan),'bytes':OUT.stat().st_size},ensure_ascii=False))
