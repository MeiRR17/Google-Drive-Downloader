#!/usr/bin/env python3
"""Download an explicit JSON manifest of Google Drive files with integrity checks."""

import argparse
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import time
import unicodedata

FILE_ID = re.compile(r"^[A-Za-z0-9_-]{10,128}$")
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
RATE_LIMIT = re.compile(r"^[1-9][0-9]*(?:[KMG])?$", re.IGNORECASE)
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
WINDOWS_INVALID = set('<>:"|?*')


def validate_relative_path(relative: str) -> str:
    """Validate a portable destination independent of the host filesystem."""
    if not isinstance(relative, str) or not relative:
        raise ValueError("Invalid destination path")
    normalized = relative.replace("\\", "/")
    components = normalized.split("/")
    if normalized.startswith("/") or any(part in ("", ".", "..") for part in components):
        raise ValueError(f"Unsafe destination: {relative!r}")
    for part in components:
        if (part.endswith((" ", ".")) or any(
            char in WINDOWS_INVALID or ord(char) < 32 or ord(char) == 127
            for char in part
        ) or part.split(".", 1)[0].upper() in WINDOWS_RESERVED):
            raise ValueError(f"Non-portable destination: {relative!r}")
    return normalized



def safe_destination(root: Path, relative: str) -> Path:
    normalized = validate_relative_path(relative)
    segments = normalized.split("/")
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


def temporary_paths(target: Path, file_id: str):
    """Give each source file its own resumable temporary download namespace."""
    token = hashlib.sha256(file_id.encode("ascii")).hexdigest()[:16]
    staging = target.with_name(target.name + "." + token + ".download")
    return staging, Path(str(staging) + ".part")


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
        normalized = validate_relative_path(name)
        key = unicodedata.normalize("NFC", normalized).casefold()
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


def select_entries(entries, includes, excludes, limit, offset=0):
    """Filter manifest paths in their original order, using POSIX-style separators.

    Shell-style patterns are matched against the entire manifest path; glob
    wildcards are case-sensitive and do not change the destination on disk.
    """
    selected = []
    matched = 0
    for entry in entries:
        path = entry[1].replace("\\", "/")
        if includes and not any(fnmatch.fnmatchcase(path, pattern) for pattern in includes):
            continue
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in excludes):
            continue
        if matched < offset:
            matched += 1
            continue
        selected.append(entry)
        if limit is not None and len(selected) >= limit:
            break
    return selected


