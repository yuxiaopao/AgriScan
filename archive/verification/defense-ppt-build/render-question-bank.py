import importlib.util, shutil, sys, os
from pathlib import Path

root=Path('E:/AgriScan/.runtime/defense-ppt-build')
skill=Path('C:/Users/18984/.codex/plugins/cache/openai-primary-runtime/documents/26.1020.11618/skills/documents/render_docx.py')
spec=importlib.util.spec_from_file_location('packaged_docx_renderer',skill)
renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)

def native_word_pdf(doc_path,user_profile,convert_tmp_dir,stem,verbose):
    source=root/'question-bank-native.pdf'
    assert source.exists() and source.stat().st_size>0
    target=Path(convert_tmp_dir)/(stem+'.pdf')
    shutil.copy2(source,target)
    return str(target),'Native Microsoft Word ExportAsFixedFormat used because this Windows runtime does not bundle LibreOffice.'

renderer.convert_to_pdf=native_word_pdf
os.environ['PATH']='C:/Users/18984/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin'+os.pathsep+os.environ.get('PATH','')
sys.argv=[str(skill),'E:/AgriScan/deliverables/defense/禾观AgriScan_课程答辩题库_48题含参考回答.docx','--output_dir',str(root/'question-bank-render-final'),'--dpi','144','--emit_pdf']
renderer.main()
