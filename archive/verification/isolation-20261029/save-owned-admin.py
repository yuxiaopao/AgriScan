from pathlib import Path
import subprocess

target=Path('.runtime/isolation-20261029/admin-ui-own-only.tsx')
original=subprocess.run(['git','show','HEAD:admin/src/Admin.tsx'],capture_output=True,check=True).stdout
target.write_bytes(original)
script=Path('.runtime/patch-owner-admin-ui.py').read_text(encoding='utf-8')
script=script.replace("path=Path('admin/src/Admin.tsx')","path=Path('.runtime/isolation-20261029/admin-ui-own-only.tsx')")
exec(compile(script,'<owned-admin-patch>','exec'))
print('Saved an ownership-only Admin.tsx snapshot from HEAD.')
