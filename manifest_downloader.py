#!/usr/bin/env python3
"""Download an explicit JSON manifest of Google Drive files with integrity checks."""

import argparse
import fnmatch
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


def failed_entries(report_path: Path, entries):
    """Select entries recorded as failures, restricted to the current manifest."""
    data = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("failed"), list):
        raise ValueError("Failure report must contain a failed array")
    known = {(file_id, path) for file_id, path, _ in entries}
    selected = set()
    for index, item in enumerate(data["failed"], 1):
        if not isinstance(item, dict):
            raise ValueError(f"Failure report entry {index} must be an object")
        file_id, path = item.get("id"), item.get("path")
        if not isinstance(file_id, str) or not isinstance(path, str):
            raise ValueError(f"Failure report entry {index} must include string id and path")
        pair = (file_id, path)
        if pair not in known:
            raise ValueError(f"Failure report entry {index} does not match the manifest")
        selected.add(pair)
    return [entry for entry in entries if (entry[0], entry[1]) in selected]


def select_entries(entries, includes, excludes, limit):
    """Filter manifest paths in their original order, using POSIX-style separators.

    Shell-style patterns are matched against the entire manifest path; glob
    wildcards are case-sensitive and do not change the destination on disk.
    """
    selected = []
    for entry in entries:
        path = entry[1].replace("\\", "/")
        if includes and not any(fnmatch.fnmatchcase(path, pattern) for pattern in includes):
            continue
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in excludes):
            continue
        selected.append(entry)
        if limit is not None and len(selected) >= limit:
            break
    return selected


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
    parser.add_argument("--only-failed", type=Path, metavar="REPORT",
                        help="Retry only entries listed in a previous failure report")
    parser.add_argument("--dry-run", action="store_true",
                        help="List selected destinations without writing or downloading")
    parser.add_argument("--include", action="append", default=[], metavar="GLOB",
                        help="Include matching manifest paths (repeatable)")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="Exclude matching manifest paths (repeatable)")
    parser.add_argument("--limit", type=int, metavar="N",
                        help="Process at most N matching files, in manifest order")
    parser.add_argument("--force", action="store_true",
                        help="Re-download selected files even when a destination already exists")
    parser.add_argument("--verify-only", action="store_true",
                        help="Audit local files and optional checksums without network access")
    args = parser.parse_args(argv)
    if args.retries < 1 or args.backoff < 0:
        parser.error("--retries must be >= 1 and --backoff must be >= 0")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")
    if args.verify_only and args.force:
        parser.error("--verify-only cannot be combined with --force")
    if args.verify_only and args.dry_run:
        parser.error("--verify-only cannot be combined with --dry-run")

    try:
        entries = load_manifest(args.manifest)
        if args.only_failed is not None:
            entries = failed_entries(args.only_failed, entries)
        entries = select_entries(entries, args.include, args.exclude, args.limit)
        # Validate every destination before writing anything.
        root = args.output.absolute()
        destinations = [safe_destination(root, name) for _, name, _ in entries]
        report_path = args.failed_report.absolute()
        if (report_path == root or report_path in destinations
                or report_path in (args.manifest.absolute(), args.cookies.absolute())):
            raise ValueError("Failure report conflicts with an input or download")
        if report_path.is_symlink():
            raise ValueError("Failure report must not be a symlink")
        if args.only_failed and args.only_failed.absolute() == report_path and not args.dry_run:
            raise ValueError("Use a different --failed-report when retrying failures")
        temporary_paths = {
            target.with_name(target.name + ".download") for target in destinations
        }
        part_paths = {Path(str(path) + ".part") for path in temporary_paths}
        reserved_paths = temporary_paths | part_paths
        if (report_path in reserved_paths or any(target in reserved_paths for target in destinations)
                or args.manifest.absolute() in reserved_paths
                or args.cookies.absolute() in reserved_paths):
            raise ValueError("Temporary download path conflicts with an input, entry or report")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    if args.dry_run:
        for _, name, expected in entries:
            print(f"PLAN {name}" + (" [SHA-256]" if expected else ""))
        print(f"Selected {len(entries)} entries; no files changed")
        return 0
    if args.verify_only:
        failures = []
        for (file_id, name, expected), target in zip(entries, destinations):
            try:
                safe_destination(root, name)
                if not target.is_file() or target.stat().st_size == 0:
                    error = "missing or empty"
                elif expected is not None and digest(target) != expected:
                    error = "SHA-256 mismatch"
                else:
                    print(f"VALID {name}" + (" [SHA-256]" if expected else " [non-empty]"))
                    continue
            except OSError as exc:
                error = str(exc)
            failures.append({"id": file_id, "path": name, "error": error})
            print(f"INVALID {name}: {error}", file=sys.stderr)
        print(f"Verified {len(entries) - len(failures)}/{len(entries)} selected entries")
        # Verification is read-only; no output directory or report is created.
        return 1 if failures else 0
    if entries and not args.cookies.is_file():
        parser.error(f"Cookie file not found: {args.cookies}")
    root.mkdir(parents=True, exist_ok=True)
    failures = []
    for (file_id, name, expected), target in zip(entries, destinations):
        try:
            # Recheck to reject symlinks introduced after initial validation.
            safe_destination(root, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            safe_destination(root, name)
            if target.is_file() and target.stat().st_size > 0 and not args.force:
                if expected is None or digest(target) == expected:
                    print(f"SKIP {name}")
                    continue
                print(f"REPLACE checksum mismatch: {name}", file=sys.stderr)
            temporary = target.with_name(target.name + ".download")
            partial = Path(str(temporary) + ".part")
            if temporary.is_symlink() or partial.is_symlink() or target.is_symlink():
                raise ValueError("Symlink at target or temporary download")
            success = False
            error = "download failed"
            for attempt in range(args.retries):
                # yt-dlp can resume .part across attempts and subsequent invocations.
                # A completed .download left by an interrupted run is also usable,
                # but only after its optional digest has been checked.
                if temporary.is_file() and temporary.stat().st_size > 0:
                    if expected is None or digest(temporary) == expected:
                        if target.is_symlink():
                            raise ValueError("Destination became symlink")
                        os.replace(temporary, target)
                        success = True
                        break
                    temporary.unlink()
                    # The completed artifact failed verification; discard stale
                    # partial state rather than resuming corrupted bytes.
                    partial.unlink(missing_ok=True)
                command = [
                    sys.executable, "-m", "yt_dlp", "--cookies", str(args.cookies),
                    "--no-playlist", "--continue", "--no-overwrites",
                    "--format", "best[ext=mp4]/best", "-o", str(temporary),
                    f"https://drive.google.com/file/d/{file_id}/view",
                ]
                result = subprocess.run(command, check=False)
                if temporary.is_symlink() or partial.is_symlink() or target.is_symlink():
                    raise ValueError("Symlink introduced during download")
                if result.returncode == 0 and temporary.is_file() and temporary.stat().st_size > 0:
                    if expected is None or digest(temporary) == expected:
                        os.replace(temporary, target)
                        success = True
                        break
                    error = "SHA-256 mismatch"
                    temporary.unlink()
                    partial.unlink(missing_ok=True)
                else:
                    error = f"yt-dlp exit status {result.returncode}"
                    # Do not trust an incomplete non-.part file on retry.
                    # Retain the resumable .part file produced by yt-dlp.
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
