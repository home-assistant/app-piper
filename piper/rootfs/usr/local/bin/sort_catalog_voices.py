"""Keep re-downloadable catalog voice models out of the backed-up part of /data.

Catalog voices and uploaded ones would otherwise sit side by side: by default
wyoming-piper downloads catalog models into --download-dir, and the web
interface uploads custom voices there too. Only the uploads are irreplaceable,
while a single catalog voice is 20-110 MB of every backup the app is part of,
for something a restore fetches again on demand.

Catalog models live in /data/catalog_voices instead, which config.yaml excludes
from backups and which is handed back to wyoming-piper as another --data-dir:

1. At startup, sort_catalog_voices() moves any catalog voices already in /data
   (from versions before this split, or uploaded unmodified through the web UI)
   into /data/catalog_voices. A file is moved only when its md5 matches what the
   catalog lists for that name, so a custom voice that reuses a catalog name --
   a fine-tune exported as en_US-lessac-medium.onnx, say -- stays in /data and
   stays in backups. Names are checked before hashing, so a custom voice under a
   custom name reads no bytes at all.

2. At runtime (--run), wyoming_piper.download.ensure_voice_exists is directed to
   download missing catalog voices straight into /data/catalog_voices while
   --download-dir remains /data. That keeps web UI uploads (and voices.json and
   HF_HOME) in /data so uploads are always backed up, while voices downloaded at
   startup or on demand while the app runs never land in /data in the first
   place.
"""

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Union

import wyoming_piper.download as piper_download
from wyoming_piper.download import get_voices
from wyoming_piper.file_hash import get_file_hash

_ensure_voice_exists = piper_download.ensure_voice_exists


def catalog_digests(download_dir: Path) -> Dict[str, Set[str]]:
    """Map file name to the md5 digests the catalog publishes for that name.

    A set rather than one digest: the same file is listed under a voice and
    under each of its aliases, and nothing guarantees those agree.
    """
    digests: Dict[str, Set[str]] = {}

    # update_voices is left off: this must not depend on the network, and the
    # Piper service downloads the current voices.json moments later anyway.
    for voice in get_voices(download_dir).values():
        for file_path, file_info in voice.get("files", {}).items():
            digest = file_info.get("md5_digest")
            if digest:
                digests.setdefault(Path(file_path).name, set()).add(digest)

    return digests


def sort_catalog_voices(data_dir: Path, catalog_dir: Path) -> None:
    """Move catalog voice pairs whose md5 matches the catalog to catalog_dir."""
    digests = catalog_digests(data_dir)

    moved: List[str] = []
    moved_bytes = 0

    for onnx_path in sorted(data_dir.glob("*.onnx")):
        # A voice is the model and its config together. Moving one without the
        # other would hide the voice from both directories.
        pair = [onnx_path, onnx_path.with_name(f"{onnx_path.name}.json")]

        if not all(path.is_file() and not path.is_symlink() for path in pair):
            continue

        if not all(path.name in digests for path in pair):
            continue

        if not all(get_file_hash(path) in digests[path.name] for path in pair):
            continue

        catalog_dir.mkdir(parents=True, exist_ok=True)
        for path in pair:
            moved_bytes += path.stat().st_size
            # Same filesystem, so this is a rename: the voice is in exactly one
            # of the two directories at every point, never half-copied.
            path.replace(catalog_dir / path.name)

        moved.append(onnx_path.name[: -len(".onnx")])

    if moved:
        print(
            f"Moved {len(moved)} re-downloadable voice(s), "
            f"{moved_bytes / (1024 * 1024):.0f} MiB, to {catalog_dir}, "
            f"which is left out of backups: {', '.join(moved)}"
        )


def _has_voice_pair(directory: Path, name: str) -> bool:
    """Return True if directory has a non-empty .onnx and .onnx.json for name."""
    for suffix in (".onnx", ".onnx.json"):
        path = directory / f"{name}{suffix}"
        if not path.is_file() or path.stat().st_size == 0:
            return False
    return True


def run_piper(catalog_dir: Path, piper_args: List[str]) -> None:
    """Run wyoming-piper with catalog downloads directed to catalog_dir."""

    def ensure_voice_exists(
        name: str,
        data_dirs: Iterable[Union[str, Path]],
        _download_dir: Union[str, Path],
        voices_info: Dict[str, Any],
    ) -> None:
        """Download missing catalog voices into catalog_dir."""
        if "files" in voices_info.get(name, {}):
            # find_voice() requires both files in the same data_dir. Only check
            # directories that already have a complete pair so a stray single
            # file in /data cannot split a download across two directories.
            complete_dirs = [
                d for d in data_dirs if _has_voice_pair(Path(d), name)
            ]
            data_dirs = complete_dirs or [catalog_dir]

        _ensure_voice_exists(name, data_dirs, catalog_dir, voices_info)

    import wyoming_piper.__main__ as piper_main
    import wyoming_piper.handler as piper_handler

    piper_download.ensure_voice_exists = ensure_voice_exists
    piper_handler.ensure_voice_exists = ensure_voice_exists
    piper_main.ensure_voice_exists = ensure_voice_exists

    sys.argv = [sys.argv[0], *piper_args]
    piper_main.run()


def main() -> None:
    """Entry point for sorting catalog voices or launching wyoming-piper."""
    if len(sys.argv) >= 3 and sys.argv[1] == "--run":
        run_piper(Path(sys.argv[2]), sys.argv[3:])
        return

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", help="Directory voices are uploaded into")
    parser.add_argument("catalog_dir", help="Directory to move catalog voices to")
    args = parser.parse_args()

    sort_catalog_voices(Path(args.data_dir), Path(args.catalog_dir))


if __name__ == "__main__":
    main()
