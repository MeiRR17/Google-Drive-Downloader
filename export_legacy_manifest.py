#!/usr/bin/env python3
"""Export the legacy COURSE_STRUCTURE assignment to a JSON download manifest.

The source is parsed as Python syntax but never imported or executed.
Only a literal dictionary is accepted.
"""

import argparse
import ast
import json
from pathlib import Path
import sys

from manifest_downloader import FILE_ID, safe_destination


def read_course_structure(source: Path):
    tree = ast.parse(source.read_text(encoding="utf-8-sig"), filename=str(source))
    matches = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "COURSE_STRUCTURE"
            for target in node.targets
        ):
            matches.append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "COURSE_STRUCTURE":
            matches.append(node.value)
    if len(matches) != 1:
        raise ValueError("Expected exactly one COURSE_STRUCTURE assignment")
    try:
        structure = ast.literal_eval(matches[0])
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError) as exc:
        raise ValueError("COURSE_STRUCTURE must contain a literal dictionary") from exc
    if not isinstance(structure, dict):
        raise ValueError("COURSE_STRUCTURE must be a dictionary")
    return structure


def export_entries(structure):
    entries = []
    destinations = set()
    for folder, files in structure.items():
        if not isinstance(folder, str) or not isinstance(files, (list, tuple)):
            raise ValueError("Every course folder must map to a list or tuple")
        # Folder names may include nested components, filenames may not.
        if not folder or folder.startswith(("/", "\\")) or ":" in folder:
            raise ValueError(f"Invalid folder: {folder!r}")
        if not folder.replace("\\", "/").split("/") or any(
            part in ("", ".", "..") for part in folder.replace("\\", "/").split("/")
        ):
            raise ValueError(f"Unsafe folder: {folder!r}")
        for pair in files:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError(f"Expected (file_id, filename) in {folder!r}")
            file_id, filename = pair
            if not isinstance(file_id, str) or not FILE_ID.fullmatch(file_id):
                raise ValueError(f"Invalid file ID in {folder!r}")
            if (not isinstance(filename, str) or not filename
                    or filename in (".", "..") or "/" in filename
                    or "\\" in filename or ":" in filename):
                raise ValueError(f"Unsafe filename in {folder!r}: {filename!r}")
            destination = folder.replace("\\", "/") + "/" + filename
            # Apply exactly the same path checks as the manifest downloader.
            safe_destination(Path("downloads").absolute(), destination)
            key = destination.casefold()
            if key in destinations:
                raise ValueError(f"Duplicate target: {destination!r}")
            destinations.add(key)
            entries.append({"id": file_id, "path": destination})
    return entries


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).with_name("auto_downloader.py"))
    parser.add_argument("--output", type=Path, default=Path("manifest.json"))
    args = parser.parse_args(argv)
    try:
        entries = export_entries(read_course_structure(args.source))
        payload = json.dumps({"files": entries}, indent=2, ensure_ascii=False) + "\n"
        # Exclusive creation protects existing user-edited manifest files.
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(payload)
    except FileExistsError:
        parser.error(f"Output already exists (not overwritten): {args.output}")
    except (OSError, ValueError, SyntaxError) as exc:
        parser.error(str(exc))
    print(f"Exported {len(entries)} entries to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
