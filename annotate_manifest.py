#!/usr/bin/env python3
"""Annotate a download manifest with SHA-256 values from local files.

Local hashes establish a baseline for later integrity checks, not proof that a
file was downloaded correctly from Google Drive.
"""

import argparse
import json
from pathlib import Path
import sys

from manifest_downloader import digest, load_manifest, safe_destination


def enrich_manifest(manifest: Path, root: Path, skip_missing: bool):
    document = json.loads(manifest.read_text(encoding="utf-8"))
    # Reuse the downloader's manifest validation before touching local files.
    validated = load_manifest(manifest)
    if len(document["files"]) != len(validated):
        raise ValueError("Manifest entries changed during parsing")

    updated = 0
    confirmed = 0
    missing = []
    for entry, (file_id, path, existing, expected_size) in zip(document["files"], validated):
        destination = safe_destination(root, path)
        if not destination.is_file() or destination.stat().st_size == 0:
            missing.append(path)
            continue
        actual_size = destination.stat().st_size
        if expected_size is not None:
            if actual_size != expected_size:
                raise ValueError(
                    f"Existing size_bytes does not match local file: {path!r}; "
                    "refusing to replace the expected size"
                )
        else:
            entry["size_bytes"] = actual_size
        actual = digest(destination)
        if existing is not None:
            if actual != existing:
                raise ValueError(
                    f"Existing SHA-256 does not match local file: {path!r}; "
                    "refusing to replace the expected digest"
                )
            confirmed += 1
        else:
            entry["sha256"] = actual
            updated += 1

    if missing and not skip_missing:
        examples = ", ".join(repr(path) for path in missing[:3])
        raise ValueError(
            f"{len(missing)} files missing or empty ({examples}); "
            "use --skip-missing to leave these entries unchanged"
        )
    return document, updated, confirmed, missing


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Existing JSON manifest")
    parser.add_argument("--root", type=Path, default=Path("downloads"),
                        help="Local download directory (default: downloads)")
    parser.add_argument("--output", type=Path, required=True,
                        help="New manifest path; existing files are not overwritten")
    parser.add_argument("--skip-missing", action="store_true",
                        help="Leave missing or empty files without added hashes")
    args = parser.parse_args(argv)

    source = args.manifest.absolute()
    root = args.root.absolute()
    output = args.output.absolute()
    if output == source or output == root:
        parser.error("Output must differ from the source manifest and download root")
    if output.is_symlink():
        parser.error("Output may not be a symbolic link")

    try:
        document, updated, confirmed, missing = enrich_manifest(
            source, root, args.skip_missing
        )
        # Preserve the original manifest as evidence. Create a new file only;
        # refuse existing paths even if they are empty.
        with output.open("x", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    print(
        f"Saved {output}: {updated} new SHA-256 digests, "
        f"{confirmed} existing digests confirmed, {len(missing)} missing"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
