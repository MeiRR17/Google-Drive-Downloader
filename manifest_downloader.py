#!/usr/bin/env python3
"""Download an explicit JSON manifest of Google Drive files with integrity checks."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import stat
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



def validate_directory_chain(directory: Path, label: str):
    """Reject symlinks, junctions, and non-directories in a parent chain.

    Check with lstat rather than following links: even a symlink outside the
    configured output root can redirect a seemingly safe destination.
    """
    current = directory
    while True:
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            pass
        else:
            if (not stat.S_ISDIR(mode)
                    or getattr(current, "is_junction", lambda: False)()):
                raise ValueError(f"{label} has an unsafe directory component: {current}")
        if current == current.parent:
            break
        current = current.parent


def safe_destination(root: Path, relative: str) -> Path:
    normalized = validate_relative_path(relative)
    segments = normalized.split("/")
    validate_directory_chain(root, "Output root")
    current = root
    for index, segment in enumerate(segments):
        current = current / segment
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        if (index == len(segments) - 1
                and not stat.S_ISREG(mode)):
            raise ValueError(f"Destination must be a regular file: {relative!r}")
        if index < len(segments) - 1 and (
            not stat.S_ISDIR(mode)
            or getattr(current, "is_junction", lambda: False)()
        ):
            raise ValueError(f"Unsafe directory in output path: {relative!r}")
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


def validate_manifest_namespace(entries):
    """Reject file/directory and staging collisions before any batch filtering.

    Paths are compared using portable, NFC-normalized case-insensitive names,
    including the source-specific .download and .part staging namespaces.
    """
    occupied = {}
    for index, (file_id, name, _, _) in enumerate(entries, 1):
        normalized = validate_relative_path(name)
        token = hashlib.sha256(file_id.encode("ascii")).hexdigest()[:16]
        for kind, candidate in (
            ("destination", normalized),
            ("temporary download", normalized + "." + token + ".download"),
            ("partial download", normalized + "." + token + ".download.part"),
        ):
            key = unicodedata.normalize("NFC", candidate).casefold()
            previous = occupied.get(key)
            if previous is not None:
                raise ValueError(
                    f"Entry {index}: {kind} {candidate!r} conflicts with {previous}"
                )
            occupied[key] = f"entry {index} {kind} {candidate!r}"

    lock_key = ".manifest-downloader.lock"
    if lock_key in occupied:
        raise ValueError(f"Manifest conflicts with reserved downloader lock: {occupied[lock_key]}")

    for key, description in occupied.items():
        components = key.split("/")
        for depth in range(1, len(components)):
            parent = "/".join(components[:depth])
            if parent in occupied:
                raise ValueError(
                    f"File/directory collision: {description} is nested under "
                    f"{occupied[parent]}"
                )


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
        size_bytes = entry.get("size_bytes")
        if not isinstance(file_id, str) or not FILE_ID.fullmatch(file_id):
            raise ValueError(f"Entry {index}: invalid Drive file ID")
        if not isinstance(name, str):
            raise ValueError(f"Entry {index}: path must be a string")
        if checksum is not None and (not isinstance(checksum, str) or not SHA256.fullmatch(checksum)):
            raise ValueError(f"Entry {index}: invalid SHA-256")
        if size_bytes is not None and (
            type(size_bytes) is not int or size_bytes < 1
        ):
            raise ValueError(f"Entry {index}: size_bytes must be a positive integer")
        normalized = validate_relative_path(name)
        key = unicodedata.normalize("NFC", normalized).casefold()
        if key in destinations:
            raise ValueError(f"Entry {index}: duplicate destination {name!r}")
        destinations.add(key)
        result.append((file_id, name, checksum.lower() if checksum else None, size_bytes))
    validate_manifest_namespace(result)
    return result


def portable_path_parts(path: Path):
    """Canonicalize absolute path components for portable collision checks.

    This deliberately compares case-insensitively on all platforms, so a
    manifest that is safe on Linux will also be safe on default macOS/Windows
    filesystems.  Lexical normalization does not follow filesystem symlinks.
    """
    normalized = Path(os.path.abspath(path))
    return tuple(unicodedata.normalize("NFC", part).casefold() for part in normalized.parts)


def portable_paths_overlap(left: Path, right: Path) -> bool:
    """Return true for same-file or file/directory ancestor collisions."""
    a = portable_path_parts(left)
    b = portable_path_parts(right)
    return a[:len(b)] == b or b[:len(a)] == a


def validate_control_collisions(root: Path, entries, control_paths):
    """Protect inputs and metadata from the entire manifest, not just this batch.

    A control file cannot occupy a download destination, a resumable artifact,
    or a directory needed to store any of them.
    """
    artifacts = [(root / ".manifest-downloader.lock", "download lock")]
    for file_id, name, _, _ in entries:
        destination = root.joinpath(*validate_relative_path(name).split("/"))
        temporary, partial = temporary_paths(destination, file_id)
        artifacts.extend([
            (destination, f"download {name!r}"),
            (temporary, f"staged download {name!r}"),
            (partial, f"partial download {name!r}"),
        ])

    controls = [(label, path) for label, path in control_paths if path is not None]
    for label, path in controls:
        if portable_path_parts(path) == portable_path_parts(root):
            raise ValueError(f"{label} may not be the output directory")
        for artifact, description in artifacts:
            if portable_paths_overlap(path, artifact):
                raise ValueError(f"{label} {path} conflicts with {description} {artifact}")
    for index, (label, path) in enumerate(controls):
        for other_label, other_path in controls[index + 1:]:
            if portable_paths_overlap(path, other_path):
                raise ValueError(f"{label} {path} conflicts with {other_label} {other_path}")


def manifest_fingerprint(entries) -> str:
    """Fingerprint the complete validated manifest in its original file order."""
    content = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def failed_entries(report_path: Path, entries, reconcile=False):
    """Select reported failures; require the original manifest unless opted out."""
    data = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("failed"), list):
        raise ValueError("Failure report must contain a failed array")
    if data.get("manifest_sha256") != manifest_fingerprint(entries):
        if not reconcile:
            raise ValueError(
                "Failure report is missing a matching manifest_sha256 fingerprint; "
                "create a new failure report for the current manifest, or explicitly "
                "use --reconcile-failed to match IDs and paths against the new manifest"
            )
        print(
            "WARNING: retry report manifest fingerprint differs; reconciling only "
            "exact Drive ID and destination path matches under current integrity rules",
            file=sys.stderr,
        )
    known = {(file_id, path) for file_id, path, _, _ in entries}
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


def safe_artifact_path(path: Path, label: str):
    """Reject non-regular metadata files and symlinked parent directories."""
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        pass
    else:
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"{label} must be a regular file path: {path}")
    validate_directory_chain(path.parent, label)


def append_progress(path: Path, event: dict):
    """Append a JSONL event without following a substituted symlink on POSIX."""
    safe_artifact_path(path, "Progress log")
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_artifact_path(path, "Progress log")
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    # O_NOFOLLOW protects the final pathname on supporting platforms.
    # O_NONBLOCK avoids hanging when a file is replaced with a FIFO.
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"Progress log is not a regular file: {path}")
        with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
            descriptor = None
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            stream.flush()
    finally:
        if descriptor is not None:
            os.close(descriptor)


def validate_staging_paths(target: Path, temporary: Path, partial: Path):
    """Only ordinary files may occupy final or source-scoped staging paths.

    lstat avoids following symbolic links or special files while inspecting
    interrupted transfers before they are reused, deleted, or replaced.
    """
    for name, path in (
        ("destination", target),
        ("staged download", temporary),
        ("partial download", partial),
    ):
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"{name} must be a regular file: {path}")


def discard_oversized_partial(temporary: Path, partial: Path, expected_size, max_size):
    """Reject impossible resumptions before they consume more transfer bandwidth."""
    if not partial.is_file():
        return None
    actual = partial.stat().st_size
    if expected_size is not None and actual > expected_size:
        error = f"partial download exceeds manifest size_bytes ({actual} > {expected_size})"
    elif max_size is not None and actual > max_size:
        error = f"partial download exceeds --max-file-mib ({actual} > {max_size})"
    else:
        return None
    # Only remove source-scoped temporary artifacts, never the destination.
    temporary.unlink(missing_ok=True)
    partial.unlink(missing_ok=True)
    return error


def retry_delay(backoff: float, attempt: int, maximum: float) -> float:
    """Bound exponential retry waits, including jitter, without overflow."""
    if backoff == 0:
        return min(maximum, random.uniform(0, 0.5))
    if backoff >= maximum:
        return maximum
    # Once the exponential reaches the cap, avoid unbounded integers.
    exponent = min(attempt, 60)
    return min(maximum, backoff * (2 ** exponent) + random.uniform(0, 0.5))


def record_progress(path: Path, event: dict) -> bool:
    """Attempt journaling; report an I/O failure without aborting recovery state."""
    try:
        append_progress(path, event)
    except (OSError, ValueError) as exc:
        print(f"PROGRESS LOG ERROR {path}: {exc}", file=sys.stderr)
        return False
    return True


def write_json_document(path: Path, document: dict, *, label: str, durable=False):
    """Atomically replace metadata JSON with optional crash-durability syncs."""
    safe_artifact_path(path, label)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_artifact_path(path, label)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".manifest-report-", suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            if durable:
                os.fsync(stream.fileno())
        safe_artifact_path(path, label)
        os.replace(temporary, path)
        if durable and os.name == "posix":
            directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_report(path: Path, failures, manifest_sha256, *, durable=False):
    """Persist a manifest-bound recovery report."""
    write_json_document(
        path, {"manifest_sha256": manifest_sha256, "failed": failures},
        label="Failure report", durable=durable
    )


@contextmanager
def download_lock(root: Path):
    """Prevent cooperative download runs from modifying the same output root."""
    lock_path = root / ".manifest-downloader.lock"
    try:
        descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise SystemExit(
            f"Download directory is locked: {lock_path}. "
            "If no download is running, remove the stale lock manually."
        )
    identity = os.fstat(descriptor)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(f"pid={os.getpid()}\n")
            stream.flush()
        yield
    finally:
        try:
            stat = os.lstat(lock_path)
            if (stat.st_dev, stat.st_ino) == (identity.st_dev, identity.st_ino):
                lock_path.unlink()
        except FileNotFoundError:
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="JSON manifest containing files [{id,path,sha256?}]")
    parser.add_argument("--output", type=Path, default=Path("downloads"))
    parser.add_argument("--cookies", type=Path, default=Path("cookies.txt"))
    parser.add_argument("--no-cookies", action="store_true",
                        help="Download public Drive files without an authentication cookie file")
    parser.add_argument("--failed-report", type=Path, default=Path("failed-downloads.json"))
    parser.add_argument("--checkpoint", action="store_true",
                        help="Update failure report after each file, including pending entries")
    parser.add_argument("--durable-reports", action="store_true",
                        help="fsync recovery reports before rename and sync parent directory on POSIX")
    parser.add_argument("--progress-log", type=Path,
                        help="Append a JSONL record after each download, skip or failure")
    parser.add_argument("--summary-json", type=Path, metavar="PATH",
                        help="Write a machine-readable JSON summary after a download batch")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--max-failures", type=int, metavar="N",
                        help="Stop after N failed files and retain the remaining retry list")
    parser.add_argument("--max-consecutive-failures", type=int, metavar="N",
                        help="Stop after N files fail in a row; successful skips reset the count")
    parser.add_argument("--max-total-mib", type=int, metavar="MIB",
                        help="Stop batch after its new downloads reach MIB MiB")
    parser.add_argument("--max-new-files", type=int, metavar="N",
                        help="Stop batch after N newly completed files; verified skips do not count")
    parser.add_argument("--max-run-seconds", type=float, metavar="SECONDS",
                        help="Stop at a file boundary after SECONDS of batch processing")
    parser.add_argument("--backoff", type=float, default=2.0)
    parser.add_argument("--max-backoff", type=float, default=60.0, metavar="SECONDS",
                        help="Maximum wait between retries, including jitter (default: 60)")
    parser.add_argument("--file-timeout", type=float, metavar="SECONDS",
                        help="Maximum wall-clock seconds per yt-dlp attempt")
    parser.add_argument("--limit-rate", metavar="RATE",
                        help="Limit yt-dlp transfer speed, e.g. 500K or 2M bytes/second")
    parser.add_argument("--max-file-mib", type=int, metavar="MIB",
                        help="Reject downloads larger than MIB mebibytes (1 MiB = 1048576 bytes)")
    parser.add_argument("--min-free-mib", type=int, metavar="MIB",
                        help="Preserve at least MIB MiB of available disk space before transfers")
    parser.add_argument("--sleep-between-files", type=float, default=0.0,
                        metavar="SECONDS",
                        help="Pause between attempted files to reduce request pressure")
    parser.add_argument("--only-failed", type=Path, metavar="REPORT",
                        help="Retry only entries listed in a previous failure report")
    parser.add_argument("--reconcile-failed", action="store_true",
                        help="Explicitly allow changed/legacy retry reports for exact ID/path matches")
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
    parser.add_argument("--restart-partials", action="store_true",
                        help="Discard selected resumable staging data before downloading")
    parser.add_argument("--verify-only", action="store_true",
                        help="Audit local files and optional checksums without network access")
    parser.add_argument("--require-integrity", action="store_true",
                        help="Require both SHA-256 and exact size_bytes for every selected file")
    args = parser.parse_args(argv)
    if args.retries < 1:
        parser.error("--retries must be >= 1")
    if not math.isfinite(args.backoff) or args.backoff < 0:
        parser.error("--backoff must be a finite non-negative number")
    if not math.isfinite(args.max_backoff) or args.max_backoff <= 0:
        parser.error("--max-backoff must be a finite positive number")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")
    if args.offset < 0:
        parser.error("--offset must be >= 0")
    if args.max_failures is not None and args.max_failures < 1:
        parser.error("--max-failures must be >= 1")
    if args.max_consecutive_failures is not None and args.max_consecutive_failures < 1:
        parser.error("--max-consecutive-failures must be >= 1")
    if args.max_total_mib is not None and args.max_total_mib < 1:
        parser.error("--max-total-mib must be >= 1")
    if args.max_new_files is not None and args.max_new_files < 1:
        parser.error("--max-new-files must be >= 1")
    if args.max_run_seconds is not None and (
        not math.isfinite(args.max_run_seconds) or args.max_run_seconds <= 0
    ):
        parser.error("--max-run-seconds must be a finite positive number")
    budget_bytes = args.max_total_mib * 1024 * 1024 if args.max_total_mib else None
    if args.max_file_mib is not None and args.max_file_mib < 1:
        parser.error("--max-file-mib must be >= 1")
    if args.min_free_mib is not None and args.min_free_mib < 1:
        parser.error("--min-free-mib must be >= 1")
    max_file_bytes = args.max_file_mib * 1024 * 1024 if args.max_file_mib else None
    reserve_bytes = args.min_free_mib * 1024 * 1024 if args.min_free_mib else None
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
    if args.durable_reports and (args.verify_only or args.dry_run):
        parser.error("--durable-reports requires a download run")
    if args.summary_json is not None and (args.verify_only or args.dry_run):
        parser.error("--summary-json requires a download run")
    if args.reconcile_failed and args.only_failed is None:
        parser.error("--reconcile-failed requires --only-failed REPORT")

    try:
        entries = load_manifest(args.manifest)
        manifest_sha256 = manifest_fingerprint(entries)
        root = args.output.absolute()
        report_path = args.failed_report.absolute()
        progress_path = args.progress_log.absolute() if args.progress_log else None
        summary_path = args.summary_json.absolute() if args.summary_json else None
        manifest_path = args.manifest.absolute()
        cookie_path = args.cookies.absolute() if not args.no_cookies else None
        failed_input_path = args.only_failed.absolute() if args.only_failed else None
        validate_control_collisions(root, entries, [
            ("Manifest", manifest_path),
            ("Cookies", cookie_path),
            ("Failure report", report_path),
            ("Progress log", progress_path),
            ("Batch summary", summary_path),
            ("Retry input", failed_input_path),
        ])
        if args.only_failed is not None:
            entries = failed_entries(args.only_failed, entries, reconcile=args.reconcile_failed)
        entries = select_entries(entries, args.include, args.exclude, args.limit, args.offset)
        if args.require_integrity:
            for file_id, name, checksum, size_bytes in entries:
                missing = []
                if checksum is None:
                    missing.append("sha256")
                if size_bytes is None:
                    missing.append("size_bytes")
                if missing:
                    raise ValueError(
                        f"{name!r} ({file_id}) missing required integrity metadata: "
                        + ", ".join(missing)
                    )
        # Validate every destination before writing anything.
        root = args.output.absolute()
        destinations = [safe_destination(root, name) for _, name, _, _ in entries]
        report_path = args.failed_report.absolute()
        progress_path = args.progress_log.absolute() if args.progress_log else None
        if (report_path == root or report_path in destinations
                or report_path in (args.manifest.absolute(), args.cookies.absolute())):
            raise ValueError("Failure report conflicts with an input or download")
        safe_artifact_path(report_path, "Failure report")
        if summary_path is not None:
            safe_artifact_path(summary_path, "Batch summary")
        if progress_path is not None:
            safe_artifact_path(progress_path, "Progress log")
            if (progress_path in destinations
                    or progress_path in (root, report_path, args.manifest.absolute(),
                                         args.cookies.absolute())
                    or (args.only_failed and progress_path == args.only_failed.absolute())):
                raise ValueError("Progress log conflicts with an input, report or download")
        if args.only_failed and args.only_failed.absolute() == report_path and not args.dry_run:
            raise ValueError("Use a different --failed-report when retrying failures")
        staging_paths = {
            temporary_paths(target, file_id)[0]
            for (file_id, _, _, _), target in zip(entries, destinations)
        }
        part_paths = {
            temporary_paths(target, file_id)[1]
            for (file_id, _, _, _), target in zip(entries, destinations)
        }
        reserved_paths = staging_paths | part_paths
        lock_path = root / ".manifest-downloader.lock"
        if (lock_path in destinations or lock_path in reserved_paths
                or lock_path in (report_path, args.manifest.absolute(), args.cookies.absolute())
                or lock_path == progress_path):
            raise ValueError("Download lock path conflicts with a manifest entry or input")
        if (report_path in reserved_paths or any(target in reserved_paths for target in destinations)
                or args.manifest.absolute() in reserved_paths
                or args.cookies.absolute() in reserved_paths
                or (progress_path is not None and progress_path in reserved_paths)):
            raise ValueError("Temporary download path conflicts with an input, entry or report")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    if args.dry_run:
        for _, name, expected, size_bytes in entries:
            markers = []
            if expected:
                markers.append("SHA-256")
            if size_bytes is not None:
                markers.append(f"{size_bytes} bytes")
            print(f"PLAN {name}" + (f" [{' / '.join(markers)}]" if markers else ""))
        print(f"Selected {len(entries)} entries; no files changed")
        return 0
    if args.verify_only:
        failures = []
        for (file_id, name, expected, size_bytes), target in zip(entries, destinations):
            try:
                safe_destination(root, name)
                if not target.is_file() or target.stat().st_size == 0:
                    error = "missing or empty"
                elif size_bytes is not None and target.stat().st_size != size_bytes:
                    error = "size_bytes mismatch"
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
    if entries and not args.no_cookies and not args.cookies.is_file():
        parser.error(f"Cookie file not found: {args.cookies}")
    validate_directory_chain(root, "Output root")
    root.mkdir(parents=True, exist_ok=True)
    validate_directory_chain(root, "Output root")
    with download_lock(root):
        failures = []
        pending = {
            (file_id, name): {"id": file_id, "path": name, "error": "pending"}
            for file_id, name, _, _ in entries
        }
        if args.checkpoint:
            write_report(report_path, list(pending.values()), manifest_sha256,
                         durable=args.durable_reports)
        processed = 0
        stopped_early = False
        consecutive_failures = 0
        stopped_budget = False
        stopped_time = False
        started_at = time.monotonic()
        downloaded_bytes = 0
        downloaded_files = 0
        skipped_files = 0
        stop_reason = None
        journal_failed = False
        interrupted = False
        try:
            for index, ((file_id, name, expected, size_bytes), target) in enumerate(zip(entries, destinations)):
                if (args.max_run_seconds is not None
                        and time.monotonic() - started_at >= args.max_run_seconds):
                    stopped_time = True
                    stop_reason = "time_budget"
                    print(
                        f"STOP: batch time budget of {args.max_run_seconds:g} seconds reached",
                        file=sys.stderr
                    )
                    break
                status = "failed"
                error = None
                try:
                    # Recheck to reject symlinks introduced after initial validation.
                    safe_destination(root, name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    safe_destination(root, name)
                    if target.is_file() and target.stat().st_size > 0 and not args.force:
                        if ((size_bytes is None or target.stat().st_size == size_bytes)
                                and (expected is None or digest(target) == expected)):
                            print(f"SKIP {name}")
                            if progress_path is not None:
                                if not record_progress(progress_path, {
                                    "id": file_id, "path": name, "status": "skipped"
                                }):
                                    journal_failed = True
                                    progress_path = None
                            consecutive_failures = 0
                            skipped_files += 1
                            pending.pop((file_id, name))
                            processed += 1
                            if args.checkpoint:
                                write_report(report_path, failures + list(pending.values()), manifest_sha256,
                                 durable=args.durable_reports)
                            continue
                        print(f"REPLACE integrity mismatch: {name}", file=sys.stderr)
                    # Reject impossible manifest sizes without starting yt-dlp.
                    if max_file_bytes is not None and size_bytes is not None and size_bytes > max_file_bytes:
                        raise ValueError(
                            f"manifest size_bytes ({size_bytes}) exceeds "
                            f"--max-file-mib ({max_file_bytes} bytes)"
                        )
                    # Batch budgets limit new downloads, not inspection or
                    # skipping of already verified local destinations.
                    if args.max_new_files is not None and downloaded_files >= args.max_new_files:
                        stopped_budget = True
                        stop_reason = "new_file_budget"
                        print(
                            f"STOP: reached --max-new-files={args.max_new_files}; "
                            f"{len(pending)} entries remain pending",
                            file=sys.stderr,
                        )
                        break
                    if budget_bytes is not None and downloaded_bytes >= budget_bytes:
                        stopped_budget = True
                        stop_reason = "byte_budget"
                        print("STOP: download byte budget reached", file=sys.stderr)
                        break
                    if (budget_bytes is not None and size_bytes is not None
                            and size_bytes > budget_bytes - downloaded_bytes):
                        stopped_budget = True
                        stop_reason = "byte_budget"
                        print(
                            f"STOP: {name} requires {size_bytes} bytes; "
                            f"{budget_bytes - downloaded_bytes} remain in batch budget",
                            file=sys.stderr
                        )
                        break
                    temporary, partial = temporary_paths(target, file_id)
                    validate_staging_paths(target, temporary, partial)
                    if args.restart_partials or args.force:
                        # Force means genuinely fetch again; a completed old staging
                        # artifact must not silently satisfy the replacement request.
                        # Discard only the source-scoped staging paths, never target.
                        temporary.unlink(missing_ok=True)
                        partial.unlink(missing_ok=True)
                    success = False
                    error = "download failed"
                    for attempt in range(args.retries):
                        validate_staging_paths(target, temporary, partial)
                        error = discard_oversized_partial(
                            temporary, partial, size_bytes, max_file_bytes
                        )
                        if error is not None:
                            break
                        # yt-dlp can resume .part across attempts and subsequent invocations.
                        # A completed source-specific .download left by interruption can
                        # be reused, after checking the optional manifest digest.
                        if temporary.is_file() and temporary.stat().st_size > 0:
                            if (max_file_bytes is not None
                                    and temporary.stat().st_size > max_file_bytes):
                                error = "staged file exceeds --max-file-mib"
                                temporary.unlink()
                                partial.unlink(missing_ok=True)
                                break
                            if ((size_bytes is None or temporary.stat().st_size == size_bytes)
                                    and (expected is None or digest(temporary) == expected)):
                                if target.is_symlink():
                                    raise ValueError("Destination became symlink")
                                os.replace(temporary, target)
                                success = True
                                break
                            temporary.unlink()
                            # The completed artifact failed verification; discard stale
                            # partial state rather than resuming corrupted bytes.
                            partial.unlink(missing_ok=True)
                        if reserve_bytes is not None:
                            # With an exact size, reserve space for the remaining
                            # bytes as well as the minimum requested free capacity.
                            partial_bytes = partial.stat().st_size if partial.is_file() else 0
                            needed = reserve_bytes
                            if size_bytes is not None:
                                needed += max(0, size_bytes - partial_bytes)
                            available = shutil.disk_usage(target.parent).free
                            if available < needed:
                                raise ValueError(
                                    f"Insufficient disk space: {available} bytes free, "
                                    f"{needed} required before transfer"
                                )
                        command = [
                            sys.executable, "-m", "yt_dlp",
                            "--no-playlist", "--continue", "--no-overwrites",
                            "--format", "best[ext=mp4]/best", "-o", str(temporary),
                        ]
                        if not args.no_cookies:
                            command.extend(["--cookies", str(args.cookies)])
                        if args.limit_rate is not None:
                            command.extend(["--limit-rate", args.limit_rate.upper()])
                        if args.max_file_mib is not None:
                            command.extend(["--max-filesize", f"{args.max_file_mib}M"])
                        command.append(f"https://drive.google.com/file/d/{file_id}/view")
                        try:
                            result = subprocess.run(
                                command, check=False, timeout=args.file_timeout
                            )
                        except subprocess.TimeoutExpired:
                            # subprocess.run terminates the timed-out yt-dlp process.
                            # Retain its .part file so the next attempt can continue.
                            error = f"yt-dlp timed out after {args.file_timeout:g} seconds"
                            validate_staging_paths(target, temporary, partial)
                            temporary.unlink(missing_ok=True)
                            oversized = discard_oversized_partial(
                                temporary, partial, size_bytes, max_file_bytes
                            )
                            if oversized is not None:
                                error = oversized
                                break
                            if attempt + 1 < args.retries:
                                time.sleep(retry_delay(args.backoff, attempt, args.max_backoff))
                            continue
                        validate_staging_paths(target, temporary, partial)
                        if max_file_bytes is not None and (
                            (temporary.is_file() and temporary.stat().st_size > max_file_bytes)
                            or (partial.is_file() and partial.stat().st_size > max_file_bytes)
                        ):
                            error = "download exceeds --max-file-mib"
                            temporary.unlink(missing_ok=True)
                            partial.unlink(missing_ok=True)
                            break
                        if result.returncode == 0 and temporary.is_file() and temporary.stat().st_size > 0:
                            if ((size_bytes is None or temporary.stat().st_size == size_bytes)
                                    and (expected is None or digest(temporary) == expected)):
                                os.replace(temporary, target)
                                success = True
                                break
                            error = "size_bytes or SHA-256 mismatch"
                            temporary.unlink()
                            partial.unlink(missing_ok=True)
                        else:
                            error = f"yt-dlp exit status {result.returncode}"
                            # Do not trust an incomplete non-.part file on retry.
                            # Retain the resumable .part file produced by yt-dlp.
                            temporary.unlink(missing_ok=True)
                        if attempt + 1 < args.retries:
                            time.sleep(retry_delay(args.backoff, attempt, args.max_backoff))
                    if success:
                        status = "downloaded"
                        downloaded_files += 1
                        downloaded_bytes += target.stat().st_size
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
                    if not record_progress(progress_path, event):
                        journal_failed = True
                        progress_path = None
                consecutive_failures = consecutive_failures + 1 if status == "failed" else 0
                pending.pop((file_id, name))
                processed += 1
                if args.checkpoint:
                    write_report(report_path, failures + list(pending.values()), manifest_sha256,
                                 durable=args.durable_reports)
                if args.max_failures is not None and len(failures) >= args.max_failures:
                    stopped_early = True
                    stop_reason = "failure_limit"
                    print(
                        f"STOP: reached --max-failures={args.max_failures}; "
                        f"{len(pending)} entries remain pending",
                        file=sys.stderr
                    )
                    break
                if (args.max_consecutive_failures is not None
                        and consecutive_failures >= args.max_consecutive_failures):
                    stopped_early = True
                    stop_reason = "consecutive_failure_limit"
                    print(
                        f"STOP: {consecutive_failures} consecutive failures; "
                        f"{len(pending)} entries remain pending",
                        file=sys.stderr
                    )
                    break
                if args.sleep_between_files and index + 1 < len(entries):
                    time.sleep(args.sleep_between_files)
        except KeyboardInterrupt:
            # The current file stays pending, even if it finished just before
            # interruption; retrying the report will safely skip valid files.
            interrupted = True
            stop_reason = "interrupted"
            print("Interrupted: preserving pending downloads for retry", file=sys.stderr)
        if interrupted or stopped_budget or stopped_time or not args.checkpoint:
            write_report(report_path, failures + list(pending.values()), manifest_sha256,
                                 durable=args.durable_reports)
        exit_code = (
            130 if interrupted else
            1 if failures or stopped_early or stopped_budget or stopped_time or journal_failed
            else 0
        )
        if summary_path is not None:
            write_json_document(
                summary_path,
                {
                    "manifest_sha256": manifest_sha256,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "selected": len(entries),
                    "processed": processed,
                    "downloaded": downloaded_files,
                    "skipped": skipped_files,
                    "failed": len(failures),
                    "pending": len(pending),
                    "downloaded_bytes": downloaded_bytes,
                    "elapsed_seconds": round(time.monotonic() - started_at, 3),
                    "stop_reason": stop_reason,
                    "progress_log_failed": journal_failed,
                    "exit_code": exit_code,
                },
                label="Batch summary",
                durable=args.durable_reports,
            )
        if interrupted:
            print(
                f"Interrupted after {processed}/{len(entries)} entries; "
                f"{len(pending)} pending, {len(failures)} failed. "
                f"Retry with --only-failed {report_path}",
                file=sys.stderr
            )
            return 130
        print(
            f"Completed: {processed - len(failures)}/{processed} processed successfully; "
            f"{len(pending)} pending of {len(entries)} selected; "
            f"{downloaded_files} new files, {downloaded_bytes} new bytes completed"
        )
        return exit_code


if __name__ == "__main__":
    sys.exit(main())