def append_progress(path: Path, event: dict):
    """Append a complete JSONL event after each processed entry."""
    if path.is_symlink():
        raise ValueError("Progress log must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        stream.flush()


def write_report(path: Path, failures):
    """Atomically replace a failure report without using a predictable temp file."""
    if path.is_symlink():
        raise ValueError("Failure report must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".failed-report-", suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump({"failed": failures}, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
        if path.is_symlink():
            raise ValueError("Failure report became a symlink")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="JSON manifest containing files [{id,path,sha256?}]")
    parser.add_argument("--output", type=Path, default=Path("downloads"))
    parser.add_argument("--cookies", type=Path, default=Path("cookies.txt"))
    parser.add_argument("--failed-report", type=Path, default=Path("failed-downloads.json"))
    parser.add_argument("--checkpoint", action="store_true",
                        help="Update failure report after each file, including pending entries")
    parser.add_argument("--progress-log", type=Path,
                        help="Append a JSONL record after each download, skip or failure")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--max-failures", type=int, metavar="N",
                        help="Stop after N failed files and retain the remaining retry list")
    parser.add_argument("--backoff", type=float, default=2.0)
    parser.add_argument("--file-timeout", type=float, metavar="SECONDS",
                        help="Maximum wall-clock seconds per yt-dlp attempt")
    parser.add_argument("--limit-rate", metavar="RATE",
                        help="Limit yt-dlp transfer speed, e.g. 500K or 2M bytes/second")
    parser.add_argument("--sleep-between-files", type=float, default=0.0,
                        metavar="SECONDS",
                        help="Pause between attempted files to reduce request pressure")
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
    parser.add_argument("--offset", type=int, default=0, metavar="N",
                        help="Skip the first N entries after path filtering (default: 0)")
    parser.add_argument("--force", action="store_true",
                        help="Re-download selected files even when a destination already exists")
    parser.add_argument("--verify-only", action="store_true",
                        help="Audit local files and optional checksums without network access")
    args = parser.parse_args(argv)
    if args.retries < 1 or args.backoff < 0:
        parser.error("--retries must be >= 1 and --backoff must be >= 0")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")
    if args.offset < 0:
        parser.error("--offset must be >= 0")
    if args.max_failures is not None and args.max_failures < 1:
        parser.error("--max-failures must be >= 1")
    if args.file_timeout is not None and not (0 < args.file_timeout < float("inf")):
        parser.error("--file-timeout must be a finite positive number")
    if args.limit_rate is not None and not RATE_LIMIT.fullmatch(args.limit_rate):
        parser.error("--limit-rate must be a positive integer optionally suffixed K, M or G")
    if not (0 <= args.sleep_between_files < float("inf")):
        parser.error("--sleep-between-files must be a finite non-negative number")
    if args.verify_only and args.force:
        parser.error("--verify-only cannot be combined with --force")
    if args.verify_only and args.dry_run:
        parser.error("--verify-only cannot be combined with --dry-run")
    if args.checkpoint and (args.verify_only or args.dry_run):
        parser.error("--checkpoint requires a download run")

    try:
        entries = load_manifest(args.manifest)
        if args.only_failed is not None:
            entries = failed_entries(args.only_failed, entries)
        entries = select_entries(entries, args.include, args.exclude, args.limit, args.offset)
        # Validate every destination before writing anything.
        root = args.output.absolute()
        destinations = [safe_destination(root, name) for _, name, _ in entries]
        report_path = args.failed_report.absolute()
        progress_path = args.progress_log.absolute() if args.progress_log else None
        if (report_path == root or report_path in destinations
                or report_path in (args.manifest.absolute(), args.cookies.absolute())):
            raise ValueError("Failure report conflicts with an input or download")
        if report_path.is_symlink():
            raise ValueError("Failure report must not be a symlink")
        if progress_path is not None:
            if (progress_path.is_symlink() or progress_path in destinations
                    or progress_path in (root, report_path, args.manifest.absolute(),
                                         args.cookies.absolute())
                    or (args.only_failed and progress_path == args.only_failed.absolute())):
                raise ValueError("Progress log conflicts with an input, report or download")
        if args.only_failed and args.only_failed.absolute() == report_path and not args.dry_run:
            raise ValueError("Use a different --failed-report when retrying failures")
        staging_paths = {
            temporary_paths(target, file_id)[0]
            for (file_id, _, _), target in zip(entries, destinations)
        }
        part_paths = {
            temporary_paths(target, file_id)[1]
            for (file_id, _, _), target in zip(entries, destinations)
        }
        reserved_paths = staging_paths | part_paths
        if (report_path in reserved_paths or any(target in reserved_paths for target in destinations)
                or args.manifest.absolute() in reserved_paths
                or args.cookies.absolute() in reserved_paths
                or (progress_path is not None and progress_path in reserved_paths)):
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
    pending = {
        (file_id, name): {"id": file_id, "path": name, "error": "pending"}
        for file_id, name, _ in entries
    }
    if args.checkpoint:
        write_report(report_path, list(pending.values()))
    processed = 0
    stopped_early = False
    for index, ((file_id, name, expected), target) in enumerate(zip(entries, destinations)):
        status = "failed"
        error = None
        try:
            # Recheck to reject symlinks introduced after initial validation.
            safe_destination(root, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            safe_destination(root, name)
            if target.is_file() and target.stat().st_size > 0 and not args.force:
                if expected is None or digest(target) == expected:
                    print(f"SKIP {name}")
                    if progress_path is not None:
                        append_progress(progress_path, {
                            "id": file_id, "path": name, "status": "skipped"
                        })
                    pending.pop((file_id, name))
                    processed += 1
                    if args.checkpoint:
                        write_report(report_path, failures + list(pending.values()))
                    continue
                print(f"REPLACE checksum mismatch: {name}", file=sys.stderr)
            temporary, partial = temporary_paths(target, file_id)
            if temporary.is_symlink() or partial.is_symlink() or target.is_symlink():
                raise ValueError("Symlink at target or temporary download")
            success = False
            error = "download failed"
            for attempt in range(args.retries):
                # yt-dlp can resume .part across attempts and subsequent invocations.
                # A completed source-specific .download left by interruption can
                # be reused, after checking the optional manifest digest.
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
                ]
                if args.limit_rate is not None:
                    command.extend(["--limit-rate", args.limit_rate.upper()])
                command.append(f"https://drive.google.com/file/d/{file_id}/view")
                try:
                    result = subprocess.run(
                        command, check=False, timeout=args.file_timeout
                    )
                except subprocess.TimeoutExpired:
                    # subprocess.run terminates the timed-out yt-dlp process.
                    # Retain its .part file so the next attempt can continue.
                    error = f"yt-dlp timed out after {args.file_timeout:g} seconds"
                    if temporary.is_symlink() or partial.is_symlink() or target.is_symlink():
                        raise ValueError("Symlink introduced during download")
                    temporary.unlink(missing_ok=True)
                    if attempt + 1 < args.retries:
                        time.sleep(args.backoff * (2 ** attempt) + random.uniform(0, 0.5))
                    continue
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
                status = "downloaded"
                print(f"OK   {name}")
            else:
                failures.append({"id": file_id, "path": name, "error": error})
                print(f"FAIL {name}: {error}", file=sys.stderr)
        except (OSError, ValueError) as exc:
            error = str(exc)
            failures.append({"id": file_id, "path": name, "error": error})
            print(f"FAIL {name}: {exc}", file=sys.stderr)
        if progress_path is not None:
            event = {"id": file_id, "path": name, "status": status}
            if status == "failed":
                event["error"] = error
            append_progress(progress_path, event)
        pending.pop((file_id, name))
        processed += 1
        if args.checkpoint:
            write_report(report_path, failures + list(pending.values()))
        if args.max_failures is not None and len(failures) >= args.max_failures:
            stopped_early = True
            print(
                f"STOP: reached --max-failures={args.max_failures}; "
                f"{len(pending)} entries remain pending",
                file=sys.stderr
            )
            break
        if args.sleep_between_files and index + 1 < len(entries):
            time.sleep(args.sleep_between_files)
    if not args.checkpoint:
        write_report(report_path, failures + list(pending.values()))
    print(
        f"Completed: {processed - len(failures)}/{processed} processed successfully; "
        f"{len(pending)} pending of {len(entries)} selected"
    )
    return 1 if failures or stopped_early else 0


if __name__ == "__main__":
    sys.exit(main())
