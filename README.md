# 🎬 Plex Space Reclaimer

A high-performance localhost web application designed to scan, detect, compare, and safely delete duplicate Movies and TV Shows across multiple storage drives (NTFS, exFAT, NAS).

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
- **🖥️ Plex-Inspired Localhost Web UI**:
  - Dark mode aesthetic with Plex gold accents.
  - Interactive drive selector cards showing real-time disk capacity and health.
  - Side-by-side comparison cards for duplicates with quality badges.
  - One-click smart selection ("Select lower resolution", "Keep newest", "Select by drive").

---

## 💾 System Architecture

```
plex-duplicate-finder/
├── scanner.py          # High-speed disk scanner & media parser
├── server.py           # Localhost HTTP REST API server
├── requirements.txt    # Python dependencies
├── frontend/
│   ├── index.html      # Single-page application structure
│   ├── style.css       # Plex-inspired dark theme styling
│   └── app.js          # Interactive dashboard & duplicate management
├── .gitignore
├── LICENSE
└── README.md
```

---

## 🚀 Quick Start

### 1. Requirements
- Windows 10/11
- Python 3.10+ (Standard Library supported out of the box)

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

### 3. Running the Web Tool
Start the localhost server:
```bash
python server.py
```
Open your browser and navigate to:
```
http://localhost:8282
```

---

## 🔒 Safety & Data Integrity

- **Never Overwrites**: The scanner is strictly read-only during analysis.
- **Reversible Action**: All deletion actions default to the Windows Shell Recycle Bin API (`SHFileOperation`).
- **Audit Logs**: Every scan and file action is recorded in `scan_history.json` with timestamps, original file paths, and file sizes.

---

## 📄 License

Distributed under the MIT License. See [LICENSE](file:///C:/Users/Ron/.gemini/antigravity-ide/scratch/plex-duplicate-finder/LICENSE) for details.
