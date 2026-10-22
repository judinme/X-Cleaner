# ⚡ X-Cleaner
### Complete C: Drive Storage & Duplicate Optimizer
*Enterprise-Grade Windows Storage Intelligence, Bloat Audit & Multi-Tier Duplicate Deduplication*

---

[![Platform: Windows 10/11](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-000000.svg?style=flat-square&logo=windows)](https://microsoft.com/windows)
[![Architecture: x64](https://img.shields.io/badge/Architecture-x64-000000.svg?style=flat-square)](https://github.com)
[![Design: Minimalist Monochrome](https://img.shields.io/badge/Design-Minimalist%20Monochrome%20%7C%20Swiss-000000.svg?style=flat-square)](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)
[![Packaging: Standalone Portable EXE](https://img.shields.io/badge/Binary-Portable%20Single--File%20EXE-000000.svg?style=flat-square)](https://github.com)
[![Safety: Zero False Positives](https://img.shields.io/badge/Safety-Recycle%20Bin%20%2B%20Kernel%20Blacklist-000000.svg?style=flat-square)](https://github.com)

---

## ✦ Overview

**X-Cleaner** is a high-performance Windows systems storage analyzer and deep-cleaning desktop suite designed to reclaim dozens of gigabytes of hidden disk space from the Windows system partition (`C:`).

Unlike generic temporary file cleaners that merely sweep user `Temp` folders, **X-Cleaner** performs an exhaustive, multi-threaded deep audit of the entire Windows partition:
- **Developer Ecosystem Bloat:** Docker WSL2 virtual disks (`ext4.vhdx`), Android AVDs, Gradle/Maven repositories, npm/yarn/pnpm/pip/cargo/nuget caches, and Visual Studio build artifacts.
- **Windows System Storage Reservoirs:** Hibernation files (`hiberfil.sys`), Delivery Optimization caches, Windows Component Store (WinSxS), Crash Dumps, Shadow Copies, and Service Pack leftovers.
- **3-Tier Zero-False-Positive Duplicate Engine:** Exact-byte matching, 4 KB head-hash pruning, and full streaming SHA-256 validation with NTFS Hardlink awareness and intelligent multi-criteria selection presets.
- **High-Density Storage Treemap & Large File Analyzer:** Rapid `os.scandir` parallel traversal categorizing the top storage consumers, large directory trees, and file extension distributions across the entire drive.

Packaged as a **single-file, zero-dependency portable `.exe`** with a stark **Minimalist Monochrome (Swiss / Bauhaus) UI/UX** crafted strictly from two tones: pure white (`#FFFFFF`) and pitch black (`#000000`).

---

## ✦ Minimalist Monochrome UI / UX Philosophy

The visual and interaction architecture of **X-Cleaner** strictly adheres to the **Minimalist Monochrome & Swiss Style** design specification defined by [ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill.git):

```
┌────────────────────────────────────────────────────────────────────────┐
│  X-CLEANER · SWISS MONOCHROME DESIGN SPEC                              │
├───────────────────┬───────────────────┬────────────────────────────────┤
│ Pitch Black       │ #000000           │ Main canvas, window frame      │
│ Deep Canvas       │ #080808           │ Tab backgrounds, toolbars      │
│ Surface Cards     │ #141414           │ Elevated metric cards, stats   │
│ Geometric Borders │ #222222 (1px)     │ Razor-sharp 1px dividers       │
│ Active/Hover      │ #2c2c2c           │ Subtle responsive feedback     │
│ Primary White     │ #FFFFFF           │ Text, inverted action buttons  │
│ Secondary Muted   │ #999999 / #666666 │ Monospace labels, annotations  │
└───────────────────┴───────────────────┴────────────────────────────────┘
```

- **Stark High Contrast:** Eliminates visual fatigue caused by multi-colored gradients, rainbow badges, and noisy shadows. Focuses entirely on storage metrics, file hierarchies, and actionable data.
- **Inverted Action Buttons:** Primary Call-to-Actions (e.g., `⚡ Clean Selected`, `↻ Rescan Caches`, `★ Auto-Mark Safe Dupes`) render as high-visibility solid white pills with bold black text, creating instant visual hierarchy.
- **Monospace Numerical Density:** File sizes, hashes, cluster indices, and byte counts are strictly formatted for scannability and column alignment.
- **Dynamic Per-Monitor DPI Scaling:** Custom scaling engine queries `user32.dll` (`GetDpiForWindow` / `GetDeviceCaps`) to dynamically scale geometry, fonts, padding, and tree columns across 100%, 125%, 150%, 175%, and 200% displays.

---

## ✦ Architecture & Feature Highlights

### 1. 4-Category Deep Cache & Bloat Scanner
Audits over 42 specialized system locations across four functional categories:

| Category | Targets & Systems Audited | Safety Level |
|---|---|---|
| **Developer Tools** | Docker Desktop WSL2 (`ext4.vhdx`), Android AVD emulators, Android SDK build-tools, Gradle wrapper caches, Maven `.m2` repository, npm/yarn/pnpm global caches, pip/PyPA wheel caches, Cargo `.cargo` registry, NuGet package caches, Visual Studio `/VC/` and `.vs` intermediate build caches, JetBrains IDE system caches. | Safe / Moderate / Review |
| **System Caches** | Windows Hibernation (`hiberfil.sys`), Windows Update Download Cache (`SoftwareDistribution\Download`), Delivery Optimization files, Memory Crash Dumps (`MEMORY.DMP`, Minidumps), WER Error Reporting archives, Prefetch cache (`Windows\Prefetch`), Font cache, Windows Installer orphaned patch files. | Safe / Moderate |
| **Browser Data** | Google Chrome, Microsoft Edge, Mozilla Firefox, Brave, and Opera GPU caches, code caches, service worker storages, shader caches, and network cache files (preserves user passwords, history, and active sessions). | Safe |
| **Temp Files** | Windows User Temp (`%TEMP%`), System Temp (`C:\Windows\Temp`), File Explorer thumbnail caches (`thumbcache_*.db`), Recycle Bin items across all drives. | Safe |

### 2. 3-Tier Multi-Threaded Duplicate Detection Pipeline
Guarantees **mathematical zero false positives** while minimizing disk I/O through a three-stage progressive filtration pipeline:

```
[ All Candidates (N Files) ]
              │
              ▼
   ┌──────────────────────────────────────────────┐
   │ Tier 1: Exact Byte Size Grouping             │  (Fast os.scandir metadata)
   │ Prunes 98%+ of unique files without reading  │
   └──────────────────────────────────────────────┘
              │ Size collisions only
              ▼
   ┌──────────────────────────────────────────────┐
   │ Tier 2: 4 KB Head-Hash Inspection            │  (Reads first 4096 bytes)
   │ Eliminates distinct files with matching size │
   └──────────────────────────────────────────────┘
              │ Head hash collisions only
              ▼
   ┌──────────────────────────────────────────────┐
   │ Tier 3: Full Streaming SHA-256 Hashing       │  (1 MiB block streaming)
   │ Cryptographically verifies byte identity     │
   └──────────────────────────────────────────────┘
              │ Verified duplicates
              ▼
   ┌──────────────────────────────────────────────┐
   │ NTFS Hardlink Deduplication                  │  (BY_HANDLE_FILE_INFORMATION)
   │ Preserves hardlinked files sharing clusters  │
   └──────────────────────────────────────────────┘
```

#### Smart Selection Presets:
- **Keep Oldest File:** Preserves the original file based on `st_ctime` and marks newer copies.
- **Keep Newest File:** Preserves the latest modified copy and marks older duplicates.
- **Keep Shortest Path:** Retains files located nearest to root directory structures.
- **Keep Longest Path:** Retains files nested deeply within specialized project trees.
- **Path Pattern Rules:** Auto-marks duplicates situated in designated trash/temp paths (e.g. `Downloads`, `Copy of`, `(1)`).

### 3. Large File Analyzer & Directory Treemap
- **Top 500 Huge Files:** Instant heap-sorted table of the largest files on the system partition, showing exact paths, sizes, extensions, and modification timestamps.
- **Interactive Directory Treemap:** Recursively aggregates disk consumption across directory branches, allowing instant visual identification of bloated directories.
- **File Extension Breakdown:** Aggregates storage consumption by file format (`.vhdx`, `.iso`, `.zip`, `.dll`, `.exe`, `.mp4`, `.log`, `.pdb`).

### 4. Windows System Maintenance Interop
- **Hibernation Optimization:** Reads Windows registry `SYSTEM\CurrentControlSet\Control\Power\HibernateFileSizePercent` and checks `C:\hiberfil.sys`. Provides one-click toggling (`powercfg.exe -h off` / `powercfg.exe -h on`) to instantly reclaim 8 GB – 64 GB of RAM-equivalent disk space.
- **Component Store (WinSxS) Cleanup:** Shells out to elevated DISM (`dism.exe /online /cleanup-image /startcomponentcleanup /resetbase`) to purge superseded service pack and update backups.
- **Delivery Optimization Flush:** Safely purges P2P update fragments from `C:\Windows\SoftwareDistribution\DeliveryOptimization`.

### 5. Kernel-Grade SafetyGuard Engine
- **Kernel & Boot Blacklist:** Strict exclusion list protecting critical operating system directories (`\Windows\System32`, `\Windows\WinSxS`, bootloaders, pagefile, swapfile, registry hives).
- **Cloud Storage Dehydration Prevention:** Queries Windows file attributes for `FILE_ATTRIBUTE_RECALL_ON_OPEN` (`0x00040000`) and `FILE_ATTRIBUTE_OFFLINE` (`0x00001000`). Never accesses dehydratable OneDrive/iCloud/Dropbox placeholders to prevent triggering massive cloud re-downloads.
- **Windows Recycle Bin Interop:** All file deletions default to native Windows Recycle Bin operations via `shell32.dll` (`SHFileOperationW` with `FO_DELETE` and `FOF_ALLOWUNDO | FOF_SILENT`), ensuring complete reversibility.
- **Active Process & Lock Detection:** Gracefully handles locked files without crashing or aborting background scan batches.

---

## ✦ Installation & Quick Start

### Portable Executable (Recommended)
**X-Cleaner** is distributed as a single standalone executable. No installation, runtime, or registry setup is required:

1. Download or copy **`X-Cleaner.exe`** to your system (or launch directly from your Desktop: `C:\Users\SPARK\Desktop\X-Cleaner.exe`).
2. Right-click **`X-Cleaner.exe`** and select **Run as Administrator** (recommended for auditing system-level caches such as `SoftwareDistribution`, Prefetch, and `hiberfil.sys`).
3. The suite opens instantly with the Swiss Monochrome interface.

### Running from Source
If building or running in a development environment:

```powershell
# Clone or navigate to the repository
cd D:\DeepClean

# Ensure Python 3.10+ is available
python --version

# Run directly via Python
python deepclean.py
```

### Keyboard Shortcuts
| Shortcut | Action | Scope |
|---|---|---|
| `Space` | Toggle selection checkbox | Cache Tab & Duplicate Tab |
| `Double-Click` | Reveal item in Windows File Explorer | Cache Tab, Duplicate Tab, Large Files Tab |
| `Ctrl + R` | Refresh Drive Capacity & Statistics | Global |

---

## ✦ Compiling Standalone Executable

To compile `X-Cleaner.exe` from source using PyInstaller:

```powershell
# 1. Install PyInstaller and Pillow (for high-DPI icon rasterization)
pip install pyinstaller pillow

# 2. Build the portable single-file executable
python -m PyInstaller `
    --clean `
    --onefile `
    --noconsole `
    --name X-Cleaner `
    --icon=assets/deepclean.ico `
    --add-data "assets;assets" `
    deepclean.py

# 3. Output binary will be generated at:
# D:\DeepClean\dist\X-Cleaner.exe
```

---

## ✦ Technical Specifications

| Parameter | Specification |
|---|---|
| **Binary Name** | `X-Cleaner.exe` |
| **Binary Size** | ≈ 13.1 MB (portable, self-contained) |
| **Language** | Python 3.14 / Tkinter & ttk with Clam Engine |
| **Native Interop** | `ctypes` bindings for `kernel32.dll`, `shell32.dll`, `user32.dll`, `ole32.dll` |
| **Hashing Engine** | Streaming `hashlib.sha256` with 1 MiB chunking |
| **Threading Model** | Dedicated background worker daemon threads with non-blocking UI queue |
| **Memory Footprint** | ≈ 38 MB – 95 MB RAM during full drive audits |
| **Supported OS** | Windows 10 (Build 17763+), Windows 11 (all versions), Windows Server 2019/2022 |

---

## ✦ License & Warranty

Copyright © 2026 X-Cleaner Architecture Team.
Distributed under the MIT License. Built for rigorous storage optimization and deep system hygiene.
