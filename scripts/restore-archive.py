"""Download, verify, and restore the public project snapshot with Python 3.12+."""

import argparse
import hashlib
import io
import json
import sys
import tarfile
import urllib.request
from pathlib import Path


class ArchiveParts(io.RawIOBase):
    def __init__(self, paths):
        super().__init__()
        self.paths = iter(paths)
        self.current = None

    def readable(self):
        return True

    def read(self, size=-1):
        chunks = []
        remaining = size
        while remaining != 0:
            if self.current is None:
                path = next(self.paths, None)
                if path is None:
                    break
                self.current = path.open('rb')
            chunk = self.current.read(remaining)
            if not chunk:
                self.current.close()
                self.current = None
                continue
            chunks.append(chunk)
            if remaining > 0:
                remaining -= len(chunk)
        return b''.join(chunks)

    def close(self):
        if self.current is not None:
            self.current.close()
        super().close()


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def download(asset, cache):
    name = asset['name']
    if Path(name).name != name:
        raise ValueError('Invalid asset filename')
    destination = cache / name
    if destination.exists() and destination.stat().st_size == asset['bytes']:
        if sha256(destination) == asset['sha256']:
            print('Verified cached asset ' + name, flush=True)
            return destination
    partial = destination.with_name(destination.name + '.partial')
    request = urllib.request.Request(asset['url'], headers={'User-Agent': 'AgriScan-archive-restore'})
    digest = hashlib.sha256()
    count = 0
    print('Downloading ' + name, flush=True)
    with urllib.request.urlopen(request, timeout=120) as response, partial.open('wb') as output:
        for chunk in iter(lambda: response.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
            count += len(chunk)
            output.write(chunk)
    if count != asset['bytes'] or digest.hexdigest() != asset['sha256']:
        raise ValueError('Downloaded asset failed verification: ' + name)
    partial.replace(destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path(__file__).resolve().parents[1] / 'archive/release-manifest.json')
    parser.add_argument('--cache', type=Path, default=Path('.archive-downloads'))
    parser.add_argument('--output', type=Path, required=True, help='An empty directory for the restored snapshot')
    parser.add_argument('--download-only', action='store_true')
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        parser.error('Python 3.12 or newer is required for safe archive extraction')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    assets = manifest['archive_parts']
    if not assets:
        parser.error('The manifest does not contain archive parts')
    if args.output.exists() and (not args.output.is_dir() or any(args.output.iterdir())):
        parser.error('--output must be an empty directory')
    args.cache.mkdir(parents=True, exist_ok=True)
    paths = [download(asset, args.cache) for asset in assets]
    if args.download_only:
        print('All archive parts have been downloaded and verified.', flush=True)
        return
    args.output.mkdir(parents=True, exist_ok=True)
    print('Extracting into ' + str(args.output.resolve()), flush=True)
    with ArchiveParts(paths) as stream, tarfile.open(fileobj=stream, mode='r|gz') as archive:
        archive.extractall(path=args.output, filter='data')
    print('Restored the public snapshot. Environment templates and redacted records are included.', flush=True)


if __name__ == '__main__':
    main()
