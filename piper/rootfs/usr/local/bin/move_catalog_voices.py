"""Move catalog voices out of /data into the download directory.

Up to wyoming-piper 2.5.2, catalog voices were downloaded into /data, the same
directory the web interface uploads custom voices into. Uploads now stay in
/data (backed up) while downloads go to a directory left out of backups, so the
catalog voices already in /data are moved there once.

A voice is moved only when both its model and its config match an md5 digest
the catalog lists for that file name. A custom voice that reuses a catalog name
-- a fine-tune exported as en_US-lessac-medium.onnx, say -- stays in /data and
stays in backups. Names are checked before hashing, so a custom voice under a
custom name reads no bytes at all.

Digests come from both the bundled catalog and the voices.json that older
versions downloaded into /data: catalog models are sometimes re-exported, and a
voice downloaded before that only matches the catalog of its time.
"""

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Set

from wyoming_piper.download import get_voices
from wyoming_piper.file_hash import get_file_hash


def _add_digests(digests: Dict[str, Set[str]], voices: Iterable[dict]) -> None:
    for voice in voices:
        for file_path, file_info in voice.get("files", {}).items():
            digest = file_info.get("md5_digest")
            if digest:
                digests.setdefault(Path(file_path).name, set()).add(digest)


def catalog_digests(data_dir: Path, download_dir: Path) -> Dict[str, Set[str]]:
    """Map file name to every md5 digest a known catalog lists for it."""
    digests: Dict[str, Set[str]] = {}

    # Bundled catalog, plus anything already downloaded into the new location.
    # No network: --update-voices fetches the current list moments later.
    _add_digests(digests, get_voices(download_dir).values())

    old_catalog = data_dir / "voices.json"
    if old_catalog.is_file():
        try:
            with open(old_catalog, "r", encoding="utf-8") as catalog_file:
                _add_digests(digests, json.load(catalog_file).values())
        except (OSError, ValueError, AttributeError) as err:
            print(f"Ignoring {old_catalog}: {err}")

    return digests


def move_catalog_voices(data_dir: Path, download_dir: Path) -> None:
    """Move voice pairs from data_dir whose md5 matches the catalog."""
    digests = catalog_digests(data_dir, download_dir)

    moved: List[str] = []
    moved_bytes = 0

    for onnx_path in sorted(data_dir.glob("*.onnx")):
        # A voice is the model and its config together. Moving only one would
        # hide the voice from both directories.
        pair = [onnx_path, onnx_path.with_name(f"{onnx_path.name}.json")]

        if not all(path.is_file() and not path.is_symlink() for path in pair):
            continue

        if not all(path.name in digests for path in pair):
            continue

        if not all(get_file_hash(path) in digests[path.name] for path in pair):
            continue

        download_dir.mkdir(parents=True, exist_ok=True)
        for path in pair:
            moved_bytes += path.stat().st_size
            # Same filesystem, so this is a rename: the voice is in exactly one
            # of the two directories at every point, never half-copied.
            path.replace(download_dir / path.name)

        moved.append(onnx_path.name[: -len(".onnx")])

    if moved:
        print(
            f"Moved {len(moved)} catalog voice(s), "
            f"{moved_bytes / (1024 * 1024):.0f} MiB, to {download_dir}, "
            f"which is left out of backups: {', '.join(moved)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", help="Directory voices are uploaded into")
    parser.add_argument("download_dir", help="Directory catalog voices belong in")
    args = parser.parse_args()

    move_catalog_voices(Path(args.data_dir), Path(args.download_dir))


if __name__ == "__main__":
    main()
