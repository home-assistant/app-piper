"""Sort the Piper voices in /data into the download and upload directories.

Up to wyoming-piper 2.5.2, catalog voices were downloaded into /data, the same
directory the web interface uploaded custom voices into. They now have their
own directories: downloads go to one that backups leave out, uploads to one
that is backed up. This moves the voice pairs already in /data, once:

1. A pair whose model and config both match an md5 digest the catalog lists for
   that file name goes to the download directory. Names are checked before
   hashing, so a custom voice under a custom name reads no bytes at all.

2. Every other pair goes to the upload directory. That covers uploads, a custom
   voice that reuses a catalog name -- a fine-tune exported as
   en_US-lessac-medium.onnx, say -- and catalog voices this cannot recognize.
   All of them are kept in backups, which is safe for any of them.

Digests come from both the bundled catalog and the voices.json that older
versions downloaded into /data: catalog models are sometimes re-exported, and a
voice downloaded before that only matches the catalog of its time.

A pair is never moved over an existing file of the same name; it is left in
/data and reported instead.
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


def _is_catalog_pair(pair: List[Path], digests: Dict[str, Set[str]]) -> bool:
    if not all(path.name in digests for path in pair):
        return False

    return all(get_file_hash(path) in digests[path.name] for path in pair)


def _megabytes(paths: List[Path]) -> str:
    return f"{sum(path.stat().st_size for path in paths) / (1024 * 1024):.0f} MiB"


def migrate_voices(data_dir: Path, download_dir: Path, upload_dir: Path) -> None:
    """Move every voice pair in data_dir to download_dir or upload_dir."""
    digests = catalog_digests(data_dir, download_dir)

    moved: Dict[Path, List[Path]] = {download_dir: [], upload_dir: []}
    skipped: List[str] = []

    for onnx_path in sorted(data_dir.glob("*.onnx")):
        # A voice is the model and its config together. A model without its
        # config was never usable, so it is left where it is.
        pair = [onnx_path, onnx_path.with_name(f"{onnx_path.name}.json")]
        if not all(path.is_file() and not path.is_symlink() for path in pair):
            continue

        target_dir = download_dir if _is_catalog_pair(pair, digests) else upload_dir
        if any((target_dir / path.name).exists() for path in pair):
            skipped.append(onnx_path.name)
            continue

        target_dir.mkdir(parents=True, exist_ok=True)
        for path in pair:
            # Same filesystem, so this is a rename: the voice is in exactly one
            # directory at every point, never half-copied.
            path.replace(target_dir / path.name)

        moved[target_dir].extend(target_dir / path.name for path in pair)

    for target_dir, what in (
        (download_dir, "catalog voice(s), left out of backups"),
        (upload_dir, "custom voice(s), kept in backups"),
    ):
        paths = moved[target_dir]
        if paths:
            names = [p.name[: -len(".onnx")] for p in paths if p.suffix == ".onnx"]
            print(
                f"Moved {len(names)} {what}, {_megabytes(paths)}, "
                f"to {target_dir}: {', '.join(names)}"
            )

    if skipped:
        print(
            f"Left in {data_dir}, already present where they belong: "
            f"{', '.join(skipped)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", help="Directory to move voices out of")
    parser.add_argument("download_dir", help="Directory catalog voices belong in")
    parser.add_argument("upload_dir", help="Directory custom voices belong in")
    args = parser.parse_args()

    migrate_voices(Path(args.data_dir), Path(args.download_dir), Path(args.upload_dir))


if __name__ == "__main__":
    main()
