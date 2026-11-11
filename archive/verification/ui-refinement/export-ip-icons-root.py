import json, shutil, hashlib
from pathlib import Path
from PIL import Image

root=Path('E:/AgriScan')
manifest_path=root/'design/mobile-field-journal/ip-icon-prompts-root.json'
manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
for asset in manifest['assets']:
    source=Path(asset['generated_source'])
    copied=root/asset['source_copy']
    output=root/asset['project_path']
    if copied.exists() or output.exists():
        raise FileExistsError(asset['name'])
    copied.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source,copied)
    original=Image.open(copied).convert('RGBA')
    assert original.getchannel('A').getextrema()==(0,255)
    encoded=original.resize((192,192), Image.Resampling.LANCZOS)
    encoded.save(output,format='WEBP',lossless=True,method=6)
    decoded=Image.open(output).convert('RGBA')
    assert decoded.getchannel('A').tobytes()==encoded.getchannel('A').tobytes()
    asset.update(source_size=list(original.size),output_size=list(decoded.size),bytes=output.stat().st_size,sha256=hashlib.sha256(output.read_bytes()).hexdigest(),alpha_extrema=list(decoded.getchannel('A').getextrema()))
    print(asset['name'],asset['bytes'],asset['alpha_extrema'])
manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
