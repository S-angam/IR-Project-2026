"""Download and extract TREC ToT data, reusing files already on disk."""

import hashlib
import json
from pathlib import Path
import shutil
from urllib.request import urlopen
from zipfile import ZipFile


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CHUNK_SIZE = 1024 * 1024


def _target_path(root: Path, name: str) -> Path:
    target = (root / name).resolve()
    if not target.is_relative_to(root.resolve()) or target == root.resolve():
        raise ValueError(f"Dataset path escapes its directory: {name}")
    return target


def _matches_size(path: Path, expected_size: int) -> bool:
    return path.is_file() and path.stat().st_size == expected_size


def _checksum(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "md5").hexdigest()


def _ensure_archive(archive: Path, url: str, expected_md5: str) -> None:
    if archive.is_file() and _checksum(archive) == expected_md5:
        print(f"Reusing archive: {archive.name}", flush=True)
        return

    print(f"Downloading: {archive.name}", flush=True)
    partial = archive.with_name(archive.name + ".part")
    try:
        with urlopen(url, timeout=60) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output, CHUNK_SIZE)
        if _checksum(partial) != expected_md5:
            raise ValueError(f"Checksum mismatch for {archive.name}")
        partial.replace(archive)
    finally:
        partial.unlink(missing_ok=True)


def ensure_dataset(data_dir: Path = DATA_DIR) -> Path:
    """Prepare data/raw and return its path; complete datasets need no network.

    The manifest specifies expected extracted paths and byte sizes. Existing
    outputs of those sizes are skipped. ZIP checksums are verified whenever
    extraction is needed; ZipFile checks member CRCs during extraction.
    """
    data_dir = Path(data_dir).resolve()
    manifest = json.loads((data_dir / "sources.json").read_text(encoding="utf-8"))
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    for item in manifest["files"]:
        expected = item["extracted_files"]
        if not expected:
            raise ValueError(f"No extraction targets for {item['filename']}")
        targets = {name: _target_path(raw_dir, name) for name in expected}
        missing = [
            name for name, path in targets.items()
            if not _matches_size(path, expected[name])
        ]
        if not missing:
            print(f"Already ready: {item['filename']}", flush=True)
            continue

        archive = _target_path(raw_dir, item["filename"])
        _ensure_archive(archive, item["url"], item["md5"])
        with ZipFile(archive) as zipped:
            # Extract only manifest-listed data files, excluding __MACOSX metadata.
            for name in missing:
                member = zipped.getinfo(name)
                if member.is_dir() or member.file_size != expected[name]:
                    raise ValueError(f"Unexpected archive member: {name}")

            for name in missing:
                target = targets[name]
                target.parent.mkdir(parents=True, exist_ok=True)
                partial = target.with_name(target.name + ".part")
                print(f"Extracting: {name}", flush=True)
                try:
                    with zipped.open(name) as source, partial.open("wb") as output:
                        shutil.copyfileobj(source, output, CHUNK_SIZE)
                    if not _matches_size(partial, expected[name]):
                        raise ValueError(f"Incomplete extraction: {name}")
                    partial.replace(target)
                finally:
                    partial.unlink(missing_ok=True)

    print(f"Dataset ready: {raw_dir}", flush=True)
    return raw_dir


if __name__ == "__main__":
    ensure_dataset()
