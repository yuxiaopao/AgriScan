import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import sharp from 'sharp';

// This helper is intentionally separate from generation/repair. Run it only
// after all 24 final page images have been selected and copied into INPUT.
const INPUT = 'E:/AgriScan/deliverables/defense/整套24页图片_20261029';
const PYTHON = 'C:/Users/18984/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe';
const OVERVIEW = '24页总览.jpg';
const MANIFEST = '24页图片清单.json';
const ZIP = path.join(path.dirname(INPUT), '禾观AgriScan_24页图片完整版.zip');
const COLS = 4, ROWS = 6, TILE_W = 480, TILE_H = 270;
const EXPECTED_RATIO = 16 / 9;
const RELATIVE_RATIO_TOLERANCE = 0.015;

const sha256 = async file => createHash('sha256').update(await fs.readFile(file)).digest('hex');
const entries = await fs.readdir(INPUT, { withFileTypes: true });
// Only top-level regular files are considered; never traverse directories.
const pngs = entries.filter(e => e.isFile() && /\.png$/i.test(e.name));
if (pngs.length !== 24) throw new Error(`Expected exactly 24 PNG pages; found ${pngs.length}. No outputs written.`);

const byNumber = new Map();
for (const entry of pngs) {
  const match = /^(\d{2})_.+\.png$/i.exec(entry.name);
  if (!match) throw new Error(`PNG does not follow NN_title.png naming: ${entry.name}`);
  const number = Number(match[1]);
  if (number < 1 || number > 24) throw new Error(`Unexpected page number in ${entry.name}`);
  if (byNumber.has(number)) throw new Error(`Duplicate page ${match[1]}: ${byNumber.get(number)} / ${entry.name}`);
  byNumber.set(number, entry.name);
}
const pageNames = Array.from({ length: 24 }, (_, i) => {
  const name = byNumber.get(i + 1);
  if (!name) throw new Error(`Missing page ${String(i + 1).padStart(2, '0')}`);
  return name;
});

const pages = [];
for (const [i, name] of pageNames.entries()) {
  const fullPath = path.join(INPUT, name);
  const metadata = await sharp(fullPath, { failOn: 'error' }).metadata();
  if (metadata.format !== 'png' || !metadata.width || !metadata.height) throw new Error(`Invalid PNG: ${name}`);
  const ratio = metadata.width / metadata.height;
  if (Math.abs(ratio / EXPECTED_RATIO - 1) > RELATIVE_RATIO_TOLERANCE) {
    throw new Error(`Page ${i + 1} is not approximately 16:9: ${name} (${metadata.width}x${metadata.height})`);
  }
  const stat = await fs.stat(fullPath);
  pages.push({ page: i + 1, file: name, width: metadata.width, height: metadata.height, bytes: stat.size, sha256: await sha256(fullPath) });
}

// Validate all existing JSON prompt/manifests before creating deliverables.
const jsonNames = entries.filter(e => e.isFile() && /\.json$/i.test(e.name) && e.name !== MANIFEST).map(e => e.name).sort();
if (!jsonNames.length) throw new Error('No top-level JSON prompt/manifest found; refusing an incomplete package.');
const jsonFiles = [];
for (const name of jsonNames) {
  const file = path.join(INPUT, name);
  JSON.parse((await fs.readFile(file, 'utf8')).replace(/^\uFEFF/, ''));
  const stat = await fs.stat(file);
  jsonFiles.push({ file: name, bytes: stat.size, sha256: await sha256(file) });
}

const tiles = [];
for (const [i, name] of pageNames.entries()) {
  // Resize only in memory for the overview; source PNG files remain untouched.
  const thumbnail = await sharp(path.join(INPUT, name), { failOn: 'error' })
    .resize(TILE_W, TILE_H, { fit: 'contain', background: '#062E25' })
    .flatten({ background: '#062E25' }).png().toBuffer();
  tiles.push({ input: thumbnail, left: (i % COLS) * TILE_W, top: Math.floor(i / COLS) * TILE_H });
}
await sharp({ create: { width: COLS * TILE_W, height: ROWS * TILE_H, channels: 3, background: '#062E25' } })
  .composite(tiles).jpeg({ quality: 92, chromaSubsampling: '4:4:4' }).toFile(path.join(INPUT, OVERVIEW));

const overviewMeta = await sharp(path.join(INPUT, OVERVIEW)).metadata();
if (overviewMeta.width !== 1920 || overviewMeta.height !== 1620) throw new Error('Unexpected overview size.');

const manifest = {
  title: '禾观 AgriScan · 课程答辩 24 页图片完整版',
  created_at_utc: new Date().toISOString(),
  source_directory: INPUT,
  deliverable_type: 'raster slide images; not an editable PowerPoint deck',
  page_count: 24,
  page_order: '01–24, left to right then top to bottom in overview',
  aspect_ratio_validation: { expected: '16:9', relative_tolerance: RELATIVE_RATIO_TOLERANCE },
  pages,
  overview: { file: OVERVIEW, width: overviewMeta.width, height: overviewMeta.height, columns: COLS, rows: ROWS, sha256: await sha256(path.join(INPUT, OVERVIEW)) },
  prompt_and_source_manifests: jsonFiles,
  archive_files: [...pageNames, OVERVIEW, ...jsonNames, MANIFEST],
};
await fs.writeFile(path.join(INPUT, MANIFEST), JSON.stringify(manifest, null, 2) + '\n', 'utf8');

// Verify source images did not change while making the contact sheet.
for (const page of pages) {
  if (await sha256(path.join(INPUT, page.file)) !== page.sha256) throw new Error(`Source PNG changed during packaging: ${page.file}`);
}

const zipCode = String.raw`
import json, os, sys, zipfile
from pathlib import Path
request = json.load(sys.stdin)
base = Path(request['directory']).resolve()
target = Path(request['zip']).resolve()
names = request['files']
if len(names) != len(set(names)):
    raise ValueError('Duplicate archive members')
temporary = target.with_name(target.name + '.building')
for name in names:
    if Path(name).name != name or name in ('.', '..'):
        raise ValueError('Only flat file names are permitted')
    source = base / name
    if not source.is_file() or source.is_symlink() or source.resolve().parent != base:
        raise ValueError('Unsafe or missing archive source: ' + name)
    if source.resolve() == target:
        raise ValueError('Archive must not contain itself')
with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True, strict_timestamps=False) as archive:
    for name in names:
        archive.write(base / name, arcname=name)
with zipfile.ZipFile(temporary, 'r') as archive:
    if archive.namelist() != names:
        raise ValueError('Archive member mismatch')
    bad = archive.testzip()
    if bad:
        raise ValueError('Archive CRC failure: ' + bad)
os.replace(temporary, target)
print(json.dumps({'zip': str(target), 'files': len(names), 'bytes': target.stat().st_size}, ensure_ascii=False))
`;
const result = spawnSync(PYTHON, ['-X', 'utf8', '-c', zipCode], {
  input: JSON.stringify({ directory: INPUT, zip: ZIP, files: manifest.archive_files }),
  encoding: 'utf8', windowsHide: true, maxBuffer: 1024 * 1024,
});
if (result.error) throw result.error;
if (result.status !== 0) throw new Error(`ZIP creation failed: ${result.stderr || result.stdout}`);
console.log(JSON.stringify({ pages_validated: 24, source_pngs_unchanged: true, overview: path.join(INPUT, OVERVIEW), manifest: path.join(INPUT, MANIFEST), archive: JSON.parse(result.stdout.trim()) }, null, 2));
