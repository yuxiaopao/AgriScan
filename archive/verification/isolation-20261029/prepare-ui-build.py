import io
import json
from pathlib import Path
import subprocess
import tarfile

root=Path('.runtime/isolation-20261029/build').resolve()
if root.exists() and any(root.iterdir()):
    # An interrupted initial preparation may already contain our three package
    # junctions. Never traverse or remove their targets.
    for surface in root.iterdir():
        if surface.name not in {'frontend','admin','mobile'} or not surface.is_dir():
            raise SystemExit('Build snapshot already exists; preserved.')
        if any(entry.name!='node_modules' for entry in surface.iterdir()):
            raise SystemExit('Build snapshot already exists; preserved.')
root.mkdir(parents=True,exist_ok=True)
head=subprocess.run(['git','rev-parse','HEAD'],check=True,capture_output=True,text=True).stdout.strip()
archive=subprocess.run(['git','archive',head,'frontend','admin','mobile'],check=True,capture_output=True).stdout
with tarfile.open(fileobj=io.BytesIO(archive),mode='r:') as bundle:
    for member in bundle.getmembers():
        destination=(root/member.name).resolve()
        if (destination!=root and root not in destination.parents) or not (member.isfile() or member.isdir()):
            raise SystemExit('Unsafe source archive member rejected.')
    bundle.extractall(root)
overlay=Path('.runtime/isolation-20261029/owned-ui')
files=json.loads(Path('.runtime/isolation-20261029/owned-ui-files.json').read_text(encoding='utf-8'))
for name in files:
    destination=root/name
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_bytes((overlay/name).read_bytes())
assert './polish.css' not in (root/'admin/src/Admin.tsx').read_text(encoding='utf-8')
assert 'MotionSurface' not in (root/'frontend/src/App.tsx').read_text(encoding='utf-8')
assert 'ObservationStack' not in (root/'frontend/src/Dashboard.tsx').read_text(encoding='utf-8')
report={'root':str(root),'head':head,'overlay_files':files,'unknown_design_imports_excluded':True}
Path('.runtime/isolation-20261029/ui-source-snapshot.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
