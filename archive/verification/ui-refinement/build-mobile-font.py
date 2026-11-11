from pathlib import Path
import sys
import hashlib
import json
import urllib.request

ROOT = Path('E:/AgriScan')
WORK = ROOT / '.runtime/ui-refinement'
sys.path.insert(0, str(WORK / 'font-build-deps'))
from fontTools.ttLib import TTFont
from fontTools import subset
from fontTools.varLib.instancer import instantiateVariableFont

REVISION = '2894aab31764f10f29c421bdfd2340d3b382d384'
BASE = 'https://raw.githubusercontent.com/google/fonts/' + REVISION + '/ofl/notosanssc/'
FONT_URL = BASE + 'NotoSansSC%5Bwght%5D.ttf'
LICENSE_URL = BASE + 'OFL.txt'
SOURCE = WORK / 'NotoSansSC-variable-source.ttf'
DEST = ROOT / 'mobile/public/fonts'
DEST.mkdir(parents=True, exist_ok=True)
OUTPUT = DEST / 'agriscan-sans-sc.woff2'
if OUTPUT.exists():
    raise SystemExit('Output already exists; refusing to replace an existing font.')

def download(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'AgriScan-font-build/1.0'})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()

source_bytes = download(FONT_URL)
if len(source_bytes) < 1000000:
    raise ValueError('Unexpected source font size')
SOURCE.write_bytes(source_bytes)
license_bytes = download(LICENSE_URL)
if b'SIL OPEN FONT LICENSE Version 1.1' not in license_bytes:
    raise ValueError('Expected OFL 1.1 license')

source_files = []
text = []
for folder, extensions in [('mobile/src', {'.ts', '.tsx', '.css'}), ('frontend/src', {'.ts', '.tsx', '.css'}), ('backend/app', {'.py'})]:
    for path in sorted((ROOT / folder).rglob('*')):
        if path.is_file() and path.suffix in extensions:
            text.append(path.read_text(encoding='utf-8-sig'))
            source_files.append(path.relative_to(ROOT).as_posix())
ui_chars = {ord(c) for c in ''.join(text) if c.isprintable()}
common_han = set()
for row in range(0xB0, 0xD8):
    for cell in range(0xA1, 0xFF):
        try:
            common_han.add(ord(bytes([row, cell]).decode('gb2312')))
        except UnicodeDecodeError:
            pass
assert len(common_han) == 3755
required = ui_chars | common_han | set(range(0x20, 0x7F)) | set(range(0x2000, 0x2070)) | set(range(0x3000, 0x3040)) | set(range(0xFF00, 0xFFF0))

font = TTFont(SOURCE, recalcTimestamp=False)
original_cmap = font.getBestCmap()
supported_required = required.intersection(original_cmap)
missing_original = sorted(ui_chars.difference(original_cmap))
options = subset.Options()
options.flavor = 'woff2'
options.name_IDs = ['*']
options.name_languages = ['*']
options.name_legacy = True
options.layout_features = ['*']
options.recalc_timestamp = False
subsetter = subset.Subsetter(options=options)
subsetter.populate(unicodes=supported_required)
subsetter.subset(font)
names = {1: 'Agri Sans', 2: 'Regular', 3: 'Agri Sans Variable UI Subset 2026-10-29', 4: 'Agri Sans', 6: 'AgriSans', 16: 'Agri Sans', 17: 'Regular', 25: 'AgriSans'}
for record in font['name'].names:
    if record.nameID in names:
        record.string = names[record.nameID].encode(record.getEncoding())
font.flavor = 'woff2'
font.save(OUTPUT)
(DEST / 'OFL.txt').write_bytes(license_bytes)

check = TTFont(OUTPUT)
cmap = check.getBestCmap()
missing_subset = sorted(supported_required.difference(cmap))
assert not missing_subset, missing_subset
assert OUTPUT.read_bytes()[:4] == b'wOF2'
axes = {axis.axisTag: [axis.minValue, axis.defaultValue, axis.maxValue] for axis in check['fvar'].axes}
assert axes['wght'][0] == 100 and axes['wght'][2] == 900
weight_tests = []
for weight in [400, 600, 700]:
    instance = instantiateVariableFont(check, {'wght': weight}, inplace=False)
    assert len(instance.getBestCmap()) == len(cmap)
    assert instance['OS/2'].usWeightClass == weight
    weight_tests.append(weight)

manifest = {
    'family': 'Agri Sans',
    'derived_from': 'Noto Sans SC variable',
    'source_repository': 'https://github.com/google/fonts',
    'source_commit': REVISION,
    'source_url': FONT_URL,
    'source_sha256': hashlib.sha256(source_bytes).hexdigest(),
    'source_bytes': len(source_bytes),
    'license': 'SIL Open Font License 1.1',
    'license_url': LICENSE_URL,
    'license_file': 'OFL.txt',
    'output_file': OUTPUT.name,
    'output_bytes': OUTPUT.stat().st_size,
    'output_sha256': hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
    'variable_axes': axes,
    'coverage': {
        'static_source_files': source_files,
        'static_unique_printable_characters': len(ui_chars),
        'common_han': 'All 3755 GB2312 level 1 Han characters',
        'latin_and_punctuation': 'ASCII, supported General Punctuation, CJK punctuation, fullwidth forms',
        'output_unicode_count': len(cmap),
        'missing_static_characters_present_in_original_font': len(missing_subset),
        'characters_not_in_original_font_use_system_fallback': ['U+%04X' % value for value in missing_original],
        'dynamic_content': 'Characters outside this subset intentionally use the CSS fallback font; color emoji use the system emoji font.'
    },
    'validation': {'woff2_roundtrip': 'passed', 'preserved_wght_100_900': 'passed', 'instantiated_weights': weight_tests, 'all_source_supported_glyphs_retained': 'passed'},
    'generated_for': 'AgriScan mobile UI, 2026-10-29'
}
(DEST / 'font-source.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print(json.dumps({key: manifest[key] for key in ['family', 'source_bytes', 'output_bytes', 'output_sha256', 'variable_axes', 'validation']}, ensure_ascii=True))
print('Source files:', len(source_files), 'UI printable characters:', len(ui_chars), 'Output Unicode codepoints:', len(cmap), 'Original-font fallback codepoints:', len(missing_original))
