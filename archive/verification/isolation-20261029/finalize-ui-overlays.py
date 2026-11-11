import json
from pathlib import Path

for name in ['admin/src/Admin.tsx','.runtime/patch-owner-admin-ui.py']:
    path=Path(name);source=path.read_text(encoding='utf-8')
    for old,new in [
        ("useState(record.owner_id?(record.plot_id??''):'')","useState(record.plot_id??'')"),
        ("plot_id:owner==='unassigned'?null:(plotId||null)","plot_id:plotId||null"),
        ("disabled={busy||plots.loading||owner==='unassigned'}","disabled={busy||plots.loading}"),
        ("!ownerChanged&&record.plot_id&&record.owner_id&&","!ownerChanged&&record.plot_id&&"),
        ('请先分配归属用户，再关联地块。','请先分配归属用户再关联新地块；已有历史关联可保留或解除。'),
    ]:
        if source.count(old)!=1:raise RuntimeError('Expected one edit in '+name)
        source=source.replace(old,new,1)
    path.write_text(source,encoding='utf-8')
print('Historical association preservation updated without changing parallel design.')
