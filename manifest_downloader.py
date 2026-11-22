#!/usr/bin/env python3
"""Download an explicit JSON manifest of Google Drive files with integrity checks."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import time

FILE_ID = re.compile(r"^[A-Za-z0-9_-]{10,128}$")
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def safe_destination(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("Invalid destination path")
    # Treat backslashes as separators on every platform.
    normalized = relative.replace("\\", "/")
    segments = normalized.split("/")
    if (normalized.startswith("/") or any(s in ("", ".", "..") for s in segments)
            or ":" in segments[0] or any("\x00" in s for s in segments)):
        raise ValueError(f"Unsafe destination: {relative!r}")
    current = root
    if root.is_symlink():
        raise ValueError("Output root may not be a symlink")
    for segment in segments:
        current = current / segment
        if current.is_symlink():
            raise ValueError(f"Symlink in output path: {relative!r}")
    if not current.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Destination escapes output root: {relative!r}")
    return current


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def load_manifest(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("files"), list):
        raise ValueError("Manifest must be a JSON object with a files array")
    result = []
    destinations = set()
    for index, entry in enumerate(data["files"], 1):
        if not isinstance(entry, dict):
            raise ValueError(f"Entry {index}: expected object")
        file_id, name = entry.get("id"), entry.get("path")
        checksum = entry.get("sha256")
        if not isinstance(file_id, str) or not FILE_ID.fullmatch(file_id):
            raise ValueError(f"Entry {index}: invalid Drive file ID")
        if not isinstance(name, str):
            raise ValueError(f"Entry {index}: path must be a string")
        if checksum is not None and (not isinstance(checksum, str) or not SHA256.fullmatch(checksum)):
            raise ValueError(f"Entry {index}: invalid SHA-256")
        key = name.replace("\\", "/").casefold()
        if key in destinations:
            raise ValueError(f"Entry {index}: duplicate destination {name!r}")
        destinations.add(key)
        result.append((file_id, name, checksum.lower() if checksum else None))
    return result


def write_report(path: Path, failures):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps({"failed": failures}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="JSON manifest containing files [{id,path,sha256?}]")
    parser.add_argument("--output", type=Path, default=Path("downloads"))
    parser.add_argument("--cookies", type=Path, default=Path("cookies.txt"))
    parser.add_argument("--failed-report", type=Path, default=Path("failed-downloads.json"))
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--backoff", type=float, default=2.0)
    args = parser.parse_args(argv)
    if args.retries < 1 or args.backoff < 0:
        parser.error("--retries must be >= 1 and --backoff must be >= 0")
    if not args.cookies.is_file():
        parser.error(f"Cookie file not found: {args.cookies}")

    try:
        entries = load_manifest(args.manifest)
        # Validate every destination before writing anything.
        root = args.output.absolute()
        destinations = [safe_destination(root, name) for _, name, _ in entries]
        report_path = args.failed_report.absolute()
        if report_path == root or report_path in destinations:
            raise ValueError("Failure report must not overwrite a download")
        if report_path.is_symlink():
            raise ValueError("Failure report must not be a symlink")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    root.mkdir(parents=True, exist_ok=True)
    failures = []
    for (file_id, name, expected), target in zip(entries, destinations):
        try:
            # Recheck to reject symlinks introduced after initial validation.
            safe_destination(root, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            safe_destination(root, name)
            if target.is_file() and target.stat().st_size > 0:
                if expected is None or digest(target) == expected:
                    print(f"SKIP {name}")
                    continue
                print(f"REPLACE checksum mismatch: {name}", file=sys.stderr)
            temporary = target.with_name(target.name + ".download")
            if temporary.is_symlink() or target.is_symlink():
                raise ValueError("Symlink at target or temporary download")
            success = False
            error = "download failed"
            for attempt in range(args.retries):
                temporary.unlink(missing_ok=True)
                command = [
                    sys.executable, "-m", "yt_dlp", "--cookies", str(args.cookies),
                    "--no-playlist", "--no-part", "--no-overwrites",
                    "--format", "best[ext=mp4]/best", "-o", str(temporary),
                    f"https://drive.google.com/file/d/{file_id}/view",
                ]
                result = subprocess.run(command, check=False)
                if result.returncode == 0 and temporary.is_file() and temporary.stat().st_size > 0:
                    if expected is None or digest(temporary) == expected:
                        if target.is_symlink():
                            raise ValueError("Destination became symlink")
                        os.replace(temporary, target)
                        success = True
                        break
                    error = "SHA-256 mismatch"
                else:
                    error = f"yt-dlp exit status {result.returncode}"
                temporary.unlink(missing_ok=True)
                if attempt + 1 < args.retries:
                    time.sleep(args.backoff * (2 ** attempt) + random.uniform(0, 0.5))
            if success:
                print(f"OK   {name}")
            else:
                failures.append({"id": file_id, "path": name, "error": error})
                print(f"FAIL {name}: {error}", file=sys.stderr)
        except (OSError, ValueError) as exc:
            failures.append({"id": file_id, "path": name, "error": str(exc)})
            print(f"FAIL {name}: {exc}", file=sys.stderr)
    write_report(args.failed_report, failures)
    print(f"Completed: {len(entries) - len(failures)}/{len(entries)} entries successful or already present")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
