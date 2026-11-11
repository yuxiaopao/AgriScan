"""Reapply only this agent's UI changes to HEAD without touching the worktree."""
import ast
from pathlib import Path
import re
import subprocess
import json

root=Path('.runtime/isolation-20261029/owned-ui')
def baseline(name):
    return subprocess.run(['git','show','HEAD:'+name],capture_output=True,check=True).stdout.decode('utf-8')
def save(name,source):
    target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(source,encoding='utf-8')
def once(source,old,new):
    if source.count(old)!=1:raise RuntimeError('Unexpected edit anchor: '+old[:80])
    return source.replace(old,new,1)
def line(source,start):
    return next(row for row in source.splitlines() if row.startswith(start))
def replace_region(base,working,start,end):
    b=base.index(start);e=base.index(end,b)
    w=working.index(start);we=working.index(end,w)
    return base[:b]+working[w:we]+base[e:]

copy_program=ast.parse(Path('.runtime/isolation-20261029/patch-personal-copy.py').read_text(encoding='utf-8'))
copy_changes=ast.literal_eval(next(node.value for node in copy_program.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='changes' for t in node.targets)))

name='frontend/src/App.tsx';source=baseline(name);working=Path(name).read_text(encoding='utf-8')
source=once(source,'  const client = useClientConfiguration()','  const client = useClientConfiguration()\n  const sessionToken = getToken()')
for prefix in ['  const queueDetection','    const expired']:
    source=once(source,line(source,prefix),line(working,prefix))
source=once(source,line(source,'  const requireAuth'),line(source,'  const requireAuth')+'\n'+line(working,'  function clearAccountData'))
source=once(source,line(source,'    if (getToken()) api<User>'),line(working,'    const bootToken')+'\n'+line(working,'    if (bootToken)'))
source=replace_region(source,working,'  useEffect(() => {\n    if (accessPage || isAdminHash()) return','  useEffect(() => {if (!toastMessage)')
source=once(source,'        setToken(null); setUser(null); setData(null); setDetectionRequests([]); setSelected(null); setDeleteRecord(false)','        setToken(null);setUser(null);clearAccountData()')
source=replace_region(source,working,'  async function removeRecord() {','  const currentPageName')
source=once(source,"onLogin={value => {setUser(value); window.location.hash = 'dashboard'; reload()}}", "onLogin={value => {clearAccountData();setUser(value);window.location.hash = 'dashboard';reload()}}")
source=once(source,'  return <div className="app-shell">','  return <div className="app-shell" key={user?.username??\'guest\'}>')
for old,new in copy_changes[name]:source=source.replace(old,new)
save(name,source)

for name in ['frontend/src/Dashboard.tsx','frontend/src/Pages.tsx','mobile/src/WorkspacePages.tsx']:
    source=baseline(name)
    for old,new in copy_changes[name]:source=source.replace(old,new)
    save(name,source)

name='frontend/src/PlotEditor.tsx';source=baseline(name);working=Path(name).read_text(encoding='utf-8')
source=once(source,"type FormEvent}","type FormEvent, type ReactNode}")
for prefix in ['interface Props ', 'export default function PlotEditor(', '  const key = ', '    const body = ']:
    source=once(source,line(source,prefix),line(working,prefix))
source=once(source,'`/plots${savedId ? `/${savedId}` : \'\'}`','`${apiPrefix}${savedId ? `/${savedId}` : \'\'}`')
source=source.replace('`/plots/${saved.id}/cover`','`${apiPrefix}/${saved.id}/cover`')
anchor=line(source,'      {error &&')
source=once(source,anchor,anchor+'\n'+line(working,"      {apiPrefix==='/admin/plots'"))
save(name,source)

name='mobile/src/App.tsx';source=baseline(name);working=Path(name).read_text(encoding='utf-8')
source=once(source,line(source,'    setChecking(true);api<User>'),line(working,'    const token=')+'\n'+line(working,'    const stillCurrent=')+'\n'+line(working,'    setChecking(true);api<User>'))
source=once(source,line(source,'  async function logout()'),line(working,'  async function logout()'))
source=once(source,'onLogin={value=>{setUser(value);navigate(\'home\')}}',"onLogin={value=>{dataVersion.current++;setData(emptyWorkspace);setSelected(null);setAnalysis(null);setError('');setToast('');setUser(value);navigate('home')}}")
source=once(source,'return <div className={`app-frame page-${page}`}><header','return <div className={`app-frame page-${page}`} key={`${getServiceBase()}:${user?.username??\'guest\'}`}><header')
save(name,source)

admin=Path('.runtime/isolation-20261029/admin-ui-own-only.tsx').read_text(encoding='utf-8')
save('admin/src/Admin.tsx',admin)
save('admin/src/OwnerPicker.tsx',Path('admin/src/OwnerPicker.tsx').read_text(encoding='utf-8'))
name='admin/src/admin.css';style=next(row for row in Path(name).read_text(encoding='utf-8').splitlines() if row.startswith('.adm-owner-picker'))
save(name,baseline(name)+'\n'+style+'\n')
files=sorted(str(path.relative_to(root)).replace('\\','/') for path in root.rglob('*') if path.is_file())
Path('.runtime/isolation-20261029/owned-ui-files.json').write_text(json.dumps(files,indent=2),encoding='utf-8')
print(json.dumps({'files':files,'root':str(root)}))
