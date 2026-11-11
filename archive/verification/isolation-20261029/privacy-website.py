"""Only change privacy wording; preserve unrelated in-progress design edits."""
from pathlib import Path
import subprocess

name='website/index.html'
changes=[('工作空间数据互通 · 小禾对话按账户保存','同一账户跨端同步 · 不同账户的数据独立保存'),
         ('使用同一账户登录即可查看共享工作空间的数据；小禾私人对话只对所属账户开放。',
          '使用同一账户登录即可同步自己的检测和地块；不同账户的数据互不可见，小禾对话也只对所属账户开放。')]
content=subprocess.check_output(['git','show','HEAD:'+name]).decode('utf-8')
working=Path(name).read_text(encoding='utf-8')
for old,new in changes:
    assert old in content
    content=content.replace(old,new)
    if old in working: working=working.replace(old,new)
destination=Path('.runtime/isolation-20261029/owned-document')/name
destination.parent.mkdir(parents=True,exist_ok=True)
destination.write_text(content,encoding='utf-8')
Path(name).write_text(working,encoding='utf-8')
print('Website privacy-only snapshot created; parallel design retained in working copy')
