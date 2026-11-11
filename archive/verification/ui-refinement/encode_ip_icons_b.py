import json
import shutil
from pathlib import Path
from PIL import Image

manifest = Path('E:/AgriScan/design/mobile-field-journal/ip-icon-prompts-b.json')
doc = json.loads(manifest.read_text(encoding='utf-8'))
for item in doc['icons']:
    original = Path(item['generation_path'])
    source = Path(item['source_path'])
    output = Path(item['project_path'])
    source.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(original, source)
    with Image.open(source) as image:
        rgba = image.convert('RGBA')
        alpha = rgba.getchannel('A')
        extrema = alpha.getextrema()
        if extrema[0] != 0 or extrema[1] != 255:
            raise RuntimeError('Source does not have genuine transparency: ' + item['name'])
        item['source_size'] = list(image.size)
        item['source_mode'] = image.mode
        item['source_alpha_range'] = list(extrema)
        item['source_alpha_bbox'] = list(alpha.getbbox())
        item['source_transparent_pixels'] = alpha.histogram()[0]
        rgba.resize((192, 192), Image.Resampling.LANCZOS).save(output, format='WEBP', quality=92, method=6, alpha_quality=100)
    with Image.open(output) as image:
        alpha = image.getchannel('A')
        item['production_size'] = list(image.size)
        item['production_mode'] = image.mode
        item['production_alpha_range'] = list(alpha.getextrema())
        item['production_transparent_pixels'] = alpha.histogram()[0]
    item['source_bytes'] = source.stat().st_size
    item['production_bytes'] = output.stat().st_size
manifest.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps([{key: value for key, value in item.items() if key != 'prompt'} for item in doc['icons']], ensure_ascii=False, indent=2))
