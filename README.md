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

