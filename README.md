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

The downloader creates destination directories, skips existing non-empty files (or verifies them first when SHA-256 is supplied), retries failed transfers, and records failures in `failed-downloads.json`. It exits with status 1 if any entry fails. Downloads first write to a temporary `.download` file and replace the destination only after successful completion and optional checksum verification.

Manifest paths must be relative to the output root. Absolute paths, parent traversal (`..`), repeated separators, duplicate destinations (case-insensitive), and symlinks within the output path are rejected. Keep the cookie file outside version control. This command assumes Python 3.9 or newer and a working yt-dlp installation; no tests have been run for this new entry point yet.

### Migrating the original course list

The legacy `auto_downloader.py` contains an existing `COURSE_STRUCTURE` mapping. Export it once to a manifest without running downloads or executing the source file:

```bash
python export_legacy_manifest.py --source auto_downloader.py --output manifest.json
python manifest_downloader.py manifest.json --output University_Course_Data --cookies cookies.txt
```

The exporter preserves the original directory names, filenames, and Drive file IDs, and refuses to overwrite an existing `manifest.json`. The generated JSON is a regular editable file: remove entries, add entries, or attach a trusted `sha256` field to individual files before downloading. Importing requires a literal `COURSE_STRUCTURE` dictionary; dynamically calculated structures are deliberately unsupported. Neither the exporter nor the manifest contains cookie credentials. Because a manifest includes Drive file IDs and potentially descriptive filenames, review it before publishing it.

These additions are separate from the legacy script and do not modify its behavior.
