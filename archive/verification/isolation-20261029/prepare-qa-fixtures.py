import hashlib
import json
from pathlib import Path
import shutil
from uuid import uuid4

root=Path(__file__).resolve().parents[2]
folder=Path(__file__).resolve().parent
manifest=folder/'qa-fixtures.json'
assert not manifest.exists(),'Existing QA fixture manifest preserved; inspect and resume explicitly.'
suffix=uuid4().hex[:6]
sources={
 'apple':root/'datasets/plantvillage/classification/test/Apple___Apple_scab/0261a6e4-21f8-481a-8827-b674e6955644___FREC_Scab 3055.JPG',
 'corn_rust':root/'datasets/plantvillage/classification/test/Corn_(maize)___Common_rust_/RS_Rust 2036.JPG',
 'corn_healthy':root/'datasets/plantvillage/classification/test/Corn_(maize)___healthy/205f8753-7598-4469-86c2-59307f90e85c___R.S_HL 8228 copy.jpg',
}
items={}
for key,source in sources.items():
    assert source.is_file()
    local=folder/f'qa-fixture-{suffix}-{key}.jpg'
    shutil.copyfile(source,local)
    items[key]={'local':str(local),'remote':f'/srv/agriscan/bootstrap/qa_iso_20261029_{suffix}_{key}.jpg',
                'sha256':hashlib.sha256(local.read_bytes()).hexdigest(),'bytes':local.stat().st_size,'source':str(source)}
manifest.write_text(json.dumps({'suffix':suffix,'fixtures':items},indent=2),encoding='utf-8')
print(json.dumps({'suffix':suffix,'fixture_count':len(items),'bytes':sum(item['bytes'] for item in items.values())}))
