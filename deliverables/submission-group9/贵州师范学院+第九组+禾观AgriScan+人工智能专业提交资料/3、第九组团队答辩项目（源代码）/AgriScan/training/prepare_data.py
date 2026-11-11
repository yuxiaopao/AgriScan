"""Download the author's pinned mirror and prepare leakage-audited color splits."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import random
import shutil
import time
import urllib.request
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((Path(__file__).with_name("config.json")).read_text(encoding="utf-8"))
DATA = ROOT / "datasets" / "plantvillage"
SOURCE = CONFIG["dataset"]
BASE_URL = f"https://huggingface.co/datasets/{SOURCE['mirror']}/resolve/{SOURCE['revision']}"


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(remote, local, expected_sha=None, expected_bytes=None):
    local.parent.mkdir(parents=True, exist_ok=True)
    if local.exists():
        if expected_sha and digest(local) != expected_sha:
            raise ValueError(f"Existing download has an invalid SHA256: {local}")
        return
    partial = local.with_suffix(local.suffix + ".part")
    for attempt in range(SOURCE["download_retries"]):
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": "AgriScan-dataset-workflow/1.0"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        try:
            request = urllib.request.Request(f"{BASE_URL}/{remote}", headers=headers)
            with urllib.request.urlopen(request, timeout=SOURCE["download_timeout_seconds"]) as response:
                if offset and response.status != 206:
                    offset = 0
                if offset and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                    raise ValueError("Unexpected response range")
                length = int(response.headers.get("Content-Length", 0)) + offset
                with partial.open("ab" if offset else "wb") as output:
                    started = time.monotonic()
                    updated = 0
                    size = offset
                    while block := response.read(SOURCE["download_chunk_bytes"]):
                        output.write(block)
                        size += len(block)
                        if time.monotonic() - updated > 10:
                            updated = time.monotonic()
                            state = {"stage": "downloading", "file": remote, "bytes": size,
                                     "total": expected_bytes or length, "attempt": attempt + 1,
                                     "bytes_per_second": (size-offset)/max(updated-started, 0.001),
                                     "updated_at": time.time()}
                            write_json(DATA / "download-status.json", state)
                            print(json.dumps(state), flush=True)
                if expected_bytes and size != expected_bytes:
                    raise ValueError(f"Download size {size} != {expected_bytes}")
            if expected_sha and digest(partial) != expected_sha:
                # Retain the corrupt file for diagnosis; never resume a verified-bad archive.
                raise RuntimeError("Archive SHA256 mismatch; remove or inspect .part before retrying")
            os.replace(partial, local)
            return
        except RuntimeError:
            raise
        except Exception as error:
            print(f"Download attempt {attempt+1} failed: {error}", flush=True)
            if attempt + 1 == SOURCE["download_retries"]:
                raise
            time.sleep(min(2 ** attempt, 30))


def download_archive(local, url=None, total=None, checksum=None, status_path=None):
    """Bounded parallel HTTP ranges, resumable parts, and final source SHA256."""
    url = url or f"{BASE_URL}/data.zip"
    total = total or SOURCE["archive_bytes"]
    checksum = checksum or SOURCE["archive_sha256"]
    status_path = status_path or DATA / "download-status.json"
    if local.exists():
        if digest(local) != checksum:
            raise ValueError("Existing archive SHA256 mismatch")
        return
    local.parent.mkdir(parents=True, exist_ok=True)
    connections = SOURCE["download_connections"]
    part_size = (total + connections - 1) // connections
    parts = local.parent / ("download-parts" if local.name == "data.zip" else local.name + ".parts")
    parts.mkdir(exist_ok=True)
    ranges = [(index * part_size, min((index + 1) * part_size, total))
              for index in range(connections)]
    # Preserve an earlier sequential download as ranges without downloading it again.
    old_partial = local.with_suffix(local.suffix + ".part")
    if old_partial.exists():
        with old_partial.open("rb") as source:
            for index, (start, end) in enumerate(ranges):
                available = max(0, min(end, old_partial.stat().st_size) - start)
                part = parts / f"{index:03d}.part"
                if available and (not part.exists() or part.stat().st_size < available):
                    source.seek(start)
                    remaining = available
                    with part.open("wb") as output:
                        while remaining:
                            block = source.read(min(SOURCE["download_chunk_bytes"], remaining))
                            if not block:
                                raise ValueError("Unexpected end of partial archive")
                            output.write(block)
                            remaining -= len(block)

    def fetch(index, start, end):
        part = parts / f"{index:03d}.part"
        for attempt in range(SOURCE["download_retries"]):
            offset = part.stat().st_size if part.exists() else 0
            if offset == end-start:
                return
            if offset > end-start:
                raise ValueError(f"Range file is too large: {part}")
            try:
                request = urllib.request.Request(url, headers={
                    "User-Agent": "AgriScan-dataset-workflow/1.0",
                    "Range": f"bytes={start+offset}-{end-1}",
                })
                with urllib.request.urlopen(request, timeout=SOURCE["download_timeout_seconds"]) as response:
                    expected = f"bytes {start+offset}-{end-1}/{total}"
                    if response.status != 206 or response.headers.get("Content-Range") != expected:
                        raise RuntimeError("Source server did not honor the exact byte range")
                    with part.open("ab") as output:
                        while block := response.read(SOURCE["download_chunk_bytes"]):
                            output.write(block)
                if part.stat().st_size != end-start:
                    raise OSError("Incomplete HTTP range")
                return
            except RuntimeError:
                raise
            except Exception:
                if attempt+1 == SOURCE["download_retries"]:
                    raise
                time.sleep(min(2**attempt, 30))

    initial_bytes = sum(path.stat().st_size for path in parts.glob("*.part"))
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=connections) as executor:
        pending = {executor.submit(fetch, index, start, end)
                   for index, (start, end) in enumerate(ranges)}
        while pending:
            done, pending = wait(pending, timeout=10, return_when=FIRST_COMPLETED)
            for future in done:
                future.result()
            size = sum(path.stat().st_size for path in parts.glob("*.part"))
            progress = {"stage": "downloading", "file": local.name, "bytes": size,
                        "total": total, "connections": connections, "updated_at": time.time(),
                        "bytes_per_second": (size-initial_bytes)/max(time.monotonic()-started, 0.001)}
            write_json(status_path, progress)
            print(json.dumps(progress), flush=True)
    with old_partial.open("wb") as output:
        for index in range(connections):
            with (parts / f"{index:03d}.part").open("rb") as source:
                shutil.copyfileobj(source, output)
    if digest(old_partial) != checksum:
        raise ValueError("Reassembled archive SHA256 mismatch")
    os.replace(old_partial, local)


def leaf_identifier(relative, leaf_map):
    path = PurePosixPath(relative)
    class_name = path.parent.name
    identifier = path.stem.replace("_final_masked", "").split("___")[-1].split("copy")[0].strip()
    suggestions = leaf_map.get(identifier.lower(), [])
    if len(suggestions) == 1:
        return str(suggestions[0])
    matching = [value for value in suggestions if class_name in value]
    return str(matching[0]) if matching else f"{class_name}/{identifier.lower()}"


class Groups:
    def __init__(self, size):
        self.parents = list(range(size))

    def find(self, value):
        while self.parents[value] != value:
            self.parents[value] = self.parents[self.parents[value]]
            value = self.parents[value]
        return value

    def union(self, first, second):
        self.parents[self.find(first)] = self.find(second)


def make_split_records(records, leaf_map, test_files, seed, val_fraction):
    """Keep original test groups sealed; derive validation only from training groups."""
    unions = Groups(len(records))
    seen_leaf, seen_digest = {}, {}
    for index, record in enumerate(records):
        record["leaf_id"] = leaf_identifier(record["source"], leaf_map)
        for key, lookup in ((record["leaf_id"], seen_leaf), (record["sha256"], seen_digest)):
            if key in lookup:
                unions.union(index, lookup[key])
            else:
                lookup[key] = index
    groups = defaultdict(list)
    for index, record in enumerate(records):
        groups[unions.find(index)].append(record)
    by_class = defaultdict(list)
    moved_to_test = 0
    for members in groups.values():
        classes = {item["class"] for item in members}
        if len(classes) != 1:
            raise ValueError(f"Conflicting class labels in a leaf/content group: {classes}")
        group_id = min(item["source"] for item in members)
        for item in members:
            item["group_id"] = group_id
        if any(item["source"] in test_files for item in members):
            for item in members:
                item["split"] = "test"
                moved_to_test += item["source"] not in test_files
        else:
            by_class[members[0]["class"]].append(members)
    randomizer = random.Random(seed)
    for class_name, class_groups in sorted(by_class.items()):
        class_groups.sort(key=lambda group: min(item["source"] for item in group))
        randomizer.shuffle(class_groups)
        target = round(sum(map(len, class_groups)) * val_fraction)
        assigned = 0
        for index, members in enumerate(class_groups):
            split = "val" if assigned < target and index < len(class_groups)-1 else "train"
            if split == "val":
                assigned += len(members)
            for item in members:
                item["split"] = split
        if not any(item["split"] == "val" for group in class_groups for item in group):
            raise ValueError(f"No validation group for {class_name}")
    for field in ("group_id", "leaf_id", "sha256"):
        locations = defaultdict(set)
        for item in records:
            locations[item[field]].add(item["split"])
        if any(len(value) != 1 for value in locations.values()):
            raise AssertionError(f"Leakage across splits: {field}")
    return records, moved_to_test


def prepare():
    from PIL import Image
    DATA.mkdir(parents=True, exist_ok=True)
    metadata = DATA / "source"
    for remote in ("leaf_grouping/leaf-map.json", "splits/color_train.txt",
                   "splits/color_test.txt", "README.md", "plant_village.py"):
        download(remote, metadata / remote)
    archive = DATA / "data.zip"
    download_archive(archive)
    write_json(DATA / "download-status.json", {"stage": "extracting", "updated_at": time.time()})
    with zipfile.ZipFile(archive) as zipped:
        for entry in zipped.infolist():
            parts = PurePosixPath(entry.filename).parts
            if parts[:2] != ("raw", "color") or entry.is_dir():
                continue
            if len(parts) != 4 or any(part in (".", "..") for part in parts):
                raise ValueError(f"Unexpected archive path: {entry.filename}")
            destination = DATA.joinpath(*parts)
            if destination.exists() and destination.stat().st_size == entry.file_size:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zipped.open(entry) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)
    train_files = set((metadata / "splits/color_train.txt").read_text().splitlines())
    test_files = set((metadata / "splits/color_test.txt").read_text().splitlines())
    if train_files & test_files:
        raise ValueError("Official train/test lists overlap")
    files = sorted(path for path in (DATA / "raw/color").glob("*/*") if path.is_file())
    actual = {path.relative_to(DATA).as_posix() for path in files}
    if actual != train_files | test_files:
        raise ValueError(f"Archive/metadata disagreement: extra={len(actual-train_files-test_files)}, "
                         f"missing={len((train_files|test_files)-actual)}")
    classes = sorted({path.parent.name for path in files})
    if len(classes) != SOURCE["classes"]:
        raise ValueError(f"Expected {SOURCE['classes']} classes, received {len(classes)}")
    records, errors = [], []
    for index, path in enumerate(files):
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                image.convert("RGB").load()
            records.append({"source": path.relative_to(DATA).as_posix(),
                            "class": path.parent.name, "sha256": digest(path)})
        except Exception as error:
            errors.append({"source": str(path), "error": str(error)})
        if index % 2000 == 0:
            print(f"Verified {index}/{len(files)} images", flush=True)
    write_json(DATA / "invalid-images.json", errors)
    if errors:
        raise ValueError(f"{len(errors)} invalid images: see invalid-images.json")
    leaf_map = json.loads((metadata / "leaf_grouping/leaf-map.json").read_text())
    records, moved = make_split_records(records, leaf_map, test_files, SOURCE["seed"],
                                       SOURCE["validation_fraction_of_train"])
    dataset_root = DATA / "classification"
    desired = set()
    for record in records:
        source = DATA / record["source"]
        target = dataset_root / record["split"] / record["class"] / source.name
        desired.add(target.resolve())
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)
    # Refuse stale extra files rather than silently contaminate a split or delete user data.
    existing = {path.resolve() for path in dataset_root.glob("*/*/*") if path.is_file()}
    if existing != desired:
        raise ValueError("Existing classification directory has stale files; use a new dataset directory")
    per_class = {name: dict(Counter(item["split"] for item in records if item["class"] == name))
                 for name in classes}
    if any(set(counts) != {"train", "val", "test"} for counts in per_class.values()):
        raise ValueError("Every class must occur in all three splits")
    manifest = DATA / "manifest.jsonl"
    with manifest.open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
    report = {"source": SOURCE, "images": len(records), "classes": classes,
              "counts": dict(Counter(item["split"] for item in records)),
              "per_class": per_class, "moved_to_test_for_leakage_prevention": moved,
              "cross_split_leaf_overlap": 0, "cross_split_sha256_overlap": 0,
              "manifest_sha256": digest(manifest), "invalid_images": len(errors)}
    write_json(DATA / "dataset-report.json", report)
    write_json(DATA / "download-status.json", {"stage": "ready", "updated_at": time.time(),
                                              "counts": report["counts"]})
    print(json.dumps({key: report[key] for key in ("images", "counts", "moved_to_test_for_leakage_prevention")}), flush=True)


if __name__ == "__main__":
    try:
        prepare()
    except Exception as error:
        write_json(DATA / "download-status.json", {"stage": "failed", "error": str(error),
                                                  "updated_at": time.time()})
        raise
