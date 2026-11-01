# 🎬 Plex Space Reclaimer (Plex Space Saver)

A high-performance localhost web application and background service designed to scan, detect, compare, transcode, and safely delete duplicate Movies and TV Shows across multiple storage drives (NTFS, exFAT, NAS).

Engineered specifically for large-scale multi-terabyte Plex media libraries (100+ TB) where naive hashing is impractical.

---

## ✨ Key Features

- **🚀 Ultra-Fast Sparse Scanning**: Instead of computing full SHA-256 hashes on multi-gigabyte video files (which thrashes spinning hard drives), the scanner combines **intelligent filename normalization**, **exact byte matching**, and **sparse chunk hashing** (header + middle + footer sampling) for near-instantaneous verification.
- **🏷️ Smart Quality & Stream Recognition**: Automatically parses and detects:
  - Resolution: `4K / 2160p`, `1080p`, `720p`, `480p`
  - Video Codecs: `HEVC / x265`, `AVC / x264`, `AV1`, `Remux`
  - Audio Formats: `TrueHD Atmos`, `DTS-HD MA`, `DDP 5.1`, `Stereo`
  - Release groups and edition tags (`Director's Cut`, `Extended`)
- **🗂️ Cross-Drive Duplicate Grouping**:
  - **Exact Duplicates**: Identical byte size and matching sparse hash.
  - **Quality Variations**: Same movie or TV episode in differing qualities (e.g., 4K HDR on Drive X vs. 1080p SDR on Drive A).
  - **Folder Duplicates**: Redundant season or show folders created by different download clients or media managers.
- **🛡️ Safety-First Deletion Guarantee**:
  - **Recycle Bin Integration**: Deleted files are sent directly to the Windows Recycle Bin by default, allowing full recovery.
  - **Quarantine Mode**: Optionally move duplicates into a designated `_quarantine` directory on each drive.
  - **Dry Run & Confirmation**: Always preview total space reclaimed before executing any deletion.
  - **Audit Logging**: Persistent records in `deletion_audit.json` with item details and reclaimable space metrics.
- **🎥 Hardware-Accelerated Transcoding**:
  - Built-in In-App Transcode Queue using Intel QuickSync (`hevc_qsv`), NVIDIA NVENC (`hevc_nvenc`), AMD AMF, and CPU `libx265`.
  - Generates 15-second test preview snippets to compare visual quality and projected space savings before processing entire libraries.
  - Safely drops problematic subtitle streams (`-sn`) during transcoding to prevent crashes on image-based PGS subs.
  - Skips unsupported Dolby Vision Profile 7 REMUX files to avoid hardware decoder hangs.
- **🧹 Drive Offloader & Library Cleaner**:
  - **Drive Offloader / Migrator**: Moves non-duplicate movies and series to secondary storage to free up primary drives.
  - **Library Cleaner**: Scans for and removes orphan folders, tiny sample clips, and leftover junk metadata.
- **🖥️ Plex-Inspired Web UI & Desktop Integration**:
  - Dark mode aesthetic with official Plex gold styling.
  - Interactive drive cards showing real-time capacity and health.
  - Side-by-side comparison cards with quality badges and one-click smart filters.
  - **Desktop Shortcut & Custom Logo**: Double-clickable desktop shortcut with a high-res custom icon (`plex_space_saver.ico`).
  - **Windows Boot Auto-Start**: Runs silently as a background service via `pythonw.exe` on system reboot with no intrusive terminal popups.

---

## 💾 System Architecture

```
plex-duplicate-finder/
├── scanner.py                   # High-speed disk scanner & media parser
├── media_inspector.py           # Deep stream & codec analysis via ffprobe
├── transcoder.py                # Hardware-accelerated transcoding engine
├── optimizer.py                 # Space optimization advisor logic
├── pool_migrator.py             # Smart drive offloader and library migrator
├── balancer.py                  # Multi-drive space balancing engine
├── cleaner.py                   # Empty directory and sample clip cleaner
├── plex_api.py                  # Plex Server integration & library refresh
├── tmdb_api.py                  # TMDb artwork and poster caching
├── server.py                    # Localhost HTTP REST API server (with pythonw support)
├── launch_plex_space_saver.vbs  # Desktop launcher (checks server & opens browser)
├── setup_startup_and_desktop.py # One-click installer for desktop icon & boot startup
├── generate_logo.py             # High-res Windows ICO and PNG logo generator
├── plex_space_saver.ico         # Multi-resolution Windows application icon
├── plex_space_saver.png         # High-resolution branding logo
├── requirements.txt             # Python dependencies
├── frontend/
│   ├── index.html               # Single-page application structure
│   ├── style.css                # Plex-inspired dark theme styling
│   └── app.js                   # Interactive dashboard & duplicate management
├── .gitignore
├── LICENSE
└── README.md
```

---

## 🚀 Quick Start

### 1. Requirements
- Windows 10/11
- Python 3.10+ (Standard Library supported out of the box)
- Optional: `ffmpeg` / `ffprobe` in PATH for hardware transcoding and deep stream inspection.

### 2. Installation
Clone the repository:
```bash
git clone https://github.com/ronavis/plex-duplicate-finder.git
cd plex-duplicate-finder
```

Install optional dependencies for enhanced media info and Recycle Bin support:
```bash
pip install -r requirements.txt
```

### 3. One-Click Desktop & Startup Setup (Recommended for Windows)
Run the automated setup script:
```bash
python setup_startup_and_desktop.py
```
This will automatically:
1. Place a **Plex Space Saver** double-clickable shortcut with the custom logo on your **Desktop**.
2. Configure **Windows Startup** (`StartPlexSpaceSaver.vbs`) so the background server boots silently whenever Windows starts.
3. Start the server immediately in the background on port `8282`.

### 4. Running Manually
To start the localhost server manually:
```bash
python server.py
```
Then navigate to:
```
http://localhost:8282
```

---

## 🔒 Safety & Data Integrity

- **Strictly Read-Only During Scans**: Scanning never alters, touches, or renames files without explicit confirmation.
- **Reversible Action**: All deletion actions default to the Windows Shell Recycle Bin API (`SHFileOperation`).
- **Comprehensive Audit Trail**: Every file deletion and space reclamation is permanently recorded in `deletion_audit.json`.

---

## 📄 License

Distributed under the MIT License. See [LICENSE](file:///C:/Users/Ron/.gemini/antigravity-ide/scratch/plex-duplicate-finder/LICENSE) for details.
