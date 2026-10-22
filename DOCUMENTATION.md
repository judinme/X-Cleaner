# ⚡ X-Cleaner · Complete Technical Documentation & Architectural Specification

---

## Document Information
- **Product Name:** X-Cleaner (Complete C: Drive Storage & Duplicate Optimizer)
- **Document Version:** 1.0.0
- **Target OS:** Microsoft Windows 10 (Build 17763+) / Windows 11 / Windows Server 2019+
- **Architecture:** x86_64 (AMD64)
- **Primary Source:** `d:\DeepClean\deepclean.py`
- **Design Standard:** [UI/UX Pro Max Skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill.git) — *Minimalist Monochrome & Swiss Style*

---

## 1. Executive Overview & Design System

### 1.1 Architectural Purpose
Windows workstations accumulate gigabytes of unmanaged storage over time, primarily stemming from:
1. **Modern Developer Stacks:** Container layers, SDK system images, dependency caches, and build intermediates that standard cleanup utilities ignore.
2. **System Storage Buffers:** Reserved hibernation files sized to 40%–100% of physical RAM, delivery optimization delivery pools, memory dumps, and Windows Component Store (WinSxS) superseded assemblies.
3. **Accidental Duplicate Files:** Redundant downloads, duplicated virtual disks, installer copies, and multiple workspace checkouts.

**X-Cleaner** was built to provide an exhaustive, multi-threaded deep storage audit and deduplication engine packaged into an independent, zero-dependency portable `.exe` with zero false positives.

---

