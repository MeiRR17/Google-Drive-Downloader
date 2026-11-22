> **Script consolidation (2026-11-03):** Selected utility scripts from this repository were integrated into [Learning_Modules/tools/google-drive-downloader](https://github.com/MeiRR17/Learning_Modules/tree/main/tools/google-drive-downloader), via [PR #4](https://github.com/MeiRR17/Learning_Modules/pull/4). The import includes source provenance and CI syntax/content checks. The original repository remains accessible, may contain additional data or configuration, and has **not been archived or deleted**. Consult the consolidated README for exclusions and portability changes.

---

# Google Drive Downloader

A Python script to automatically download video courses from Google Drive using yt-dlp with cookie-based authentication. Maintains the exact folder hierarchy structure locally.

## Features

- Downloads videos from Google Drive using file IDs
- Preserves original folder structure
- Resumable downloads (skips existing files)
- Progress tracking with detailed logs
- Error handling and failed download reporting
- Random throttling to avoid rate limiting

## Prerequisites

- Python 3.7 or higher
- yt-dlp library
- Google Drive cookies (Netscape format)

## Installation

### 1. Install Python

Download and install Python from [python.org](https://www.python.org/downloads/). Make sure to check "Add Python to PATH" during installation.

### 2. Install yt-dlp

Open a terminal/command prompt and run:

```bash
pip install yt-dlp
```

### 3. Export Google Drive Cookies

You need to export your browser cookies to authenticate with Google Drive:

**Option A: Using Chrome Extension (Recommended)**
1. Install the "Get cookies.txt LOCALLY" Chrome extension
2. Go to drive.google.com and log in
3. Click the extension icon and export cookies
4. Save the file as `cookies.txt` in the same folder as this script

**Option B: Using Browser Export Tool**
1. Use a tool like [cookies.txt](https://github.com/kairi003/Get-cookies.txt-LOCALLY)
2. Export cookies from drive.google.com
3. Save as `cookies.txt`

**Important:** The `cookies.txt` file should be in the same directory as `auto_downloader.py`. It's already in `.gitignore` to prevent accidental commits.

## Project Structure

```
Google Drive Downloader/
├── auto_downloader.py    # Main script
├── cookies.txt           # Browser cookies (NOT in git)
├── .gitignore            # Ignores cookies.txt
└── README.md             # This file
```

## Configuration

### Setting Up Your Course Structure

Edit the `COURSE_STRUCTURE` dictionary in `auto_downloader.py` to add your courses:

```python
COURSE_STRUCTURE = {
    "Folder/Subfolder": [
        ("FILE_ID_HERE", "filename.mp4"),
        ("ANOTHER_FILE_ID", "another_video.mp4")
    ]
}
```

### Finding Google Drive File IDs

1. Open the file in Google Drive
2. The URL format is: `https://drive.google.com/file/d/[FILE_ID]/view`
3. Copy the `[FILE_ID]` part (the long alphanumeric string)

### Changing Output Directory

Edit the `BASE_DIR` variable at the top of the script:

```python
BASE_DIR = os.path.abspath("Your_Custom_Folder_Name")
```

## Usage

### Basic Usage

1. Place `cookies.txt` in the same folder as the script
2. Run the script:

```bash
python auto_downloader.py
```

### What Happens During Execution

1. The script checks for `cookies.txt`
2. Creates the base directory structure
3. Iterates through each folder and file in `COURSE_STRUCTURE`
4. Downloads each file using yt-dlp
5. Skips files that already exist (resumable)
6. Adds random delays between downloads (0.5-1.5 seconds)
7. Reports progress and any failed downloads

### Output Structure

After running, you'll have:

```
University_Course_Data/
├── 01-Linux/
│   ├── 01-intro.mp4
│   ├── 02-HPC.mp4
│   └── ...
├── 02-Python/
│   ├── part1/
│   │   ├── 01-intro_to_Python.mp4
│   │   └── ...
│   └── part2/
│       ├── part1.mp4
│       └── ...
└── ...
```

## Troubleshooting

### "cookies.txt file not found!"

- Ensure `cookies.txt` is in the same directory as the script
- Check that the filename is exactly `cookies.txt` (not `cookies.txt.txt`)

### Download Failed Errors

- Your cookies may have expired - re-export them
- Check your internet connection
- Verify the file ID is correct
- Some files may require additional permissions

### Files Not Downloading

- Check if files already exist in the output directory (script skips existing files)
- Delete existing files if you want to re-download them
- Verify the file IDs are still valid (files may have been deleted or moved)

### Permission Errors

- Ensure you have write permissions in the output directory
- On Windows, run the terminal as Administrator if needed

## Advanced Usage

### Adding Speed Adjustment and Video Processing

Based on your requirements to adjust video speed and extract to a separate folder, you can extend the script with FFmpeg:

1. Install FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html)
2. Add FFmpeg to your system PATH
3. Create a secondary script that:
   - Reads the downloaded videos
   - Uses FFmpeg to adjust playback speed
   - Maintains the same folder hierarchy in a new output directory

Example FFmpeg command for speed adjustment:
```bash
ffmpeg -i input.mp4 -filter:v "setpts=0.5*PTS" -filter:a "atempo=2.0" output.mp4
```

## Security Notes

- **Never commit `cookies.txt` to version control** - it contains your authentication tokens
- The `.gitignore` file is configured to ignore `cookies.txt`
- Re-export cookies periodically as they may expire
- Only use cookies from accounts you own or have permission to access

## License

This script is provided as-is for educational purposes.

## Support

For issues with:
- **yt-dlp**: Visit [yt-dlp GitHub](https://github.com/yt-dlp/yt-dlp)
- **Cookie export**: Use the Chrome extension mentioned above
- **Script errors**: Check the error messages in the terminal output

## Manifest downloader (new, opt-in)

`manifest_downloader.py` is an alternative entry point for an explicit JSON file list. It does **not** change the original hard-coded `auto_downloader.py` workflow.

Create a `manifest.json` file:

```json
{
  "files": [
    {
      "id": "REPLACE_WITH_GOOGLE_DRIVE_FILE_ID",
      "path": "course/lesson-01.mp4",
      "sha256": "OPTIONAL_64_CHARACTER_HEX_SHA256"
    }
  ]
}
```

Remove the `sha256` property when you have no trusted digest; do not use the illustrative placeholder as a real checksum. Run:

```bash
python -m pip install yt-dlp
python manifest_downloader.py manifest.json --output downloads --cookies cookies.txt --retries 3 --backoff 2
```

The downloader creates destination directories, skips existing non-empty files (or verifies them first when SHA-256 is supplied), retries failed transfers, and records failures in `failed-downloads.json`. It exits with status 1 if any entry fails. Downloads first write to a temporary `.<source-token>.download` file and replace the destination only after successful completion and optional checksum verification. yt-dlp retains an associated `.<source-token>.download.part` file after interrupted transfers, allowing later runs to resume supported transfers. Completed temporary files left behind after interruption are reused only after optional checksum validation.

Manifest paths must be relative to the output root. Absolute paths, parent traversal (`..`), repeated separators, duplicate destinations (case-insensitive), and symlinks within the output path are rejected. Keep the cookie file outside version control. This command assumes Python 3.9 or newer and a working yt-dlp installation; no tests have been run for this new entry point yet.

### Migrating the original course list

The legacy `auto_downloader.py` contains an existing `COURSE_STRUCTURE` mapping. Export it once to a manifest without running downloads or executing the source file:

```bash
python export_legacy_manifest.py --source auto_downloader.py --output manifest.json
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt
```

The exporter preserves the original directory names, filenames, and Drive file IDs, and refuses to overwrite an existing `manifest.json`. The generated JSON is a regular editable file: remove entries, add entries, or attach a trusted `sha256` field to individual files before downloading. Importing requires a literal `COURSE_STRUCTURE` dictionary; dynamically calculated structures are deliberately unsupported. Neither the exporter nor the manifest contains cookie credentials. Because a manifest includes Drive file IDs and potentially descriptive filenames, review it before publishing it.

These additions are separate from the legacy script and do not modify its behavior.

### Preview and retry failed entries

Preview the manifest before downloading, without needing a cookie file:

```bash
python manifest_downloader.py manifest.json --output University_Course_Data --dry-run
```

To retry only entries in the previous failure report, retain the original report and write the new result to a different path:

```bash
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt --only-failed failed-downloads.json --failed-report retry-results.json
```

The retry list is checked against the current manifest (both file ID and destination path). Entries absent from the current manifest are rejected, preventing a stale report from silently introducing unrelated downloads. The script rejects report filenames that overlap input files, download targets or temporary download paths. A successful retry creates a new report with an empty `failed` array. The original report remains available for auditing.

### Select courses and limit download batches

The manifest downloader supports repeated include/exclude patterns and bounded batches, preserving the order of the original manifest. These filters apply after `--only-failed` (if supplied), and before downloading:

```bash
# Preview just the Linux lessons (no cookie file required)
python manifest_downloader.py manifest.json --include '01-Linux/*' --dry-run

# Download up to five entries from either Python subfolder
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt --include '02-Python/*' --limit 5

# Download all entries except Tableau
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt --exclude '08-Tableau/*'
```

Use quotes around patterns so your shell does not expand them. Paths use forward slashes in patterns, even when running on Windows; matching is case-sensitive. Multiple `--include` values are combined as OR, and any matching `--exclude` removes an entry. `--limit` accepts a positive integer and applies after filtering. The JSON failure report records failures from the *selected batch*, not from the entire manifest. For a complete synchronization, omit the selection switches.


### Resume interrupted downloads or replace existing files

By default, the manifest downloader skips non-empty destination files, optionally checking the SHA-256 field. If a transfer is interrupted, yt-dlp's partial `.<source-token>.download.part` data is retained, and the next invocation can resume the transfer when the remote server supports range requests. The completed destination is replaced only once the new download finishes and any configured SHA-256 check succeeds.

To deliberately re-download matching entries even when a non-empty destination already exists:

```bash
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt --force --include '01-Linux/*'
```

The `--force` option applies only to the selected entries and preserves existing destination files until a replacement is ready. It does not bypass SHA-256 verification. To restart a specific transfer from zero rather than resume, remove that file's `.<source-token>.download.part` temporary file while the downloader is **not** running. Avoid running multiple copies of the downloader against the same output paths concurrently.


### Audit local files without downloading

Use `--verify-only` to inspect the selected output files offline. This mode does not require `cookies.txt`, does not create directories or reports, and does not contact Google Drive.

```bash
python manifest_downloader.py manifest.json --output University_Course_Data --verify-only
python manifest_downloader.py manifest.json --output University_Course_Data --verify-only --include '01-Linux/*'
```

The command exits with status 0 when every selected destination is a non-empty regular file and all declared SHA-256 digests match. Missing files, empty files, and digest mismatches are printed as `INVALID` and cause exit status 1. Without a manifest SHA-256, the audit establishes only that the local file exists and is non-empty; it cannot prove that its contents match Google Drive.

For safe resume, temporary transfer filenames include a deterministic token derived from the Google Drive file ID. This avoids accidentally reusing a temporary file from another Drive source if two manifests assign different source IDs to the same output name. These staging filenames are implementation details and may be removed manually only when the downloader is stopped.

### Record persistent per-file progress

For long course downloads, append a timestamped, machine-readable journal as each file is processed:

```bash
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt --progress-log download-progress.jsonl
```

Each line is a standalone JSON object containing the UTC `timestamp`, Drive `id`, relative `path`, and `status` (`downloaded`, `skipped`, or `failed`). Failure records additionally include an `error` message. The log is appended between runs, so it is useful for reviewing which entries completed before an interruption. The existing `--failed-report` JSON output remains the way to retry failed entries with `--only-failed`; the progress log is for inspection and is not used as an authoritative download manifest. A process stopped during an active transfer may not record an event for that unfinished file.

Progress logging is opt-in and is not created by `--dry-run` or `--verify-only`. Keep progress logs private if file names or Drive IDs are sensitive; `download-progress.jsonl` is ignored by Git in this repository.

### Resume batches by manifest position

For large manifests, combine `--offset` and `--limit` to process successive windows in manifest order. The offset counts entries **after** include/exclude filtering and, if supplied, `--only-failed` selection.

```bash
# First 50 matching course files
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt --limit 50

# Next 50 matching files
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt --offset 50 --limit 50

# Inspect a later batch without downloads or cookies
python manifest_downloader.py manifest.json --include '02-Python/*' --offset 10 --limit 10 --dry-run
```

`--offset` accepts zero or a positive integer. Keep the manifest and filters unchanged between successive batches to avoid gaps or repeated selections. A batch beyond the final matching entry selects no files. Existing file skipping still applies; `--force` is required to replace already-downloaded destinations. Use `--progress-log` when a durable per-file audit trail is needed.

### Bound stalled download attempts

Add `--file-timeout SECONDS` to set a wall-clock deadline for each individual yt-dlp subprocess attempt:

```bash
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt --file-timeout 900 --retries 3 --backoff 2 --progress-log download-progress.jsonl
```

The example limits each attempt to 15 minutes; it does **not** impose a 15-minute deadline on the entire batch. When an attempt times out, the downloader stops that yt-dlp subprocess and reports a timeout if all attempts fail. Resumable partial data is retained for the next attempt or invocation. The existing retry backoff applies between attempts. If omitted, `--file-timeout` preserves the previous unlimited per-attempt duration. Supply a finite positive number of seconds.


### Generate SHA-256 checksums from downloaded files

After downloading a course collection, create a new manifest with SHA-256 digests calculated from the local files. The original manifest is **never overwritten**:

```bash
python annotate_manifest.py manifest.json --root University_Course_Data --output manifest-with-hashes.json
```

The command reads each existing non-empty file and adds a `sha256` field to its manifest entry. Any existing SHA-256 values must already match their corresponding local files; mismatches cause the operation to fail instead of silently replacing a trusted checksum. Missing or empty files cause failure by default. To retain these entries without hashes, use `--skip-missing`:

```bash
python annotate_manifest.py manifest.json --root University_Course_Data --output manifest-partial-hashes.json --skip-missing
python manifest_downloader.py manifest-with-hashes.json --output University_Course_Data --verify-only
```

Choose the file generated by the first command when using the verification command; the example verification command assumes the complete manifest was generated. Generated checksums are **local baselines only**: they can detect subsequent changes but do not independently prove that the source files were genuine or downloaded without corruption. The annotated manifest retains the original order, file IDs, paths, and any extra JSON fields. The output path must not exist already, and its parent directory must exist.

### Checkpoint retry state during long downloads

Use `--checkpoint` to keep the JSON failure report current throughout a long download batch, not only when the process exits:

```bash
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt --checkpoint --failed-report failed-downloads.json --progress-log download-progress.jsonl
```

At startup, the selected manifest entries appear in the report with an `error` value of `pending`. As each entry finishes, successful or skipped items are removed from the report and failed entries retain their error details. The report is atomically replaced after each processed entry, so an interrupted process can leave a retry list containing failed **and not-yet-processed** entries.

To retry a checkpoint report, use a different report destination to preserve the original evidence:

```bash
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt --only-failed failed-downloads.json --failed-report recovery-results.json --checkpoint
```

`--only-failed` still validates every ID/path pair against the current manifest. Checkpointing is opt-in because it writes the JSON report after each file; `--dry-run` and `--verify-only` cannot use it. The report reflects completed per-file updates and may lag the current in-flight transfer by one entry. It is not a substitute for a trusted SHA-256 digest.

### Limit bandwidth and pace large batches

The manifest downloader supports optional network throttling without affecting existing default behavior:

```bash
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt --limit-rate 2M --sleep-between-files 3 --checkpoint
```

`--limit-rate` forwards a yt-dlp transfer cap specified as a positive whole number of bytes per second with an optional `K`, `M`, or `G` suffix (for example, `500K` or `2M`). `--sleep-between-files` sets a finite non-negative number of seconds to pause between attempted manifest entries. The delay is applied after processing an entry, before the next selected entry, including entries that fail. Already-present files skipped without a download do not add a delay. Neither option changes checksum verification, resume handling, or retry backoff.

Use these options to reduce connection pressure during large course downloads. They do not guarantee that Google Drive will avoid rate limiting, and they do not override server-side quota restrictions.

### Stop a batch after repeated file failures

Use `--max-failures N` to stop processing when `N` selected files fail (after their individual retry attempts). This helps avoid repeatedly contacting an inaccessible Google Drive account, expired cookie session, or unavailable collection:

```bash
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt --max-failures 3 --checkpoint --failed-report failed-downloads.json
```

The limit counts **failed files**, not yt-dlp retry attempts; skipped or successfully downloaded files do not contribute. At the threshold, the downloader exits with status 1. The JSON failure report includes actual failures and remaining, unattempted entries marked `pending`, including when `--checkpoint` is not enabled. Using `--checkpoint` also saves the report after each processed file so that abrupt interruption still leaves an actionable list.

After diagnosing the cause, rerun the remaining entries with:

```bash
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt --only-failed failed-downloads.json --failed-report retry-results.json --max-failures 3
```

When no failure limit is provided, the downloader continues through all selected entries as before. `--max-failures` must be a positive integer.

### Portable manifest filename rules

The manifest downloader and the legacy course-list exporter validate destination names for portability across macOS, Linux and Windows. Path separators may be written with `/` or `\\` in the manifest, but the downloader interprets both as directory separators. It rejects absolute paths, parent-directory traversal, empty segments, control characters, Windows-reserved characters (`< > : " | ? *`), device names such as `CON`, `NUL`, `COM1` and `LPT1` (including names with extensions), and components ending in a space or period.

Duplicate detection is case-insensitive and applies Unicode NFC normalization. For example, filenames whose accented characters have canonically equivalent Unicode encodings are treated as collisions. If an existing legacy course filename violates these rules, rename the path in the source course mapping or in a new manifest before using the opt-in downloader. The original `auto_downloader.py` script is unaffected.

### Prevent concurrent downloads into the same directory

A normal manifest download now creates an exclusive `.manifest-downloader.lock` file inside the selected `--output` directory. Another instance of the manifest downloader targeting that directory exits rather than changing the same destination files, partial downloads or checkpoint state at the same time. The lock contains the process ID for diagnosis and is automatically removed on normal process exit, including after handled errors.

If a process is killed abruptly or the machine crashes, its lock can remain. Check that no downloader process is still operating against the directory before manually deleting the stale `.manifest-downloader.lock` file. Do not remove a live lock to run two instances concurrently. The lock applies only to the new manifest downloader, not to the legacy `auto_downloader.py` script or independent programs that do not honor the lock. Dry-run and offline verification do not create a lock.

### Restart corrupted or unusable partial downloads

Interrupted transfers normally resume from their source-specific temporary files. If a partial file is corrupt or the remote source no longer supports resuming, restart the selected transfers from scratch without manually locating hidden staging filenames:

```bash
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt --only-failed failed-downloads.json --failed-report restart-results.json --restart-partials
```

`--restart-partials` discards the selected file's `.<source-token>.download` and `.<source-token>.download.part` staging files only when that file actually needs a download. It does **not** delete or replace a completed destination that would normally be skipped. To replace those existing destination files as well, use `--force`:

```bash
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt --include '01-Linux/*' --force
```

A forced refresh now always starts the selected transfer from scratch rather than reusing a completed or partial staging artifact from an earlier session. The previous destination remains intact unless a new download finishes and passes any configured SHA-256 check. These options do not remove other files or directories. Avoid starting a second downloader targeting the same output root while either operation is running.

### Limit individual download sizes

Use `--max-file-mib N` to limit each selected transfer to `N` mebibytes (MiB, 1 MiB = 1,048,576 bytes). This is useful for preventing an unexpectedly large file from consuming substantial disk space:

```bash
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt --max-file-mib 2048 --checkpoint
```

The example sets a 2 GiB limit per downloaded file. The size constraint is passed to yt-dlp, then checked against the resulting completed or partial staging file. Oversized staging files are discarded, the corresponding entry is recorded as a failure, and any existing destination is preserved. An unexpectedly large partial download is not retried repeatedly in the same invocation. This is not a strict network-byte quota: a server that does not provide its size in advance may transfer data before the client can detect an over-limit file. No size ceiling applies unless this option is set, and it does not reject an already-present destination that the downloader would otherwise skip.

### Record and verify expected file sizes

Manifest entries can now include an optional `size_bytes` field alongside `id`, `path`, and `sha256`:

```json
{
  "files": [
    {
      "id": "1AbCdEfGhIjKlMnOpQrStUv",
      "path": "course/lesson.mp4",
      "size_bytes": 12582912
    }
  ]
}
```

`size_bytes` is an exact **positive integer in bytes**, not a rounded MiB estimate. Download mode checks this size before reusing an existing destination, promoting a completed temporary file, or replacing the destination with a new download. A mismatch causes a fresh download or a reported integrity failure. `--verify-only` checks both size and optional SHA-256. The `--dry-run` output indicates when an expected size is present.

The local `annotate_manifest.py` tool now adds `size_bytes` to entries that lack it, together with SHA-256 checksums. If a manifest already specifies a size, the annotator verifies it and refuses to overwrite a mismatch. As with local SHA-256 generation, values calculated from downloaded files are a local baseline and not independent confirmation of the remote file's authenticity. The `--max-file-mib` flag is a **separate upper bound** on individual transfers; `size_bytes` is an exact expected length.

### Detect manifest file and directory conflicts before downloading

The downloader validates the **entire** manifest's destination namespace before applying `--include`, `--exclude`, `--offset`, `--limit`, or failure-report selection. In addition to duplicate destination names, it rejects cases where one file path is used as a parent directory of another (for example, `lessons/week1` and `lessons/week1/video.mp4`).

Validation also reserves the downloader's source-specific `.download` and `.download.part` staging filenames, so a manifest entry cannot overwrite another entry's temporary or resumable transfer data. The root-level `.manifest-downloader.lock` filename is reserved. Collision checks use case-insensitive Unicode NFC comparisons across operating systems.

These checks are also applied by `export_legacy_manifest.py`. If a manifest is rejected, rename the conflicting destinations in its source before retrying; filters do not bypass conflicts in the complete manifest. This safeguard is distinct from pre-existing symlink checks, and does not delete or rename any local files.

### Progress journal write failures

When `--progress-log` is enabled, each processed file normally produces a JSONL event. If the journal cannot be appended to (for example, because the disk is full, the log location becomes unwritable, or a symlink is detected), the downloader prints a `PROGRESS LOG ERROR` message to standard error and stops writing further progress events for that invocation.

The downloader does **not** reinterpret an otherwise successful download as a failed transfer merely because the optional journal write failed. It continues processing files and updating `--failed-report` and `--checkpoint` normally, then exits with status `1` to flag incomplete progress logging even if all files downloaded successfully. Use `--verify-only` or review destination files to establish which transfers completed; an incomplete progress journal is not an authoritative completion record.

### Reserve free disk space for large transfers

Use `--min-free-mib N` to require at least `N` MiB of free disk space before starting each new yt-dlp transfer:

```bash
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt --min-free-mib 4096 --max-failures 1 --checkpoint
```

In this example, the downloader keeps a 4 GiB pre-transfer free-space reserve. If a manifest entry specifies an exact `size_bytes`, the check additionally accounts for the remaining file bytes, subtracting any existing resumable `.part` file. The check uses the free space on the filesystem containing the destination directory. Insufficient space is reported as a per-file failure without launching yt-dlp. Combine this with `--max-failures 1` to stop a large batch promptly and retain pending entries in the retry report.

This is a **pre-transfer capacity check**, not an enforced quota or an ongoing free-space monitor. Unknown-size transfers can still exhaust disk space, and other processes can consume space after the check. Download attempts are not limited by this option unless it is explicitly provided. `--min-free-mib` requires a positive whole-number MiB value.

### Resume after pressing Ctrl+C

The manifest downloader now handles an interactive Ctrl+C interruption by saving a JSON failure report containing all unsuccessful and not-yet-processed entries. The current in-progress file remains in the pending list, so any completed file will be checked and skipped on the next run if it matches the manifest. Resumable `.part` data is preserved. The downloader exits with code `130`, and the exclusive output-directory lock is released through normal cleanup.

```bash
# You can interrupt this batch with Ctrl+C.
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt --failed-report interrupted.json

# Resume the failed and pending subset.
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt --only-failed interrupted.json --failed-report resumed.json
```

This graceful recovery also works when `--checkpoint` was not supplied. `--checkpoint` remains useful for abrupt process termination, power loss and crashes where Python cannot process Ctrl+C. The report is written after interruption is handled, so it cannot be guaranteed if the system is terminated during the report write itself. A second interrupt or uncatchable termination may also prevent graceful recovery.

### Bound retry backoff

The manifest downloader retries failed yt-dlp attempts with exponential backoff and a small random jitter. The new `--max-backoff` option caps each waiting period, including jitter, to prevent very large delays in long retry sequences:

```bash
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt --retries 8 --backoff 2 --max-backoff 30
```

Here, the maximum wait between retry attempts is 30 seconds. The default cap is 60 seconds. `--backoff` must be a finite, non-negative number; `--max-backoff` must be finite and greater than zero. A base backoff of zero still allows up to half a second of jitter, subject to the cap. The cap applies to retry waits after both yt-dlp failures and per-file timeouts; it is separate from `--sleep-between-files` and `--file-timeout`. No delay occurs after the final attempt.

### Download public Drive files without a cookie file

If every selected Google Drive file is publicly accessible, opt out of cookie-based authentication with `--no-cookies`:

```bash
python manifest_downloader.py manifest.json --output downloads --no-cookies --checkpoint
```

This option omits yt-dlp's `--cookies` argument and skips the usual `cookies.txt` existence requirement. Without `--no-cookies`, the downloader continues to require `--cookies cookies.txt` (or the default `cookies.txt`) for nonempty download batches, preserving existing authenticated behavior. `--no-cookies` applies only to network downloads; read-only `--dry-run` and `--verify-only` modes do not require cookies.

Public links can still fail because of Google Drive sharing permissions, access restrictions, quotas, or extractor support. `--no-cookies` does not bypass authentication or make private files public. For a manifest mixing public and private files, use an authenticated run when the account has access to the selected files, or filter public files into a separate run.

### Limit newly downloaded bytes per batch

Use `--max-total-mib N` to bound the total size of newly completed downloads in a single invocation:

```bash
python manifest_downloader.py manifest.json --output downloads --cookies cookies.txt --max-total-mib 5120 --checkpoint
```

This example sets a nominal 5 GiB budget for newly completed downloads. Already-present valid destinations that the downloader skips **do not count** toward the budget. A completed download, including a recovered staging file promoted to its destination, counts at its actual byte length. If the manifest specifies `size_bytes`, the downloader stops **before** attempting a file that will exceed the remaining budget, leaving that file and all subsequent entries marked `pending`. If a file has no expected size, its actual size is counted after completion and may put the total above the nominal limit.

A budget stop returns exit status `1` and writes the failed/pending recovery report even if `--checkpoint` was not selected. The report can be passed to `--only-failed` in a later run with a fresh budget. If a known-size file exceeds the full budget, increase the budget or use a different selection; otherwise it will remain pending on every attempt. This is a **completed-file accounting limit**, not a live bandwidth quota or a guarantee about how many bytes will be transferred over the network. Set `--max-file-mib` separately to bound individual file size.

### Limit batch running time

Use `--max-run-seconds N` to give a manifest download batch a soft wall-clock time budget:

```bash
python manifest_downloader.py manifest.json --output downloads --cookies cookies.txt --max-run-seconds 3600 --checkpoint
```

This example runs the batch for approximately one hour, measured with a monotonic clock after the exclusive output lock has been acquired. The downloader checks the budget before **starting each new file**. If the time budget has elapsed, it stops, returns exit status `1`, and writes a failure report that retains all remaining, unattempted entries as `pending`, even without `--checkpoint`. Run again with `--only-failed` and a new `--failed-report` destination to continue the selected work.

`--max-run-seconds` must be a finite positive number. It does not terminate a download or retry sequence already in progress, so total elapsed time can exceed the configured limit. Combine it with `--file-timeout` to bound individual yt-dlp attempts, or `--max-total-mib` to separately limit completed download bytes. When omitted, batch runtime is unrestricted.

### Safe failure-report and progress-log destinations

Paths supplied through `--failed-report` and `--progress-log` are treated as metadata output files. The downloader refuses these paths if the destination itself is a symbolic link or directory, or if an existing parent directory in the path is a symbolic link. It checks the paths before starting the batch and checks again before creating directories or writing metadata.

Use ordinary directories rather than symlinked aliases for report and journal storage. This is a defense against accidental path redirection; it is not an atomic guarantee against a malicious process changing filesystem paths concurrently. If a report cannot be written, the downloader raises an error rather than silently redirecting the report to another location. The progress journal still has its separate non-fatal write-error handling described above.

### Stop batches after consecutive failures

Use `--max-consecutive-failures N` to stop an unhealthy batch after `N` files fail in a row:

```bash
python manifest_downloader.py manifest.json --output downloads --cookies cookies.txt --max-consecutive-failures 3 --checkpoint
```

This example stops after three consecutive failed manifest entries. A successful download **or a skipped existing file that passes the integrity checks** resets the consecutive-failure counter to zero. Multiple yt-dlp retry attempts for one file count as **one file failure**, not multiple consecutive failures. This is useful when credentials expire or many Google Drive links become unavailable.

The threshold applies to individual file outcomes; optional progress-log failures do not count as download failures. Unattempted entries remain marked `pending` in the failure report, and the command exits with status `1`. `--max-failures` remains available as a separate **cumulative failure limit**; whichever threshold is reached first stops the batch. Both flags require a positive integer. By default, neither limit is applied.

### Oversized resumable partials

Before a yt-dlp retry resumes an existing source-scoped `.download.part` file, the downloader checks its current byte count against the manifest's optional exact `size_bytes` and the configured `--max-file-mib` ceiling. A partial file already larger than either bound cannot become a valid final download by adding more data. In this case, the downloader removes its source-scoped `.part` and associated staged `.download` artifact, records a file failure, and moves on instead of repeatedly resuming it.

This limit check also runs after a timed-out yt-dlp attempt, including the final attempt, so an over-limit partial is not left behind for the next invocation. When the partial is within the applicable limits, the existing resume behavior is unchanged. A completed destination is never deleted by this cleanup. Without a manifest size or `--max-file-mib`, no such numeric partial-size bound exists.

### Reject unsafe staging-file types

For resumed or interrupted yt-dlp transfers, the downloader checks the final destination, source-scoped `.download` file, and corresponding `.download.part` file using filesystem metadata that does **not** follow symbolic links. Any of those paths occupied by a symbolic link, directory, named pipe, socket, or other non-regular filesystem object is rejected as a file failure. The validation is repeated before every retry and after yt-dlp attempts or timeouts.

This protects against accidentally reusing or deleting unexpected filesystem objects at the staging filenames. It does not provide an atomic guarantee against another process replacing a file between validation and use; do not share the output directory with untrusted concurrent processes. Normal regular-file resumptions and existing destination files continue to be supported.

### Protect manifests, cookies and reports from future batch collisions

The downloader checks **all entries in the manifest**, including entries later excluded by `--include`, `--exclude`, `--offset`, `--limit`, or `--only-failed`, against input and metadata paths before processing a batch. A destination, source-scoped `.download` artifact, or `.download.part` artifact must not coincide with the manifest file, authentication cookies (when enabled), failure-report destination, progress-log destination, retry-input report, or download lock.

These checks also reject file-versus-directory conflicts: for example, a manifest destination cannot be a directory that would need to contain the failure report, and the failure-report file cannot be a parent directory of a download. Metadata and input paths may not overlap each other as files or parent directories. The checks account for filenames in the **complete** manifest, rather than only the current batch, so a different filtered invocation cannot accidentally overwrite a protected file later.

If the downloader reports a collision, move the control file or rename the conflicting manifest destination before rerunning. Path checks operate on absolute paths and do not replace filesystem permissions, exclusive access or atomic filesystem protections against hostile concurrent changes.

### Byte budget and already-complete files

With `--max-total-mib`, the downloader first checks whether a selected destination is already a valid, nonempty local file (including its optional manifest SHA-256 and exact `size_bytes`). These verified existing files continue to be skipped, even after the batch's new-download byte budget is exhausted. The limit only prevents a **new transfer or staging-file promotion** from starting once its byte budget is reached. Consequently, a later already-complete entry may be skipped after the budget is reached, until the first entry that actually requires downloading is encountered.

This distinction keeps the recovery report focused on unfinished work: files verified locally are removed from `pending`, while the first blocked transfer and later entries stay pending. The separate `--max-run-seconds` limit is checked before each file and may still stop a run without inspecting additional files.

### Bind retry reports to the exact manifest

Every newly written `--failed-report` now includes a `manifest_sha256` fingerprint in addition to its `failed` array. The fingerprint is calculated from the **complete validated ordered manifest**, including file IDs, paths, optional `sha256` values and exact `size_bytes`. This makes checkpoint and interruption reports specific to the manifest revision that produced them, even when batch filters select only some entries.

When `--only-failed REPORT` is used, the downloader checks this fingerprint **before** selecting or downloading files. If the manifest has changed, or if a legacy report does not contain a matching fingerprint, the operation fails with an explanatory error. Regenerate a failure report from the current manifest before retrying. An example report now has the shape:

```json
{
  "manifest_sha256": "<64-character SHA-256 digest>",
  "failed": [
    {"id": "1AbCdEfGhIjKlMnOpQrStUv", "path": "course/lesson.mp4", "error": "pending"}
  ]
}
```

The fingerprint is a digest of the downloader's canonical validated entry list, **not** a digest of the raw manifest JSON file bytes; changes to irrelevant whitespace or JSON key order do not affect it. This is a safety check against accidental stale-report reuse, not an authentication mechanism. Reports written by earlier versions of this feature must be regenerated for the new format.

### Explicitly reconcile an older failure report

Strict manifest fingerprint matching remains the default for `--only-failed`. When a manifest has been edited since its failure report was created, or the report was generated by an older release that did not record `manifest_sha256`, use `--reconcile-failed` **only after reviewing the change**:

```bash
python manifest_downloader.py manifest.json --output downloads --cookies cookies.txt \
  --only-failed previous-failures.json --reconcile-failed \
  --failed-report current-failures.json --checkpoint
```

This emits a warning about the mismatch and restricts retries to entries whose **Google Drive ID and destination path exactly match** entries in the current manifest. Matching entries use the **current** `size_bytes` and `sha256` expectations. Entries in the retry report with IDs or paths missing from the current manifest are rejected, rather than silently skipped or redirected. A new recovery report is generated with the fingerprint of the current manifest.

`--reconcile-failed` must be used with `--only-failed`; it does not turn off path safety, local integrity checks or download limits. Omitting it continues to reject changed or legacy reports. When retrying, write the new failure report to a different path than the input report to preserve the original recovery record.