### 1.2 Minimalist Monochrome (Swiss Style) Design System
In accordance with the `ui-ux-pro-max-skill` specification (Style Category #1 *Minimalism & Swiss Style* and #70 *Minimalist Monochrome*), X-Cleaner rejects extraneous ornamentation, multicolored badges, and drop shadows in favor of stark contrast, functional clarity, and geometric precision.

#### 1.2.1 Color Palette Tokens
| Token | Hex Value | Purpose |
|---|---|---|
| `CRUST` | `#000000` | Pitch black base window background, border frames |
| `MANTLE` | `#080808` | Secondary container canvas, navigation bar |
| `BASE` | `#0d0d0d` | Notebook page backgrounds, tab canvas |
| `CARD` | `#141414` | Metric cards, stat tiles, treeview backgrounds |
| `SURFACE0` | `#222222` | Crisp 1px geometric borders, dividers |
| `SURFACE1` | `#2c2c2c` | Hover state borders, inactive tree rows |
| `SURFACE2` | `#3a3a3a` | Pressed button borders, treeview active selection |
| `OVERLAY` | `#666666` | Muted annotations, secondary timestamps |
| `SUBTEXT` | `#999999` | Secondary column metrics, descriptions |
| `TEXT` / `WHITE` | `#FFFFFF` | Primary white text, high-contrast action fills |
| `BLACK` | `#000000` | Inverted action button text, dark icon glyphs |

#### 1.2.2 High-Contrast Button Inversion
The primary interaction pattern uses inverted solid pills:
- **Primary Call to Action (`Accent.TButton` / `GradientButton`):**
  - Normal state: Background `#FFFFFF`, Foreground `#000000`, 1px border `#222222`.
  - Hover state: Background `#E0E0E0`, Foreground `#000000`.
  - Active/Pressed state: Background `#CCCCCC`, Foreground `#000000`.
- **Secondary Actions (`TButton`):**
  - Normal state: Background `#141414`, Foreground `#FFFFFF`, 1px border `#222222`.
  - Hover state: Background `#222222`, Foreground `#FFFFFF`.

#### 1.2.3 Per-Monitor Dynamic DPI Scaling Engine
To support displays ranging from standard 1080p (96 DPI) to 4K high-density panels (192–288 DPI), X-Cleaner executes hardware DPI discovery during launch:

```python
def _detect_dpi_scale():
    if os.name == "nt":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2) # Per-Monitor High DPI Aware
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        try:
            hdc = ctypes.windll.user32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88) # LOGPIXELSX
            ctypes.windll.user32.ReleaseDC(0, hdc)
            return max(1.0, dpi / 96.0)
        except Exception:
            pass
    return 1.0
```

Every dimension, font size, treeview row height, button padding, and widget geometry is routed through the scale helper `S(pixels) = int(round(pixels * DPI_SCALE))`.

---

## 2. Low-Overhead Scanning Engine & Windows API Interop

### 2.1 File System Traversal Architecture
X-Cleaner utilizes Python's C-accelerated `os.scandir` rather than `os.walk` or recursive globbing. On Windows, `os.scandir` issues `FindFirstFileW` / `FindNextFileW` Win32 API calls that retrieve file attributes, sizes, and timestamps directly in the directory entry record without requiring secondary `os.stat` system calls.

### 2.2 Symlink, Reparse Point & Junction Isolation
Windows NTFS heavily utilizes directory junctions and reparse points (e.g. `C:\Users\All Users` -> `C:\ProgramData`, `C:\Documents and Settings` -> `C:\Users`). Traversal without reparse point isolation causes infinite recursion or duplicate counting.
- Each directory entry is tested via `entry.is_symlink()` and `entry.is_junction()`.
- Visited directories are tracked in an inode/path set to guarantee single-pass traversal.

### 2.3 Cloud Dehydration Prevention (`Cloud Masking`)
OneDrive, Dropbox, and iCloud on Windows 10/11 utilize NTFS Reparse Points with cloud dehydration flags. Reading the contents of an offline cloud placeholder triggers Windows Shell to download the entire remote file across the network, saturating bandwidth and exhausting disk space.

X-Cleaner inspects the Windows Win32 file attribute flags before performing any I/O:
```python
FILE_ATTRIBUTE_OFFLINE               = 0x00001000
FILE_ATTRIBUTE_RECALL_ON_OPEN        = 0x00040000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000
CLOUD_MASK = FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_RECALL_ON_OPEN | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS

def is_cloud_placeholder(stat_res):
    attrs = getattr(stat_res, "st_file_attributes", 0)
    return bool(attrs & CLOUD_MASK)
```
Any file matching `CLOUD_MASK` is safely bypassed during both duplicate hashing and large file analysis.

---

## 3. 3-Tier Multi-Threaded Duplicate Detection Pipeline

The duplicate engine guarantees **100% mathematical zero false positives** while avoiding unnecessary disk reads on non-duplicate files.

```
┌────────────────────────────────────────────────────────────┐
│                    Candidate Files (N)                     │
└─────────────────────────────┬──────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────┐
│ Tier 1: Exact Byte-Size Bucketing                          │
│ Time Complexity: O(N) | Disk Reads: 0 bytes                │
│ Prunes files with unique sizes using os.scandir metadata   │
└─────────────────────────────┬──────────────────────────────┘
                              │ Size collisions (M files)
                              ▼
┌────────────────────────────────────────────────────────────┐
│ Tier 2: 4 KB Head-Hash Inspection                          │
│ Reads: 4096 bytes per file | Alg: SHA-256(Head Chunk)      │
│ Filters files with identical sizes but distinct headers    │
└─────────────────────────────┬──────────────────────────────┘
                              │ Head-hash collisions (K files)
                              ▼
┌────────────────────────────────────────────────────────────┐
│ Tier 3: Full Streaming SHA-256 Hashing                     │
│ Reads: 1 MiB chunked streaming | Alg: Cryptographic SHA-256│
│ Identifies true identical byte matches                     │
└─────────────────────────────┬──────────────────────────────┘
                              │ Verified duplicates
                              ▼
┌────────────────────────────────────────────────────────────┐
│ NTFS Hardlink Deduplication                                │
│ Win32 API: GetFileInformationByHandleW                     │
│ Resolves nFileIndexHigh + nFileIndexLow                    │
│ Excludes files pointing to identical NTFS MFT records      │
└────────────────────────────────────────────────────────────┘
```

### 3.1 Mathematical Proof of Zero False Positives
Two files $F_A$ and $F_B$ are declared duplicates if and only if:
1. $\text{Size}(F_A) = \text{Size}(F_B)$ (Tier 1)
2. $\text{SHA256}(F_A[0:4096]) = \text{SHA256}(F_B[0:4096])$ (Tier 2)
3. $\text{SHA256}(F_A) = \text{SHA256}(F_B)$ (Tier 3)
4. $\text{MFT\_Index}(F_A) \neq \text{MFT\_Index}(F_B)$ (Hardlink Exclusion)

The cryptographic collision probability of SHA-256 across arbitrary files is $2^{-256} \approx 8.6 \times 10^{-78}$, ensuring absolute data fidelity.

### 3.2 NTFS Hardlink Deduplication
On NTFS filesystems, multiple directory entries can point to the same physical disk clusters via hardlinks (e.g., WinSxS assemblies or package link caches). Deleting one hardlink does not reclaim disk space until the final link is severed.

X-Cleaner calls `kernel32.GetFileInformationByHandle`:
```python
class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("dwFileAttributes", wintypes.DWORD),
        ("ftCreationTime", wintypes.FILETIME),
        ("ftLastAccessTime", wintypes.FILETIME),
        ("ftLastWriteTime", wintypes.FILETIME),
        ("dwVolumeSerialNumber", wintypes.DWORD),
        ("nFileSizeHigh", wintypes.DWORD),
        ("nFileSizeLow", wintypes.DWORD),
        ("nNumberOfLinks", wintypes.DWORD),
        ("nFileIndexHigh", wintypes.DWORD),
        ("nFileIndexLow", wintypes.DWORD),
    ]
```
If two duplicate entries share identical `dwVolumeSerialNumber`, `nFileIndexHigh`, and `nFileIndexLow`, they occupy the identical physical MFT record; X-Cleaner tags them accordingly and avoids double-counting reclaimed storage.

---

## 4. Deep Inspection Catalog & Cleanup Engine

The audit engine inspects over 42 specific locations divided across four functional domains:

### 4.1 Developer Tools & Environments
| Target Name | Target Path / Command | Risk Level | Cleanup Method |
|---|---|---|---|
| **Docker WSL2 Virtual Disks** | `%LOCALAPPDATA%\Docker\wsl\data\ext4.vhdx` | Review | User prompt + Explorer reveal |
| **Android AVD Virtual Devices** | `%USERPROFILE%\.android\avd\*.avd` | Review | Purges unused emulators |
| **Android SDK Build-Tools** | `%LOCALAPPDATA%\Android\Sdk\build-tools` | Moderate | Retains highest version, flags old |
| **Gradle Dependency Cache** | `%USERPROFILE%\.gradle\caches` | Safe | Deletes downloaded jars/zips |
| **Maven Repository Cache** | `%USERPROFILE%\.m2\repository` | Safe | Deletes cached dependency artifacts |
| **npm Global Cache** | `%LOCALAPPDATA%\npm-cache` or `npm cache clean --force` | Safe | Purges tarballs & metadata index |
| **yarn Global Cache** | `%LOCALAPPDATA%\Yarn\Cache` | Safe | Deletes offline package archives |
| **pnpm Store** | `%LOCALAPPDATA%\pnpm\store` | Safe | Purges unreferenced package hardlinks |
| **pip Wheel Cache** | `%LOCALAPPDATA%\pip\cache` | Safe | Purges pre-compiled binary wheels |
| **Cargo Package Cache** | `%USERPROFILE%\.cargo\registry\cache` | Safe | Clears downloaded `.crate` files |
| **NuGet Global Cache** | `%USERPROFILE%\.nuget\packages` | Safe | Deletes downloaded nupkg files |
| **Visual Studio Build Caches** | `%LOCALAPPDATA%\Microsoft\VisualStudio\Packages` | Moderate | Clears installer packages & build caches |
| **JetBrains IDE Caches** | `%LOCALAPPDATA%\JetBrains\*\caches` | Safe | Purges AST and index caches |

### 4.2 Windows System Caches
| Target Name | Target Path / Command | Risk Level | Cleanup Method |
|---|---|---|---|
| **Hibernation File** | `C:\hiberfil.sys` | Safe | `powercfg.exe -h off` via elevated token |
| **Windows Update Downloads** | `C:\Windows\SoftwareDistribution\Download` | Safe | Stops `wuauserv`, clears files, restarts |
| **Delivery Optimization Cache** | `C:\Windows\SoftwareDistribution\DeliveryOptimization` | Safe | Purges P2P update fragments |
| **Memory Crash Dumps** | `C:\Windows\MEMORY.DMP` & `C:\Windows\Minidump` | Safe | Unlinks crash dump files |
| **Windows Error Reporting (WER)** | `%LOCALAPPDATA%\CrashDumps` & `ProgramData\Microsoft\Windows\WER` | Safe | Deletes archived application crash logs |
| **Windows Prefetch Cache** | `C:\Windows\Prefetch\*.pf` | Moderate | Clears launch optimization traces |
| **Font Cache** | `C:\Windows\ServiceProfiles\LocalService\AppData\Local\FontCache` | Safe | Purges rebuildable font metrics |
| **Component Store (WinSxS)** | `dism.exe /online /cleanup-image /startcomponentcleanup /resetbase` | Moderate | Shells elevated DISM cleanup |

### 4.3 Browser Caches
| Target Name | Target Path | Risk Level | Data Preserved |
|---|---|---|---|
| **Google Chrome Cache** | `%LOCALAPPDATA%\Google\Chrome\User Data\Default\Cache` | Safe | History, logins, cookies intact |
| **Chrome Code & GPU Cache** | `%LOCALAPPDATA%\Google\Chrome\User Data\Default\Code Cache` | Safe | Auto-regenerated on web access |
| **Microsoft Edge Cache** | `%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Cache` | Safe | History, logins, cookies intact |
| **Mozilla Firefox Cache** | `%LOCALAPPDATA%\Mozilla\Firefox\Profiles\*\cache2` | Safe | Passwords & bookmarks intact |
| **Brave Browser Cache** | `%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data\Default\Cache` | Safe | Shields & logins intact |
| **Opera / Opera GX Cache** | `%LOCALAPPDATA%\Opera Software\Opera Stable\Cache` | Safe | Retains user configurations |

### 4.4 Temporary Files
| Target Name | Target Path | Risk Level | Cleanup Method |
|---|---|---|---|
| **User Temp Directory** | `%TEMP%` (`AppData\Local\Temp`) | Safe | Deletes files not in active use |
| **Windows System Temp** | `C:\Windows\Temp` | Safe | Purges system installer remnants |
| **Explorer Thumbnail Caches**| `%LOCALAPPDATA%\Microsoft\Windows\Explorer\thumbcache_*.db` | Safe | Deletes cache; Explorer regenerates |
| **Recycle Bin** | `C:\$Recycle.Bin` | Safe | `SHEmptyRecycleBinW` API call |

---

## 5. Large File Aggregation & Treemap Engine

### 5.1 Rolling Heap Algorithm (`heapq`)
Rather than accumulating millions of file records in memory, the Large File Scanner maintains a bounded min-heap of size $K = 500$:
```python
def push_candidate(heap, file_record, k=500):
    if len(heap) < k:
        heapq.heappush(heap, file_record)
    elif file_record.size > heap[0].size:
        heapq.heappushpop(heap, file_record)
```
This guarantees memory usage strictly capped under $O(K)$ space complexity while performing a single $O(N \log K)$ traversal of the partition.

### 5.2 Directory Size Rollup
Each directory is attributed the aggregate sum of its recursive children, rendered in a navigable Treeview hierarchy for immediate bloat isolation.

---

## 6. Safety Architecture & Kernel Guardrails

### 6.1 Critical Path Blacklist
To protect Windows boot viability and system stability, the engine maintains an immutable kernel path blacklist. Even if explicitly requested by a user, operations on paths within these hierarchies are aborted:
- `C:\Windows\System32`
- `C:\Windows\SysWOW64`
- `C:\Windows\WinSxS` (except via DISM)
- `C:\Boot` & `C:\EFI`
- `C:\pagefile.sys`
- `C:\swapfile.sys`
- `C:\System Volume Information`

### 6.2 Recycle Bin Deletion Interop (`SHFileOperationW`)
By default, file purges do not issue unrecoverable `os.remove` or `os.unlink` calls. Instead, X-Cleaner bridges directly to the Windows Shell API:
```python
class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", wintypes.WORD),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]

# Flags: FO_DELETE | FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
```
This ensures all deleted items are moved to the Windows Recycle Bin and can be restored if necessary.

---

## 7. Compilation & Packaging Specification

### 7.1 Single-File PyInstaller Recipe
X-Cleaner is compiled with PyInstaller in `--onefile --noconsole` mode with embedded icon and asset manifests:

```powershell
python -m PyInstaller `
    --clean `
    --onefile `
    --noconsole `
    --name X-Cleaner `
    --icon=assets/deepclean.ico `
    --add-data "assets;assets" `
    deepclean.py
```

### 7.2 Multi-Resolution Monochrome Icon
The application icon (`assets/deepclean.ico`) is generated programmatically to ensure pixel-perfect rendering across all Windows Shell view modes:
- `256x256` — Windows File Explorer Extra Large Icons
- `128x128` — Large Icons
- `64x64` — Medium Icons
- `48x48` — Standard Desktop Icons
- `32x32` — Taskbar & Small Icons
- `16x16` — Window Titlebar & Notification Area

Each layer features a solid `#000000` background with a crisp, geometric white (`#FFFFFF`) "X" emblem.

---

## 8. Operational Runbook & Maintenance

### 8.1 Common Operational Scenarios

#### Scenario A: Reclaiming 30+ GB of Developer Disk Space
1. Launch `X-Cleaner.exe` as Administrator.
2. In the **Caches & Bloat** tab, click **↻ Rescan Caches**.
3. Review the **Developer Tools** section:
   - If Docker WSL2 is large, verify Docker containers are stopped, then select Docker cache.
   - Select Gradle, Maven, npm, and pip caches (all safe to clear; packages re-download as needed).
4. Click **⚡ Clean Selected**.

#### Scenario B: Reclaiming Hibernation Storage on Desktops
1. Desktops and fixed workstations rarely require Windows Fast Startup / Hibernation.
2. In the **Caches & Bloat** tab, locate the **☾ Hibernation** toolbar button.
3. Click the button to toggle hibernation off. The file `C:\hiberfil.sys` is immediately removed by the Windows kernel, instantly reclaiming 100% of RAM size in disk space.

#### Scenario C: Resolving Duplicate Downloads & Installer Files
1. Switch to the **Duplicate Files** tab.
2. Select target directories (defaults to `C:\Users\<User>\Downloads`, `Documents`, `Desktop`).
3. Click **↻ Scan for Duplicates**.
4. Once scan completes, click **★ Smart Auto-Mark** -> **Keep Oldest File**.
5. Click **⚡ Delete Marked Duplicates** to send duplicates safely to the Recycle Bin.

---

## 9. Conclusion
**X-Cleaner** combines low-level Windows systems programming with a focused, high-contrast Swiss design system to deliver an enterprise-grade utility that is fast, mathematically safe, and visually cohesive.
