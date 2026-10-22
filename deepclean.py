#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ X-Cleaner - Complete C: Drive Storage & Duplicate Optimizer
=============================================================

Enterprise-grade Windows storage analyzer & deep-cleaning suite.

Modules
-------
* Developer ecosystem deep caches (Docker, Android, Gradle, Node, Python,
  Rust, Go, .NET, Maven, JetBrains, VS Code family ...)
* Windows system & OS bloat (Delivery Optimization, Windows Update cache,
  crash dumps, WER, shader caches, hibernation, temp folders, Recycle Bin)
* 3-tier smart duplicate engine (size clustering -> 4 KB head hash -> SHA-256)
* Large & orphaned file radar (multi-threaded full-drive traversal)
* Live activity console with persistent log file

Pure standard library (tkinter/ttk + ctypes) -> compiles to a single portable
executable with PyInstaller:

    pyinstaller --onefile --noconsole --name X-Cleaner deepclean.py
"""
from __future__ import annotations

import ctypes
import glob
import hashlib
import math
import os
import queue
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

if os.name == "nt":
    from ctypes import wintypes

# =============================================================================
#  Constants & palette
# =============================================================================
APP_NAME = "X-Cleaner"
APP_TITLE = "⚡ X-Cleaner - Complete C: Drive Storage & Duplicate Optimizer"
APP_VERSION = "1.0.0"
IS_WINDOWS = os.name == "nt"

# Minimalist Monochrome (Black & White) Palette - Swiss / Bauhaus Minimal
CRUST = "#000000"        # Pitch black
MANTLE = "#080808"       # Deep canvas
BASE = "#0d0d0d"         # Surface base / tabs
CARD = "#141414"         # Surface panels & cards
SURFACE0 = "#222222"     # Crisp 1px borders
SURFACE1 = "#2c2c2c"     # Active borders / hover
SURFACE2 = "#3a3a3a"     # Selection / pressed
OVERLAY = "#666666"      # Muted annotations
SUBTEXT = "#999999"      # Secondary metrics & labels
TEXT = "#ffffff"         # Crisp primary white
WHITE = "#ffffff"
BLACK = "#000000"

# Monochrome functional mappings (pure grayscale spectrum)
BLUE = "#ffffff"
LAVENDER = "#e0e0e0"
MAUVE = "#ffffff"
PINK = "#d4d4d4"
RED = "#ffffff"
PEACH = "#999999"
YELLOW = "#cccccc"
GREEN = "#ffffff"
TEAL = "#e0e0e0"
SKY = "#999999"

UI = "Segoe UI"
UI_SEMI = "Segoe UI Semibold"

SPINNER = "◐◓◑◒"
CHECK_ON, CHECK_OFF, CHECK_PART, CHECK_NA = "☑", "☐", "◪", "—"

DEV, SYS, BRO, TMP = "Developer Tools", "System Caches", "Browser Data", "Temp Files"
CATEGORY_ORDER = [DEV, SYS, BRO, TMP]
SAFETY_LABEL = {"Safe": "● Safe", "Moderate": "○ Moderate", "Review": "△ Review"}

HEAD_BYTES = 4096                 # Tier-2 head chunk size
HASH_CHUNK = 1 << 20              # Tier-3 read size (1 MiB)
MAX_DUP_GROUPS_SHOWN = 6000

# File attribute flags (cloud placeholders must never be read -> would download)
FILE_ATTRIBUTE_OFFLINE = 0x00001000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000
CLOUD_MASK = FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_RECALL_ON_OPEN | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS

CREATE_NO_WINDOW = 0x08000000


# =============================================================================
#  Environment / known folders
# =============================================================================
def _env(name: str, default: str = "") -> str:
    return os.environ.get(name) or default


SYSDRIVE = _env("SystemDrive", "C:")
DRIVE_ROOT = SYSDRIVE + "\\"
WINDIR = _env("SystemRoot", SYSDRIVE + "\\Windows")
USERPROFILE = _env("USERPROFILE", os.path.expanduser("~"))
LOCALAPPDATA = _env("LOCALAPPDATA", os.path.join(USERPROFILE, "AppData", "Local"))
APPDATA = _env("APPDATA", os.path.join(USERPROFILE, "AppData", "Roaming"))
PROGRAMDATA = _env("ProgramData", SYSDRIVE + "\\ProgramData")
PROGRAMFILES = _env("ProgramFiles", SYSDRIVE + "\\Program Files")
PROGRAMFILES86 = _env("ProgramFiles(x86)", SYSDRIVE + "\\Program Files (x86)")
LOCALLOW = os.path.join(USERPROFILE, "AppData", "LocalLow")
TEMPDIR = tempfile.gettempdir()

if IS_WINDOWS:
    _shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _ole32 = ctypes.WinDLL("ole32")

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        def __init__(self, text: str):
            super().__init__()
            u = uuid.UUID(text)
            self.Data1, self.Data2, self.Data3 = u.fields[0], u.fields[1], u.fields[2]
            for i, b in enumerate(u.bytes[8:]):
                self.Data4[i] = b

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                    ("pFrom", ctypes.c_void_p), ("pTo", ctypes.c_void_p),
                    ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

    class SHQUERYRBINFO(ctypes.Structure):
        if ctypes.sizeof(ctypes.c_void_p) == 4:
            _pack_ = 1
        _fields_ = [("cbSize", wintypes.DWORD), ("i64Size", ctypes.c_longlong),
                    ("i64NumItems", ctypes.c_longlong)]

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong),
                    ("hwnd", wintypes.HWND), ("lpVerb", wintypes.LPCWSTR),
                    ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                    ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int),
                    ("hInstApp", wintypes.HINSTANCE), ("lpIDList", ctypes.c_void_p),
                    ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                    ("dwHotKey", wintypes.DWORD), ("hIconOrMonitor", wintypes.HANDLE),
                    ("hProcess", wintypes.HANDLE)]

    _shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD,
                                              wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
    _shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    _shell32.SHFileOperationW.argtypes = [ctypes.POINTER(SHFILEOPSTRUCTW)]
    _shell32.SHFileOperationW.restype = ctypes.c_int
    _shell32.SHQueryRecycleBinW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(SHQUERYRBINFO)]
    _shell32.SHQueryRecycleBinW.restype = ctypes.c_long
    _shell32.SHEmptyRecycleBinW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.DWORD]
    _shell32.SHEmptyRecycleBinW.restype = ctypes.c_long
    _shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
    _shell32.ShellExecuteExW.restype = wintypes.BOOL
    _shell32.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                       wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]
    _shell32.ShellExecuteW.restype = ctypes.c_void_p
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _user32.GetParent.argtypes = [wintypes.HWND]
    _user32.GetParent.restype = wintypes.HWND


def known_folder(guid: str, fallback: str) -> str:
    """Resolve a Windows Known Folder (handles OneDrive / relocated folders)."""
    if IS_WINDOWS:
        try:
            out = ctypes.c_wchar_p()
            hr = _shell32.SHGetKnownFolderPath(ctypes.byref(GUID(guid)), 0, None, ctypes.byref(out))
            if hr == 0 and out.value:
                path = out.value
                _ole32.CoTaskMemFree(out)
                return path
        except Exception:
            pass
    return fallback


FOLDER_DESKTOP = known_folder("{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}", os.path.join(USERPROFILE, "Desktop"))
FOLDER_DOCUMENTS = known_folder("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}", os.path.join(USERPROFILE, "Documents"))
FOLDER_DOWNLOADS = known_folder("{374DE290-123F-4565-9164-39C4925E467B}", os.path.join(USERPROFILE, "Downloads"))
FOLDER_PICTURES = known_folder("{33E28130-4E1E-4676-835A-98395C3BC3BB}", os.path.join(USERPROFILE, "Pictures"))
FOLDER_VIDEOS = known_folder("{18989B1D-99B5-455B-841C-AB7C74E4DDFC}", os.path.join(USERPROFILE, "Videos"))
FOLDER_MUSIC = known_folder("{4BD8D571-6D19-48D3-BE97-422220080E43}", os.path.join(USERPROFILE, "Music"))


def default_duplicate_roots() -> list:
    roots = [FOLDER_DOWNLOADS, FOLDER_DOCUMENTS, FOLDER_DESKTOP, FOLDER_PICTURES, FOLDER_VIDEOS]
    return [r for r in roots if r and os.path.isdir(r)]


# =============================================================================
#  Formatting helpers
# =============================================================================
def fmt_size(n) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(n)} B"
            if unit in ("GB", "TB"):
                return f"{n:.2f} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.2f} TB"


def fmt_time(ts) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except (OSError, ValueError, OverflowError):
        return "—"


def fmt_elapsed(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600:d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60:02d}:{sec % 60:02d}"


def parse_human_size(text: str) -> int:
    """Parse docker-style sizes such as '1.2GB', '512kB', '0B'."""
    m = re.search(r"([\d.]+)\s*([kKMGT]?i?B)", text or "")
    if not m:
        return 0
    num = float(m.group(1))
    unit = m.group(2).upper().replace("I", "")
    mult = {"B": 1, "KB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12}.get(unit, 1)
    return int(num * mult)


def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def _hex(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _rgb(t):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in t)


def blend(c1: str, c2: str, t: float) -> str:
    a, b = _hex(c1), _hex(c2)
    return _rgb(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))


# =============================================================================
#  Win32 helpers
# =============================================================================
def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def com_init():
    if IS_WINDOWS:
        try:
            _ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
        except Exception:
            pass


def run_hidden(cmd, timeout=60):
    """Run a console command without flashing a window. Returns CompletedProcess or None."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout,
                              stdin=subprocess.DEVNULL,
                              creationflags=CREATE_NO_WINDOW if IS_WINDOWS else 0)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def run_elevated(exe: str, params: str, timeout: int = 180):
    """Run a program with UAC elevation (runas) and wait. Returns exit code or None if refused."""
    if is_admin():
        r = run_hidden(f'"{exe}" {params}', timeout=timeout)
        return None if r is None else r.returncode
    if not IS_WINDOWS:
        return None
    sei = SHELLEXECUTEINFOW()
    sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
    sei.fMask = 0x00000040 | 0x00000100  # SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC
    sei.lpVerb = "runas"
    sei.lpFile = exe
    sei.lpParameters = params
    sei.nShow = 0  # SW_HIDE
    if not _shell32.ShellExecuteExW(ctypes.byref(sei)):
        return None  # ERROR_CANCELLED (1223) when the user declines UAC
    if not sei.hProcess:
        return 0
    try:
        _kernel32.WaitForSingleObject(sei.hProcess, timeout * 1000)
        code = wintypes.DWORD(0)
        _kernel32.GetExitCodeProcess(sei.hProcess, ctypes.byref(code))
        return int(code.value)
    finally:
        _kernel32.CloseHandle(sei.hProcess)


def send_to_recycle_bin(path: str):
    """Move a file/folder to the Windows Recycle Bin (SHFileOperationW + FOF_ALLOWUNDO)."""
    path = os.path.abspath(path)
    buf = ctypes.create_unicode_buffer(path + "\0\0")
    op = SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = 0x0003                                   # FO_DELETE
    op.pFrom = ctypes.addressof(buf)
    op.pTo = None
    op.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400        # ALLOWUNDO|NOCONFIRMATION|SILENT|NOERRORUI
    res = _shell32.SHFileOperationW(ctypes.byref(op))
    if res != 0 or op.fAnyOperationsAborted:
        raise OSError(res, f"Recycle Bin operation failed (code 0x{res:X})", path)


def recycle_bin_info(root: str = DRIVE_ROOT):
    if not IS_WINDOWS:
        return 0, 0
    info = SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
    if _shell32.SHQueryRecycleBinW(root, ctypes.byref(info)) == 0:
        return int(info.i64Size), int(info.i64NumItems)
    return 0, 0


def empty_recycle_bin(root: str = DRIVE_ROOT) -> bool:
    hr = _shell32.SHEmptyRecycleBinW(None, root, 0x1 | 0x2 | 0x4)
    return hr in (0, -2147418113)  # S_OK or E_UNEXPECTED (already empty)


def hiberfil_size():
    """Return hiberfil.sys size (bytes) or None when hibernation is disabled."""
    try:
        with os.scandir(DRIVE_ROOT) as it:
            for e in it:
                if e.name.lower() == "hiberfil.sys":
                    try:
                        return e.stat(follow_symlinks=False).st_size
                    except OSError:
                        return 0
    except OSError:
        pass
    return None


def open_in_explorer(path: str):
    try:
        if os.path.isfile(path):
            subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
        elif os.path.isdir(path):
            os.startfile(path)
        else:
            parent = os.path.dirname(path)
            if os.path.isdir(parent):
                os.startfile(parent)
    except OSError:
        pass


def apply_dark_titlebar(window):
    if not IS_WINDOWS:
        return
    try:
        window.update_idletasks()
        hwnd = _user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new / pre-20H1)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value),
                                                          ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass


# =============================================================================
#  Safety guard (critical-path exclusion blacklist)
# =============================================================================
class SafetyGuard:
    """Blocks any deletion inside critical Windows locations."""

    def __init__(self):
        n = self._n
        self.hard = [n(p) for p in (
            os.path.join(WINDIR, "System32"), os.path.join(WINDIR, "SysWOW64"),
            os.path.join(WINDIR, "WinSxS"), os.path.join(WINDIR, "servicing"),
            os.path.join(WINDIR, "Boot"), os.path.join(WINDIR, "Fonts"),
            os.path.join(WINDIR, "assembly"), os.path.join(WINDIR, "Microsoft.NET"),
            os.path.join(WINDIR, "SystemApps"), os.path.join(WINDIR, "SystemResources"),
            os.path.join(WINDIR, "Installer"), os.path.join(WINDIR, "INF"),
            os.path.join(PROGRAMFILES, "Windows Defender"),
            os.path.join(PROGRAMFILES, "Windows Defender Advanced Threat Protection"),
            os.path.join(PROGRAMFILES86, "Windows Defender"),
            os.path.join(PROGRAMFILES, "WindowsApps"),
            os.path.join(PROGRAMFILES, "Common Files", "microsoft shared"),
            os.path.join(PROGRAMDATA, "Microsoft", "Windows Defender"),
            os.path.join(PROGRAMDATA, "Microsoft", "Crypto"),
            os.path.join(DRIVE_ROOT, "Boot"), os.path.join(DRIVE_ROOT, "Recovery"),
            os.path.join(DRIVE_ROOT, "System Volume Information"), os.path.join(DRIVE_ROOT, "EFI"),
        )]
        self.windir = n(WINDIR)
        # The only places under C:\Windows we are ever allowed to clean
        self.win_allow = [n(p) for p in (
            os.path.join(WINDIR, "Temp"),
            os.path.join(WINDIR, "SoftwareDistribution", "Download"),
            os.path.join(WINDIR, "SoftwareDistribution", "DeliveryOptimization"),
            os.path.join(WINDIR, "ServiceProfiles", "NetworkService", "AppData", "Local",
                         "Microsoft", "Windows", "DeliveryOptimization", "Cache"),
            os.path.join(WINDIR, "Minidump"),
            os.path.join(WINDIR, "MEMORY.DMP"),
            os.path.join(WINDIR, "LiveKernelReports"),
        )]
        self.exact = {n(p) for p in (
            DRIVE_ROOT, WINDIR, PROGRAMFILES, PROGRAMFILES86, PROGRAMDATA,
            os.path.join(DRIVE_ROOT, "Users"), USERPROFILE, LOCALAPPDATA, APPDATA, LOCALLOW,
            FOLDER_DESKTOP, FOLDER_DOCUMENTS, FOLDER_DOWNLOADS, FOLDER_PICTURES,
            FOLDER_VIDEOS, FOLDER_MUSIC, TEMPDIR,
            os.path.join(DRIVE_ROOT, "pagefile.sys"), os.path.join(DRIVE_ROOT, "swapfile.sys"),
            os.path.join(DRIVE_ROOT, "hiberfil.sys"), os.path.join(DRIVE_ROOT, "bootmgr"),
            os.path.join(DRIVE_ROOT, "BOOTNXT"),
        )}
        self.runtime = []
        mei = getattr(sys, "_MEIPASS", None)
        if mei:
            self.runtime.append(n(mei))
        if getattr(sys, "frozen", False):
            self.exact.add(n(sys.executable))

    @staticmethod
    def _n(p: str) -> str:
        p = os.path.normcase(os.path.abspath(p))
        return p[:-1] if p.endswith("\\") and len(p) > 3 else p

    @staticmethod
    def _under(p: str, base: str) -> bool:
        return p == base or p.startswith(base + "\\") or (base.endswith("\\") and p.startswith(base))

    def add_runtime(self, path: str):
        self.runtime.append(self._n(path))

    def is_hard_protected(self, path: str) -> bool:
        p = self._n(path)
        return any(self._under(p, b) for b in self.hard)

    def is_protected(self, path: str):
        """Return a human-readable reason when *path* must never be deleted, else None."""
        try:
            p = self._n(path)
        except (ValueError, OSError):
            return "invalid path"
        if re.fullmatch(r"[a-z]:\\?", p):
            return "drive root"
        if p in self.exact:
            return "critical system/user folder"
        for b in self.hard:
            if self._under(p, b):
                return "critical Windows component"
        for b in self.runtime:
            if self._under(p, b):
                return "in use by DeepClean"
        if self._under(p, self.windir) and not any(self._under(p, a) for a in self.win_allow):
            return "inside C:\\Windows"
        return None


GUARD = SafetyGuard()


# =============================================================================
#  Logging
# =============================================================================
class Logger:
    def __init__(self):
        self.q: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._fh = None
        self.path = None
        self.dir = os.path.join(LOCALAPPDATA, "X-Cleaner", "logs")
        try:
            os.makedirs(self.dir, exist_ok=True)
            self.path = os.path.join(self.dir, f"deepclean_{datetime.now():%Y%m%d_%H%M%S}.log")
            self._fh = open(self.path, "a", encoding="utf-8", buffering=1)
            GUARD.add_runtime(self.dir)
        except OSError:
            self._fh = None

    def log(self, msg: str, level: str = "INFO", console: bool = True):
        ts = datetime.now().strftime("%H:%M:%S")
        if self._fh:
            with self._lock:
                try:
                    self._fh.write(f"{datetime.now():%Y-%m-%d} {ts} [{level:<5}] {msg}\n")
                except (OSError, ValueError):
                    pass
        if console:
            self.q.put((ts, level, msg))


LOGGER = Logger()


class ScanStats:
    """Shared live counters, read by the UI pump thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self.reset("")

    def reset(self, name: str):
        with self.lock:
            self.name = name
            self.files = 0
            self.dirs = 0
            self.bytes_seen = 0
            self.errors = 0
            self.started = time.time()
        self.set_phase(name, 0.0, 1.0)

    def set_phase(self, phase: str, base: float, weight: float):
        self.phase = phase
        self.base = base
        self.weight = weight
        self.phase_frac = 0.0
        self.frac_fn = None
        self.detail = ""

    def add(self, files=0, dirs=0, nbytes=0):
        with self.lock:
            self.files += files
            self.dirs += dirs
            self.bytes_seen += nbytes

    def overall(self) -> float:
        frac = self.phase_frac
        fn = self.frac_fn
        if fn is not None:
            try:
                frac = fn()
            except Exception:
                pass
        frac = max(0.0, min(1.0, frac))
        return max(0.0, min(1.0, self.base + self.weight * frac))


class OpContext:
    """Per-operation context: cancellation, stats and rate-limited error reporting."""

    CONSOLE_ERROR_LIMIT = 60

    def __init__(self, logger: Logger, stop_event: threading.Event, stats: ScanStats):
        self.logger = logger
        self.stop_event = stop_event
        self.stats = stats
        self.perm_errors = 0
        self.os_errors = 0
        self._shown = 0
        self._lock = threading.Lock()

    @property
    def stopped(self) -> bool:
        return self.stop_event.is_set()

    def fs_error(self, action: str, path: str, exc: BaseException):
        with self._lock:
            if isinstance(exc, PermissionError):
                self.perm_errors += 1
                level = "PERM"
            else:
                self.os_errors += 1
                level = "WARN"
            show = self._shown < self.CONSOLE_ERROR_LIMIT
            if show:
                self._shown += 1
        self.stats.errors += 1
        reason = getattr(exc, "strerror", None) or str(exc)
        self.logger.log(f"{action} skipped · {path} · {reason}", level, console=show)

    def summarize(self):
        total = self.perm_errors + self.os_errors
        if total:
            self.logger.log(
                f"{self.perm_errors:,} permission-protected and {self.os_errors:,} locked/in-use items were "
                f"skipped safely (full details in log file).", "INFO")


# =============================================================================
#  File-system primitives
# =============================================================================
def entry_is_link(e) -> bool:
    """True for symlinks AND NTFS junctions (never traverse those)."""
    try:
        if e.is_symlink():
            return True
        j = getattr(e, "is_junction", None)
        if j is not None and j():
            return True
    except OSError:
        return True
    return False


def path_is_link(p: str) -> bool:
    try:
        if os.path.islink(p):
            return True
        j = getattr(os.path, "isjunction", None)
        return bool(j and j(p))
    except OSError:
        return False


def dir_size(path: str, ctx: OpContext = None, min_age_h: float = 0):
    """Iterative os.scandir size computation. Returns (bytes, files)."""
    total = files = 0
    pend_f = pend_b = pend_d = 0
    cutoff = time.time() - min_age_h * 3600 if min_age_h else None
    stack = [path]
    while stack:
        if ctx and ctx.stopped:
            break
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for e in it:
                    try:
                        if entry_is_link(e):
                            continue
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                            pend_d += 1
                        else:
                            st = e.stat(follow_symlinks=False)
                            pend_f += 1
                            pend_b += st.st_size
                            if cutoff is None or st.st_mtime <= cutoff:
                                total += st.st_size
                                files += 1
                    except OSError:
                        continue
        except OSError as ex:
            if ctx and cur == path:
                ctx.fs_error("Scan", cur, ex)
        if ctx and pend_f + pend_d >= 400:
            ctx.stats.add(pend_f, pend_d, pend_b)
            pend_f = pend_b = pend_d = 0
    if ctx:
        ctx.stats.add(pend_f, pend_d, pend_b)
    return total, files


def parallel_walk(roots, on_file, ctx: OpContext, skip_dir=None, workers: int = 8):
    """Multi-threaded breadth-first traversal using os.scandir and a shared work queue."""
    q: queue.Queue = queue.Queue()
    for r in roots:
        q.put(r)

    def worker():
        while True:
            path = q.get()
            if path is None:
                q.task_done()
                return
            try:
                if ctx.stopped:
                    continue
                nf = nd = nb = 0
                try:
                    with os.scandir(path) as it:
                        for e in it:
                            try:
                                if entry_is_link(e):
                                    continue
                                if e.is_dir(follow_symlinks=False):
                                    if skip_dir is not None and skip_dir(e.path, e.name):
                                        continue
                                    nd += 1
                                    q.put(e.path)
                                else:
                                    st = e.stat(follow_symlinks=False)
                                    nf += 1
                                    nb += st.st_size
                                    on_file(e, st)
                            except OSError as ex:
                                ctx.fs_error("Read", e.path, ex)
                            except Exception as ex:  # never let one entry kill the scan
                                ctx.logger.log(f"Unexpected error on {e.path}: {ex}", "WARN", console=False)
                except OSError as ex:
                    ctx.fs_error("Scan", path, ex)
                ctx.stats.add(nf, nd, nb)
            finally:
                q.task_done()

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, workers))]
    for t in threads:
        t.start()
    q.join()
    for _ in threads:
        q.put(None)
    for t in threads:
        t.join(timeout=5)


def _unlink(path: str):
    try:
        os.unlink(path)
    except PermissionError:
        os.chmod(path, stat.S_IWRITE)  # clear read-only attribute and retry
        os.unlink(path)


def _remove_link(path: str):
    try:
        os.unlink(path)
    except OSError:
        os.rmdir(path)  # junction / directory symlink: removes link only, never the target


def _rmdir_quiet(path: str):
    try:
        os.rmdir(path)
    except PermissionError:
        try:
            os.chmod(path, stat.S_IWRITE)
            os.rmdir(path)
        except OSError:
            pass
    except OSError:
        pass  # not empty (locked or too-young files kept) -> fine


def delete_tree(root: str, ctx: OpContext, keep_root: bool = True, min_age_h: float = 0):
    """Delete the contents of *root* (and *root* itself if keep_root=False).

    Never follows symlinks/junctions, honours the SafetyGuard for every entry,
    clears read-only attributes, and logs (without stopping) locked files.
    Returns (bytes_freed, items_deleted).
    """
    for candidate in (root, os.path.realpath(root)):
        reason = GUARD.is_protected(candidate)
        if reason:
            ctx.logger.log(f"Refused to clean protected location {candidate} ({reason})", "WARN")
            return 0, 0
    cutoff = time.time() - min_age_h * 3600 if min_age_h else None
    freed = deleted = 0
    stack = [(root, False)]
    while stack:
        if ctx.stopped:
            break
        path, post = stack.pop()
        if post:
            if path != root or not keep_root:
                _rmdir_quiet(path)
            continue
        stack.append((path, True))
        try:
            it = os.scandir(path)
        except OSError as ex:
            ctx.fs_error("Open", path, ex)
            continue
        with it:
            for e in it:
                if ctx.stopped:
                    break
                p = e.path
                try:
                    reason = GUARD.is_protected(p)
                    if reason:
                        ctx.logger.log(f"Protected entry kept: {p} ({reason})", "DEBUG", console=False)
                        continue
                    if entry_is_link(e):
                        _remove_link(p)
                        deleted += 1
                        continue
                    if e.is_dir(follow_symlinks=False):
                        stack.append((p, False))
                        continue
                    st = e.stat(follow_symlinks=False)
                    if cutoff is not None and st.st_mtime > cutoff:
                        continue
                    _unlink(p)
                    freed += st.st_size
                    deleted += 1
                except OSError as ex:
                    ctx.fs_error("Delete", p, ex)
    return freed, deleted


def delete_file(path: str, ctx: OpContext) -> int:
    reason = GUARD.is_protected(path)
    if reason:
        ctx.logger.log(f"Refused to delete protected file {path} ({reason})", "WARN")
        return 0
    try:
        st = os.stat(path, follow_symlinks=False)
        _unlink(path)
        return st.st_size
    except FileNotFoundError:
        return 0
    except OSError as ex:
        ctx.fs_error("Delete", path, ex)
        return 0


# =============================================================================
#  Cache / junk catalog
# =============================================================================
@dataclass
class CleanItem:
    key: str
    category: str
    name: str
    paths: list
    safety: str                      # Safe | Moderate | Review
    desc: str
    action: str = "contents"         # contents | dir | files | command | hibernate | recycle | info
    admin: bool = False
    min_age_h: float = 0
    commands: list = field(default_factory=list)
    est_func: object = None
    size: int = 0
    files: int = 0
    selected: bool = False
    scanned: bool = False

    @property
    def selectable(self) -> bool:
        return self.action != "info"


def _pat(base: str, rel: str) -> str:
    if any(c in rel for c in "*?"):
        return os.path.join(glob.escape(base), rel)
    return os.path.join(base, rel)


def _expand(patterns) -> list:
    out, seen = [], set()
    for pat in patterns:
        try:
            if any(c in pat for c in "*?"):
                matches = glob.glob(pat, include_hidden=True)
            else:
                matches = [pat] if os.path.lexists(pat) else []
        except (OSError, ValueError):
            matches = []
        for m in matches:
            k = os.path.normcase(os.path.abspath(m))
            if k not in seen:
                seen.add(k)
                out.append(os.path.abspath(m))
    return out


def _version_tuple(name: str):
    nums = re.findall(r"\d+", name)
    return tuple(int(x) for x in nums) if nums else None


def docker_reclaimable():
    exe = shutil.which("docker")
    if not exe:
        return 0
    r = run_hidden([exe, "system", "df", "--format", "{{.Type}}|{{.Reclaimable}}"], timeout=25)
    if r is None or r.returncode != 0:
        return 0
    total = 0
    for line in r.stdout.splitlines():
        if "|" in line:
            typ, rec = line.split("|", 1)
            if typ.strip() in ("Images", "Build Cache"):
                total += parse_human_size(rec)
    return total


def build_catalog() -> list:
    """Discover all existing cleanable locations on this machine."""
    items: list = []
    U, L, R, PD, W = USERPROFILE, LOCALAPPDATA, APPDATA, PROGRAMDATA, WINDIR

    def add(cat, name, rels, safety, desc, action="contents", admin=False, min_age_h=0, key=None):
        paths = _expand([_pat(b, r) for b, r in rels])
        if action in ("contents", "dir"):
            paths = [p for p in paths if os.path.isdir(p)]
        elif action == "files":
            paths = [p for p in paths if os.path.isfile(p)]
        paths = [p for p in paths if GUARD.is_protected(p) is None or action == "info"]
        if paths:
            items.append(CleanItem(key or f"{cat}:{name}", cat, name, paths, safety, desc,
                                   action, admin, min_age_h))

    def old_versions(cat, label, parent, safety, desc_extra=""):
        if not os.path.isdir(parent):
            return
        groups = defaultdict(list)
        try:
            with os.scandir(parent) as it:
                for e in it:
                    if e.is_dir(follow_symlinks=False) and not entry_is_link(e):
                        v = _version_tuple(e.name)
                        if v:
                            groups[re.sub(r"[\d.]+", "#", e.name)].append((v, e.name, e.path))
        except OSError:
            return
        old, kept = [], []
        for lst in groups.values():
            lst.sort()
            kept.append(lst[-1][1])
            old.extend(lst[:-1])
        if old:
            items.append(CleanItem(
                f"{cat}:{label}", cat, f"{label} ({len(old)} old version{'s' if len(old) > 1 else ''})",
                [p for _, _, p in old], safety,
                f"Keeps newest ({', '.join(kept)}); removes {', '.join(n for _, n, _ in old)}. {desc_extra}".strip(),
                action="dir"))

    # ------------------------------------------------------------------ DEV --
    if shutil.which("docker"):
        items.append(CleanItem(
            "dev:docker-prune", DEV, "Docker build cache & dangling images", [], "Moderate",
            "Runs 'docker builder prune -f' and 'docker image prune -f'. Size is Docker's reclaimable "
            "estimate (engine must be running).", action="command",
            commands=[["docker", "builder", "prune", "-f"], ["docker", "image", "prune", "-f"]],
            est_func=docker_reclaimable))
    add(DEV, "Docker Desktop WSL2 virtual disk (ext4.vhdx)",
        [(L, r"Docker\wsl\data\ext4.vhdx"), (L, r"Docker\wsl\disk\docker_data.vhdx"),
         (L, r"Docker\wsl\main\ext4.vhdx"), (PD, r"DockerDesktop\vm-data\DockerDesktop.vhdx")],
        "Review", "Report-only. Prune Docker first, then compact with 'Optimize-VHD -Mode Full' or diskpart "
                  "'compact vdisk' while Docker is stopped.", action="info")
    add(DEV, "WSL distro virtual disks",
        [(L, r"Packages\*\LocalState\ext4.vhdx"), (L, r"wsl\*\ext4.vhdx")],
        "Review", "Report-only. Linux distro disks never shrink automatically; compact with diskpart.",
        action="info")
    add(DEV, "Android Virtual Devices (AVD)", [(U, r".android\avd")], "Review",
        "Emulator images & snapshots. Deleting removes your virtual devices.")
    add(DEV, "Android SDK system images", [(L, r"Android\Sdk\system-images")], "Review",
        "Emulator system images; re-download through SDK Manager when needed.")
    old_versions(DEV, "Android SDK build-tools", os.path.join(L, r"Android\Sdk\build-tools"), "Moderate")
    old_versions(DEV, "Android NDK", os.path.join(L, r"Android\Sdk\ndk"), "Moderate")
    add(DEV, "Android build cache", [(U, r".android\build-cache"), (U, r".android\cache")], "Safe",
        "Legacy Android Gradle plugin build cache.")
    add(DEV, "Gradle caches", [(U, r".gradle\caches")], "Moderate",
        "Dependency & transform caches; next build re-downloads what it needs.")
    add(DEV, "Gradle daemons & logs", [(U, r".gradle\daemon")], "Safe",
        "Old Gradle daemon registries and logs.")
    old_versions(DEV, "Gradle wrapper distributions", os.path.join(U, r".gradle\wrapper\dists"), "Moderate",
                 "Projects pinned to an old version will re-download it.")
    add(DEV, "npm cache", [(L, "npm-cache")], "Safe", "npm _cacache, _npx and logs.")
    add(DEV, "Yarn cache", [(L, r"Yarn\Cache"), (L, r"Yarn\Berry\cache")], "Safe",
        "Yarn classic & Berry global caches.")
    add(DEV, "pnpm store", [(L, r"pnpm\store"), (L, "pnpm-cache"), (L, r"pnpm\cache")], "Moderate",
        "Content-addressable store; projects re-link on next install.")
    add(DEV, "node-gyp headers cache", [(L, r"node-gyp\Cache"), (U, ".node-gyp")], "Safe",
        "Node header tarballs downloaded for native addon builds.")
    add(DEV, "Bun install cache", [(U, r".bun\install\cache")], "Safe", "Bun package cache.")
    add(DEV, "pip cache", [(L, r"pip\cache"), (L, r"pip\Cache")], "Safe", "Downloaded wheels and HTTP cache.")
    add(DEV, "uv cache", [(L, r"uv\cache")], "Safe", "uv wheel/source cache.")
    add(DEV, "Poetry cache", [(L, r"pypoetry\Cache")], "Safe", "Poetry artifacts & repository cache.")
    add(DEV, "Pipenv cache", [(L, r"pipenv\pipenv\Cache")], "Safe", "Pipenv download cache.")
    add(DEV, "virtualenv seed cache", [(L, r"pypa\virtualenv")], "Safe", "Embedded wheel seeds.")
    add(DEV, "Conda package cache",
        [(U, r".conda\pkgs"), (U, r"anaconda3\pkgs"), (U, r"miniconda3\pkgs"), (U, r"miniforge3\pkgs"),
         (PD, r"anaconda3\pkgs"), (PD, r"miniconda3\pkgs")], "Review",
        "Tarballs & extracted packages. Prefer 'conda clean --all' if environments are hard-linked.")
    add(DEV, "Hugging Face model cache", [(U, r".cache\huggingface")], "Review",
        "Downloaded ML models/datasets. Large; re-download required.")
    add(DEV, "PyTorch hub cache", [(U, r".cache\torch")], "Review", "Downloaded torch hub checkpoints.")
    add(DEV, "Cargo registry cache", [(U, r".cargo\registry\cache"), (U, r".cargo\registry\src")], "Safe",
        "Crate archives and extracted sources (binaries in .cargo\\bin untouched).")
    add(DEV, "Cargo git checkouts", [(U, r".cargo\git\checkouts")], "Safe", "Git dependency checkouts.")
    add(DEV, "Go build cache", [(L, "go-build")], "Safe", "Go compiler build cache.")
    add(DEV, "Go module cache", [(U, r"go\pkg\mod")], "Moderate", "Downloaded Go modules (read-only files handled).")
    add(DEV, "NuGet global packages", [(U, r".nuget\packages")], "Moderate",
        "Restored NuGet packages; next restore re-downloads.")
    add(DEV, "NuGet HTTP cache", [(L, r"NuGet\v3-cache"), (L, r"NuGet\Cache"), (L, r"NuGet\plugins-cache")],
        "Safe", "NuGet HTTP/v3 cache.")
    add(DEV, "Maven local repository", [(U, r".m2\repository")], "Moderate", "Downloaded Maven artifacts.")
    add(DEV, "JetBrains IDE caches & logs", [(L, r"JetBrains\*\caches"), (L, r"JetBrains\*\log")], "Moderate",
        "Index caches of installed IDEs; they re-index on next launch.")

    # Older JetBrains / Android Studio versions
    rx = re.compile(r"^(?P<prod>[A-Za-z][A-Za-z\-]*?)(?P<ver>\d{4}\.\d+)$")
    found = defaultdict(lambda: defaultdict(list))
    for base, google in ((os.path.join(R, "JetBrains"), False), (os.path.join(L, "JetBrains"), False),
                         (os.path.join(R, "Google"), True), (os.path.join(L, "Google"), True)):
        try:
            with os.scandir(base) as it:
                for e in it:
                    m = rx.match(e.name)
                    if not m or not e.is_dir(follow_symlinks=False):
                        continue
                    prod = m.group("prod")
                    if google and not prod.startswith("AndroidStudio"):
                        continue
                    found[prod][tuple(int(x) for x in m.group("ver").split("."))].append(e.path)
        except OSError:
            continue
    for prod, versions in found.items():
        if len(versions) < 2:
            continue
        latest = max(versions)
        label = prod.replace("AndroidStudio", "Android Studio ").strip()
        for ver, paths in sorted(versions.items()):
            if ver == latest:
                continue
            vs = ".".join(map(str, ver))
            items.append(CleanItem(
                f"dev:ide:{prod}{vs}", DEV, f"Old IDE data: {label} {vs}", paths, "Moderate",
                f"Superseded by {label} {'.'.join(map(str, latest))}: settings, plugins, caches & logs "
                f"of the old version.", action="dir"))

    for editor in ("Code", "Code - Insiders", "Cursor", "Windsurf", "VSCodium"):
        add(DEV, f"{editor}: cached data & logs",
            [(R, rf"{editor}\CachedData"), (R, rf"{editor}\Cache"), (R, rf"{editor}\Code Cache"),
             (R, rf"{editor}\GPUCache"), (R, rf"{editor}\CachedExtensionVSIXs"), (R, rf"{editor}\logs")],
            "Safe", "Chromium/Electron caches, old update data and logs.")
        add(DEV, f"{editor}: workspace storage", [(R, rf"{editor}\User\workspaceStorage")], "Moderate",
            "Per-workspace state (open editors, local history). Rebuilt automatically.")

    # ------------------------------------------------------------------ SYS --
    add(SYS, "Delivery Optimization cache",
        [(W, r"SoftwareDistribution\DeliveryOptimization"),
         (W, r"ServiceProfiles\NetworkService\AppData\Local\Microsoft\Windows\DeliveryOptimization\Cache")],
        "Safe", "Peer-to-peer update cache. [Admin]", admin=True)
    add(SYS, "Windows Update download cache", [(W, r"SoftwareDistribution\Download")], "Safe",
        "Already-installed update payloads. [Admin]", admin=True)
    add(SYS, "User crash dumps", [(L, "CrashDumps")], "Safe", "Application crash dump files.")
    add(SYS, "Windows Error Reporting (system)",
        [(PD, r"Microsoft\Windows\WER\ReportArchive"), (PD, r"Microsoft\Windows\WER\ReportQueue"),
         (PD, r"Microsoft\Windows\WER\Temp")], "Safe", "Queued/archived error reports. [Admin]", admin=True)
    add(SYS, "Windows Error Reporting (user)", [(L, r"Microsoft\Windows\WER")], "Safe", "User error reports.")
    add(SYS, "System memory dumps", [(W, "Minidump"), (W, "LiveKernelReports")], "Safe",
        "Kernel minidumps & live kernel reports. [Admin]", admin=True)
    add(SYS, "Full memory dump (MEMORY.DMP)", [(W, "MEMORY.DMP")], "Safe",
        "Complete kernel crash dump. [Admin]", action="files", admin=True)
    add(SYS, "DirectX shader cache", [(L, "D3DSCache")], "Safe", "Rebuilt on demand by DirectX.")
    add(SYS, "NVIDIA shader caches",
        [(L, r"NVIDIA\DXCache"), (L, r"NVIDIA\GLCache"), (L, r"NVIDIA Corporation\NV_Cache"),
         (PD, r"NVIDIA Corporation\NV_Cache"), (LOCALLOW, r"NVIDIA\PerDriverVersion\DXCache")],
        "Safe", "Compiled GPU shaders; regenerated by games/driver.")
    add(SYS, "AMD shader caches",
        [(L, r"AMD\DxCache"), (L, r"AMD\DxcCache"), (L, r"AMD\GLCache"), (L, r"AMD\VkCache"),
         (L, r"AMD\OglCache")], "Safe", "Compiled GPU shaders; regenerated automatically.")
    add(SYS, "Intel shader caches", [(L, r"Intel\ShaderCache"), (LOCALLOW, r"Intel\ShaderCache")], "Safe",
        "Compiled GPU shaders; regenerated automatically.")
    add(SYS, "Explorer thumbnail & icon cache",
        [(L, r"Microsoft\Windows\Explorer\thumbcache_*.db"), (L, r"Microsoft\Windows\Explorer\iconcache_*.db")],
        "Safe", "Rebuilt by Explorer (files in use are skipped).", action="files")
    add(SYS, "Previous Windows installation (Windows.old)", [(DRIVE_ROOT, "Windows.old")], "Review",
        "Rollback data of a previous Windows version. If access is denied use Disk Cleanup. [Admin]",
        action="dir", admin=True)
    if hiberfil_size() is not None:
        items.append(CleanItem(
            "sys:hiberfil", SYS, "Windows hibernation file (hiberfil.sys)", [os.path.join(DRIVE_ROOT, "hiberfil.sys")],
            "Moderate", "Disables hibernation & Fast Startup via 'powercfg -h off' (UAC prompt). "
                        "Re-enable any time with the Hibernation toggle.", action="hibernate", admin=True))

    # ------------------------------------------------------------------ BRO --
    chromium = [("Google Chrome", os.path.join(L, r"Google\Chrome\User Data")),
                ("Microsoft Edge", os.path.join(L, r"Microsoft\Edge\User Data")),
                ("Brave", os.path.join(L, r"BraveSoftware\Brave-Browser\User Data")),
                ("Vivaldi", os.path.join(L, r"Vivaldi\User Data")),
                ("Chromium", os.path.join(L, r"Chromium\User Data"))]
    for label, base in chromium:
        add(BRO, f"{label}: cache",
            [(base, r"*\Cache"), (base, r"*\Code Cache"), (base, r"*\GPUCache"), (base, r"*\DawnCache"),
             (base, r"*\DawnGraphiteCache"), (base, r"*\DawnWebGPUCache"), (base, "ShaderCache"),
             (base, "GrShaderCache"), (base, "GraphiteDawnCache")],
            "Safe", "HTTP, JavaScript bytecode and GPU caches for all profiles (close browser for best results).")
        add(BRO, f"{label}: service worker caches",
            [(base, r"*\Service Worker\CacheStorage"), (base, r"*\Service Worker\ScriptCache")],
            "Moderate", "Offline caches of web apps; sites rebuild them on next visit.")
    add(BRO, "Opera: cache",
        [(L, r"Opera Software\Opera Stable\Cache"), (R, r"Opera Software\Opera Stable\Code Cache"),
         (R, r"Opera Software\Opera Stable\GPUCache"), (L, r"Opera Software\Opera GX Stable\Cache")],
        "Safe", "Opera / Opera GX caches.")
    add(BRO, "Mozilla Firefox: cache",
        [(L, r"Mozilla\Firefox\Profiles\*\cache2"), (L, r"Mozilla\Firefox\Profiles\*\startupCache"),
         (L, r"Mozilla\Firefox\Profiles\*\thumbnails")], "Safe", "Firefox disk cache for all profiles.")
    add(BRO, "Windows INetCache", [(L, r"Microsoft\Windows\INetCache")], "Safe",
        "Legacy IE / WebView cache (locked files skipped).")
    add(BRO, "Discord / Slack / Teams web caches",
        [(R, r"discord\Cache"), (R, r"discord\Code Cache"), (R, r"discord\GPUCache"),
         (R, r"Slack\Cache"), (R, r"Slack\Code Cache"), (R, r"Slack\Service Worker\CacheStorage"),
         (R, r"Microsoft\Teams\Cache"), (R, r"Microsoft\Teams\Service Worker\CacheStorage")],
        "Safe", "Electron app caches.")
    add(BRO, "Spotify offline cache", [(L, r"Spotify\Storage"), (L, r"Spotify\Data")], "Moderate",
        "Streaming cache; downloaded playlists will re-download.")

    # ------------------------------------------------------------------ TMP --
    add(TMP, "User temp folder (%TEMP%)", [(TEMPDIR, "")], "Safe",
        "Temporary files older than 24 h (newer files are kept for running installers).", min_age_h=24)
    add(TMP, "Windows temp folder", [(W, "Temp")], "Safe",
        "System temporary files older than 24 h. [Admin]", admin=True, min_age_h=24)
    items.append(CleanItem("tmp:recycle", TMP, f"Recycle Bin ({SYSDRIVE})", [os.path.join(DRIVE_ROOT, "$Recycle.Bin")],
                           "Moderate", "Permanently empties the Recycle Bin for this drive.", action="recycle"))
    return items


def measure_item(item: CleanItem, ctx: OpContext) -> CleanItem:
    total = files = 0
    try:
        if item.action in ("contents", "dir", "info", "files"):
            for p in item.paths:
                if ctx.stopped:
                    break
                if os.path.isdir(p) and not (item.action == "info"):
                    s, n = dir_size(p, ctx, item.min_age_h)
                else:
                    try:
                        s, n = os.stat(p).st_size, 1
                    except OSError:
                        s = n = 0
                total += s
                files += n
        elif item.action == "hibernate":
            total = hiberfil_size() or 0
            files = 1 if total else 0
        elif item.action == "recycle":
            total, files = recycle_bin_info()
        elif item.action == "command" and callable(item.est_func):
            total = int(item.est_func() or 0)
    except Exception as ex:
        ctx.logger.log(f"Measure failed for {item.name}: {ex}", "WARN")
    item.size, item.files, item.scanned = total, files, True
    return item


def set_hibernation(enabled: bool):
    exe = os.path.join(WINDIR, "System32", "powercfg.exe")
    return run_elevated(exe, "/hibernate " + ("on" if enabled else "off"))


def clean_item(item: CleanItem, ctx: OpContext) -> int:
    lg = ctx.logger
    a = item.action
    if a == "info":
        lg.log(f"{item.name} is report-only — nothing deleted.", "INFO")
        return 0
    if a in ("contents", "dir"):
        freed = 0
        for p in item.paths:
            if ctx.stopped:
                break
            if not os.path.lexists(p):
                continue
            if os.path.isdir(p):
                f, n = delete_tree(p, ctx, keep_root=(a == "contents"), min_age_h=item.min_age_h)
                lg.log(f"  {p} → {n:,} items removed, {fmt_size(f)} freed", "CLEAN")
                freed += f
            else:
                freed += delete_file(p, ctx)
        return freed
    if a == "files":
        freed = 0
        for p in item.paths:
            f = delete_file(p, ctx)
            if f:
                lg.log(f"  Deleted {p} ({fmt_size(f)})", "CLEAN")
            freed += f
        return freed
    if a == "hibernate":
        before = hiberfil_size() or 0
        lg.log("Requesting elevation for 'powercfg -h off' …", "INFO")
        code = set_hibernation(False)
        if code is None:
            lg.log("Hibernation change cancelled (UAC declined).", "WARN")
            return 0
        if code != 0:
            lg.log(f"powercfg exited with code {code}.", "WARN")
        time.sleep(1.0)
        after = hiberfil_size() or 0
        return max(0, before - after)
    if a == "recycle":
        before, _ = recycle_bin_info()
        if empty_recycle_bin():
            after, _ = recycle_bin_info()
            return max(0, before - after)
        lg.log("Recycle Bin could not be emptied.", "WARN")
        return 0
    if a == "command":
        reclaimed = 0
        for cmd in item.commands:
            exe = shutil.which(cmd[0])
            if not exe:
                lg.log(f"{cmd[0]} not found on PATH.", "WARN")
                continue
            lg.log(f"  Running: {' '.join(cmd)}", "CLEAN")
            r = run_hidden([exe] + cmd[1:], timeout=900)
            if r is None:
                lg.log("  Command failed to start or timed out.", "WARN")
            elif r.returncode != 0:
                lg.log(f"  Exit {r.returncode}: {(r.stderr or r.stdout).strip()[:300]}", "WARN")
            else:
                for line in r.stdout.splitlines():
                    if "reclaimed space" in line.lower():
                        reclaimed += parse_human_size(line.split(":", 1)[-1])
                        lg.log(f"  {line.strip()}", "OK")
        return reclaimed
    return 0


# =============================================================================
#  Duplicate engine (3-tier hash filter)
# =============================================================================
@dataclass
class FileRec:
    path: str
    size: int
    mtime: float


@dataclass
class DupGroup:
    size: int
    digest: str
    files: list

    @property
    def waste(self) -> int:
        return self.size * (len(self.files) - 1)


@dataclass
class LargeRec:
    path: str
    size: int
    mtime: float
    ext: str
    insight: str
    protected: bool


DUP_SKIP_DIRS = {".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv", "site-packages",
                 ".gradle", ".idea", ".vs", "$recycle.bin", "system volume information", "appdata", ".cache"}


class _Counter:
    def __init__(self):
        self.value = 0
        self._lock = threading.Lock()

    def add(self, n: int):
        with self._lock:
            self.value += n


def _dedupe_roots(roots):
    norm = sorted({os.path.normcase(os.path.abspath(r)): os.path.abspath(r) for r in roots}.items(),
                  key=lambda kv: len(kv[0]))
    kept = []
    for k, v in norm:
        if not any(k == kk or k.startswith(kk.rstrip("\\") + "\\") for kk, _ in kept):
            kept.append((k, v))
    return [v for _, v in kept]


def _head_digest(rec: FileRec, ctx: OpContext):
    if ctx.stopped:
        return None
    try:
        with open(rec.path, "rb", buffering=0) as fh:
            return hashlib.sha256(fh.read(HEAD_BYTES)).hexdigest()
    except OSError as ex:
        ctx.fs_error("Hash", rec.path, ex)
        return None


def _full_digest(rec: FileRec, ctx: OpContext, counter: _Counter):
    h = hashlib.sha256()
    try:
        with open(rec.path, "rb", buffering=0) as fh:
            while True:
                if ctx.stopped:
                    return None
                chunk = fh.read(HASH_CHUNK)
                if not chunk:
                    break
                h.update(chunk)
                counter.add(len(chunk))
        return h.hexdigest()
    except OSError as ex:
        ctx.fs_error("Hash", rec.path, ex)
        return None


def find_duplicates(ctx: OpContext, roots, min_size: int) -> list:
    lg, st = ctx.logger, ctx.stats
    roots = _dedupe_roots([r for r in roots if os.path.isdir(r)])
    if not roots:
        lg.log("No valid folders selected for duplicate scanning.", "WARN")
        return []
    lg.log("Duplicate engine targets: " + " ; ".join(roots), "SCAN")
    t0 = time.time()

    records: list = []

    def skip_dir(path, name):
        return name.lower() in DUP_SKIP_DIRS or GUARD.is_hard_protected(path)

    def on_file(e, s):
        if s.st_size >= min_size and not (getattr(s, "st_file_attributes", 0) & CLOUD_MASK):
            records.append(FileRec(e.path, s.st_size, s.st_mtime))

    f0 = st.files
    st.detail = "Enumerating files (cloud-only placeholders are skipped)…"
    st.frac_fn = lambda: 0.25 * (1 - 1 / (1 + (st.files - f0) / 25000))
    parallel_walk(roots, on_file, ctx, skip_dir, workers=8)
    st.frac_fn, st.phase_frac = None, 0.25
    if ctx.stopped:
        return []
    uniq = {}
    for r in records:
        uniq.setdefault(os.path.normcase(r.path), r)
    records = list(uniq.values())

    # ---- Tier 1: size clustering (zero I/O) ---------------------------------
    by_size = defaultdict(list)
    for r in records:
        by_size[r.size].append(r)
    clusters = {s: lst for s, lst in by_size.items() if len(lst) > 1}
    cand = [r for lst in clusters.values() for r in lst]
    lg.log(f"Tier 1 · size clustering: {len(records):,} files → {len(cand):,} candidates in "
           f"{len(clusters):,} size clusters ({len(records) - len(cand):,} unique sizes eliminated, 0 bytes read)",
           "SCAN")
    if not cand:
        lg.log("No duplicates found.", "OK")
        return []

    # ---- Tier 2: 4 KB head-chunk hash ---------------------------------------
    st.detail = f"Tier 2 · hashing first 4 KB of {len(cand):,} candidates"
    heads = defaultdict(list)
    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, (rec, dg) in enumerate(zip(cand, ex.map(lambda r: _head_digest(r, ctx), cand))):
            if dg is not None:
                heads[(rec.size, dg)].append(rec)
            if i % 200 == 0:
                st.phase_frac = 0.25 + 0.20 * (i / len(cand))
    if ctx.stopped:
        return []
    heads = {k: v for k, v in heads.items() if len(v) > 1}
    n2 = sum(len(v) for v in heads.values())
    lg.log(f"Tier 2 · head-chunk hash: {len(cand):,} → {n2:,} files share identical first 4 KB "
           f"({len(cand) - n2:,} eliminated)", "SCAN")

    # ---- Tier 3: full SHA-256 -------------------------------------------------
    final = defaultdict(list)
    need_full = []
    for (size, dg), lst in heads.items():
        if size <= HEAD_BYTES:
            final[(size, dg)].extend(lst)  # head hash already covers the full content
        else:
            need_full.extend(lst)
    total_bytes = sum(r.size for r in need_full) or 1
    counter = _Counter()
    st.detail = f"Tier 3 · full SHA-256 of {len(need_full):,} files ({fmt_size(total_bytes)})"
    st.frac_fn = lambda: 0.45 + 0.55 * (counter.value / total_bytes)
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_full_digest, r, ctx, counter): r for r in need_full}
        for fut in as_completed(futs):
            rec = futs[fut]
            try:
                dg = fut.result()
            except Exception:
                dg = None
            if dg is not None:
                final[(rec.size, dg)].append(rec)
    st.frac_fn, st.phase_frac = None, 1.0
    if ctx.stopped:
        return []

    # ---- collapse NTFS hard links (same file id => no real waste) -------------
    groups = []
    for (size, dg), lst in final.items():
        if len(lst) < 2:
            continue
        seen_ids, uniq_files = set(), []
        for r in lst:
            try:
                s = os.stat(r.path)
                fid = (s.st_dev, s.st_ino)
            except OSError:
                continue
            if fid[1] and fid in seen_ids:
                continue
            seen_ids.add(fid)
            uniq_files.append(r)
        if len(uniq_files) > 1:
            uniq_files.sort(key=lambda r: r.mtime)
            groups.append(DupGroup(size, dg, uniq_files))
    groups.sort(key=lambda g: g.waste, reverse=True)
    waste = sum(g.waste for g in groups)
    lg.log(f"Tier 3 · SHA-256 verified: {len(groups):,} duplicate clusters, "
           f"{sum(len(g.files) - 1 for g in groups):,} redundant copies, {fmt_size(waste)} reclaimable "
           f"({time.time() - t0:.1f}s)", "OK")
    return groups


# =============================================================================
#  Large & orphaned file radar
# =============================================================================
EXT_INSIGHT = {
    "Disk image": {".iso", ".img", ".dmg", ".wim", ".esd"},
    "Virtual disk": {".vhd", ".vhdx", ".vmdk", ".vdi", ".qcow2", ".avhdx"},
    "Archive": {".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".xz", ".bz2", ".zst", ".cab"},
    "Installer": {".exe", ".msi", ".msix", ".msixbundle", ".appx", ".msp", ".apk"},
    "Video": {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".webm", ".m4v", ".flv", ".ts"},
    "Crash dump": {".dmp", ".hdmp", ".mdmp"},
    "Backup / log": {".bak", ".old", ".log", ".tmp", ".etl"},
    "Database": {".db", ".sqlite", ".mdf", ".ldf", ".pst", ".ost"},
    "ML model": {".safetensors", ".ckpt", ".pt", ".pth", ".gguf", ".onnx", ".bin"},
}


def large_insight(path: str, ext: str, mtime: float, protected: bool) -> str:
    if protected:
        return "System file (protected)"
    label = next((k for k, v in EXT_INSIGHT.items() if ext in v), "File")
    days = int((time.time() - mtime) / 86400) if mtime else 0
    tags = [label]
    low = os.path.normcase(path)
    if low.startswith(os.path.normcase(FOLDER_DOWNLOADS)) and label in ("Installer", "Disk image", "Archive"):
        tags.append("likely orphaned download")
    if days >= 365:
        tags.append(f"untouched {days // 365}y+")
    elif days >= 180:
        tags.append(f"untouched {days}d")
    return " · ".join(tags)


def scan_large_files(ctx: OpContext, threshold: int) -> list:
    st, lg = ctx.stats, ctx.logger
    try:
        used = shutil.disk_usage(DRIVE_ROOT).used or 1
    except OSError:
        used = 1
    b0 = st.bytes_seen
    st.frac_fn = lambda: min(0.99, (st.bytes_seen - b0) / used)
    st.detail = f"Traversing {DRIVE_ROOT} for files ≥ {fmt_size(threshold)}"
    skip = {os.path.normcase(p) for p in (os.path.join(DRIVE_ROOT, "$Recycle.Bin"),
                                          os.path.join(DRIVE_ROOT, "System Volume Information"),
                                          os.path.join(WINDIR, "WinSxS"))}
    results: list = []

    def skip_dir(path, name):
        return os.path.normcase(path) in skip

    def on_file(e, s):
        if s.st_size >= threshold and not (getattr(s, "st_file_attributes", 0) & CLOUD_MASK):
            results.append((e.path, s.st_size, s.st_mtime))

    workers = min(16, max(4, (os.cpu_count() or 4) * 2))
    lg.log(f"Large File Radar: {workers} scanner threads traversing {DRIVE_ROOT}", "SCAN")
    parallel_walk([DRIVE_ROOT], on_file, ctx, skip_dir, workers=workers)
    st.frac_fn, st.phase_frac = None, 1.0
    out = []
    for path, size, mtime in results:
        ext = os.path.splitext(path)[1].lower()
        prot = GUARD.is_protected(path) is not None
        out.append(LargeRec(path, size, mtime, ext or "—", large_insight(path, ext, mtime, prot), prot))
    out.sort(key=lambda r: r.size, reverse=True)
    lg.log(f"Large File Radar: {len(out):,} files ≥ {fmt_size(threshold)} totalling "
           f"{fmt_size(sum(r.size for r in out))}", "OK")
    return out


# =============================================================================
#  Custom widgets
# =============================================================================
def draw_pill_gradient(canvas, x0, y0, x1, y1, c1, c2, radius, tag=""):
    w = int(x1 - x0)
    if w <= 0:
        return
    r = max(0.0, min(radius, (y1 - y0) / 2, w / 2))
    for i in range(w):
        dx = min(i, w - 1 - i)
        inset = r - math.sqrt(max(0.0, r * r - (r - dx - 0.5) ** 2)) if dx < r else 0
        canvas.create_line(x0 + i, y0 + inset, x0 + i, y1 - inset,
                           fill=blend(c1, c2, i / max(1, w - 1)), tags=tag)


class GradientButton(tk.Canvas):
    """Minimalist inverted high-contrast action button (White fill, Black text)."""

    def __init__(self, master, text, command, c1=WHITE, c2=WHITE, width=260, height=48,
                 font=(UI_SEMI, 12), bg=MANTLE, fg=BLACK):
        super().__init__(master, width=width, height=height, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self._text, self._cmd, self._c1, self._c2 = text, command, c1, c2
        self._font, self._fg, self._btn_w, self._btn_h = font, fg, width, height
        self._enabled, self._hover = True, False
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._click)
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def _set_hover(self, v):
        self._hover = v
        self._draw()

    def _click(self, _e):
        if self._enabled and self._cmd:
            self._cmd()

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()

    def set_text(self, text):
        self._text = text
        self._draw()

    def _draw(self):
        self.delete("all")
        w = self.winfo_width() if self.winfo_width() > 1 else self._btn_w
        h = self.winfo_height() if self.winfo_height() > 1 else self._btn_h
        if not self._enabled:
            c1 = c2 = SURFACE0
            fg = OVERLAY
        elif self._hover:
            c1 = c2 = "#e0e0e0"
            fg = BLACK
        else:
            c1 = c2 = WHITE
            fg = BLACK
        draw_pill_gradient(self, 0, 0, w, h, c1, c2, h / 2)
        self.create_text(w / 2, h / 2, text=self._text, fill=fg, font=self._font)


# =============================================================================
#  Main application
# =============================================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self.logger = LOGGER
        self.title(APP_TITLE)
        self.configure(bg=MANTLE)
        self.scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        self.report_callback_exception = self._tk_error
        families = set(tkfont.families(self))
        self.mono = "Cascadia Mono" if "Cascadia Mono" in families else "Consolas"

        try:
            ico = resource_path(os.path.join("assets", "deepclean.ico"))
            if os.path.exists(ico):
                self.iconbitmap(default=ico)
        except tk.TclError:
            pass

        self.ui_q: queue.Queue = queue.Queue()
        self.stats = ScanStats()
        self.stop_event = threading.Event()
        self.busy = False
        self.busy_name = ""
        self._spin = 0
        self._busy_widgets = []
        self.session_freed = 0
        self.session_recycled = 0
        self.drive = None

        self.cache_items: list = []
        self.cache_iids: dict = {}
        self.cat_iids: dict = {}
        self.dup_groups: list = []
        self.dup_marked: set = set()
        self.dup_iid_map: dict = {}
        self.dup_roots = default_duplicate_roots()
        self.large_files: list = []
        self.large_iid_map: dict = {}
        self.large_sort = ("size", True)

        self._setup_style()
        self._build_ui()

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(self.S(1420), sw - 60), min(self.S(920), sh - 80)
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 3)}")
        self.minsize(min(self.S(1100), sw - 60), min(self.S(720), sh - 80))
        self.deiconify()
        apply_dark_titlebar(self)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_drive()
        self._refresh_hibernation()
        self.after(80, self._pump)
        self.after(5000, self._auto_drive_refresh)

        self.logger.log(f"{APP_NAME} v{APP_VERSION} started — {'Administrator' if is_admin() else 'standard user'} "
                        f"session on {SYSDRIVE}", "OK")
        if self.logger.path:
            self.logger.log(f"Log file: {self.logger.path}", "INFO")
        if not is_admin():
            self.logger.log("Tip: 'Restart as Administrator' unlocks Windows Update, Delivery Optimization, "
                            "WER and C:\\Windows\\Temp cleaning.", "WARN")
        self._run_task("Discovering cleanable locations", self._task_scan_caches, quiet=True)

    # ------------------------------------------------------------------ utils
    def S(self, v) -> int:
        return int(round(v * self.scale))

    def ui(self, fn, *args):
        self.ui_q.put((fn, args))

    def _tk_error(self, exc, val, tb):
        self.logger.log("UI error: " + "".join(traceback.format_exception(exc, val, tb)).strip(), "ERROR")

    # ------------------------------------------------------------------ style
    def _setup_style(self):
        S = self.S
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure(".", background=BASE, foreground=TEXT, fieldbackground=CARD, bordercolor=SURFACE0,
                     darkcolor=BASE, lightcolor=BASE, troughcolor=CRUST, focuscolor=BASE,
                     selectbackground=SURFACE1, selectforeground=TEXT, insertcolor=TEXT, font=(UI, 10))
        st.configure("TFrame", background=BASE)
        st.configure("TNotebook", background=MANTLE, borderwidth=0, tabmargins=(S(18), S(4), S(18), 0))
        st.configure("TNotebook.Tab", background=MANTLE, foreground=SUBTEXT, padding=(S(20), S(9)),
                     borderwidth=0, font=(UI_SEMI, 10))
        st.map("TNotebook.Tab", background=[("selected", BASE), ("active", CARD)],
               foreground=[("selected", WHITE), ("active", TEXT)])
        st.configure("Treeview", background=MANTLE, fieldbackground=MANTLE, foreground=TEXT,
                     rowheight=S(28), borderwidth=0, relief="flat", font=(UI, 10), indent=S(14))
        st.map("Treeview", background=[("selected", SURFACE1)], foreground=[("selected", WHITE)])
        st.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        st.configure("Treeview.Heading", background=CRUST, foreground=SUBTEXT, relief="flat", borderwidth=0,
                     font=(UI_SEMI, 9), padding=(S(8), S(7)))
        st.map("Treeview.Heading", background=[("active", SURFACE0)], foreground=[("active", WHITE)])
        st.configure("TButton", background=CARD, foreground=TEXT, borderwidth=1, bordercolor=SURFACE0,
                     focusthickness=0, padding=(S(14), S(7)), font=(UI, 10))
        st.map("TButton", background=[("disabled", CARD), ("pressed", SURFACE2), ("active", SURFACE1)],
               foreground=[("disabled", OVERLAY)], bordercolor=[("active", SURFACE2)])
        for name, bg, act, fg in (("Accent", WHITE, "#e6e6e6", BLACK),
                                  ("Danger", CARD, SURFACE1, WHITE),
                                  ("Success", WHITE, "#e6e6e6", BLACK),
                                  ("Mauve", WHITE, "#e6e6e6", BLACK)):
            st.configure(f"{name}.TButton", background=bg, foreground=fg, font=(UI_SEMI, 10),
                         borderwidth=1, bordercolor=SURFACE1 if bg != WHITE else WHITE)
            st.map(f"{name}.TButton", background=[("disabled", CARD), ("pressed", act), ("active", act)],
                   foreground=[("disabled", OVERLAY)], bordercolor=[("active", WHITE)])
        st.configure("Glow.Horizontal.TProgressbar", troughcolor=CRUST, background=WHITE, bordercolor=SURFACE0,
                     lightcolor=WHITE, darkcolor=WHITE, thickness=S(6))
        for orient in ("Vertical", "Horizontal"):
            st.configure(f"{orient}.TScrollbar", background=SURFACE0, troughcolor=MANTLE, bordercolor=MANTLE,
                         arrowcolor=SUBTEXT, lightcolor=SURFACE0, darkcolor=SURFACE0, gripcount=0)
            st.map(f"{orient}.TScrollbar", background=[("active", SURFACE1)])
        st.configure("TSpinbox", fieldbackground=CARD, foreground=TEXT, background=CARD,
                     arrowcolor=TEXT, bordercolor=SURFACE0, lightcolor=CARD, darkcolor=CARD,
                     padding=S(4))
        st.configure("TCheckbutton", background=BASE, foreground=SUBTEXT, font=(UI, 9))
        st.map("TCheckbutton", background=[("active", BASE)], indicatorbackground=[("selected", WHITE)])

    # ------------------------------------------------------------------ layout
    def _build_ui(self):
        self._build_header()
        self._build_statusbar()
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        self.tab_cache = tk.Frame(self.nb, bg=BASE)
        self.tab_dups = tk.Frame(self.nb, bg=BASE)
        self.tab_large = tk.Frame(self.nb, bg=BASE)
        self.tab_console = tk.Frame(self.nb, bg=BASE)
        self.nb.add(self.tab_cache, text="⚙  System & Developer Caches")
        self.nb.add(self.tab_dups, text="⧉  Duplicate File Manager")
        self.nb.add(self.tab_large, text="◉  Large Files Radar")
        self.nb.add(self.tab_console, text="☰  Live Activity Console")
        self._build_cache_tab()
        self._build_dup_tab()
        self._build_large_tab()
        self._build_console_tab()

    def _build_header(self):
        S = self.S
        hdr = tk.Frame(self, bg=MANTLE)
        hdr.pack(fill="x", side="top")

        row1 = tk.Frame(hdr, bg=MANTLE)
        row1.pack(fill="x", padx=S(22), pady=(S(14), S(4)))
        tk.Label(row1, text="⚡", font=("Segoe UI Symbol", 24), fg=WHITE, bg=MANTLE).pack(side="left")
        tbox = tk.Frame(row1, bg=MANTLE)
        tbox.pack(side="left", padx=(S(8), 0))
        tk.Label(tbox, text="X-Cleaner", font=(UI_SEMI, 19), fg=TEXT, bg=MANTLE).pack(anchor="w")
        tk.Label(tbox, text="Complete C: Drive Storage & Duplicate Optimizer   ·   Enterprise Edition "
                            f"v{APP_VERSION}", font=(UI, 9), fg=SUBTEXT, bg=MANTLE).pack(anchor="w")
        right = tk.Frame(row1, bg=MANTLE)
        right.pack(side="right")
        admin = is_admin()
        tk.Label(right, text=" ADMIN " if admin else " USER ",
                 bg=WHITE if admin else CARD, fg=BLACK if admin else SUBTEXT, font=(UI_SEMI, 8), padx=S(8), pady=S(2)).pack(side="right")
        if not admin:
            ttk.Button(right, text="⛨  Restart as Administrator", command=self._relaunch_admin).pack(
                side="right", padx=(0, S(10)))

        row2 = tk.Frame(hdr, bg=MANTLE)
        row2.pack(fill="x", padx=S(22), pady=(S(8), S(4)))
        left = tk.Frame(row2, bg=MANTLE)
        left.pack(side="left", fill="x", expand=True)
        top = tk.Frame(left, bg=MANTLE)
        top.pack(fill="x")
        tk.Label(top, text=f"Local Disk ({SYSDRIVE})", font=(UI_SEMI, 11), fg=TEXT, bg=MANTLE).pack(side="left")
        self.drive_state = tk.Label(top, text="", font=(UI_SEMI, 9), fg=TEXT, bg=MANTLE)
        self.drive_state.pack(side="right")
        self.meter = tk.Canvas(left, height=S(24), bg=MANTLE, highlightthickness=0)
        self.meter.pack(fill="x", pady=(S(6), S(4)))
        self.meter.bind("<Configure>", lambda e: self._draw_meter())
        self.drive_legend = tk.Label(left, text="", font=(UI, 9), fg=SUBTEXT, bg=MANTLE, anchor="w")
        self.drive_legend.pack(fill="x")

        btns = tk.Frame(row2, bg=MANTLE)
        btns.pack(side="right", padx=(S(28), 0))
        self.hero = GradientButton(btns, "⚡  Deep Scan Entire Drive", self._start_deep_scan,
                                   width=S(290), height=S(52), font=(UI_SEMI, 12))
        self.hero.pack()
        self.stop_btn = ttk.Button(btns, text="■  Stop", style="Danger.TButton", command=self._stop)
        self.stop_btn.pack(fill="x", pady=(S(6), 0))
        self.stop_btn.state(["disabled"])

        row3 = tk.Frame(hdr, bg=MANTLE)
        row3.pack(fill="x", padx=S(22), pady=(S(8), S(4)))
        self.progress = ttk.Progressbar(row3, style="Glow.Horizontal.TProgressbar", maximum=100,
                                        mode="determinate")
        self.progress.pack(fill="x")
        info = tk.Frame(row3, bg=MANTLE)
        info.pack(fill="x", pady=(S(5), 0))
        self.status_lbl = tk.Label(info, text="Ready — run a Deep Scan to audit your drive.", font=(UI, 9),
                                   fg=TEXT, bg=MANTLE, anchor="w")
        self.status_lbl.pack(side="left", fill="x", expand=True)
        self.counter_lbl = tk.Label(info, text="", font=(self.mono, 9), fg=SUBTEXT, bg=MANTLE)
        self.counter_lbl.pack(side="right")

        cards = tk.Frame(hdr, bg=MANTLE)
        cards.pack(fill="x", padx=S(22), pady=(S(8), S(14)))
        self.cards = {}
        spec = [("cache", "Cache & Junk Found", WHITE), ("dups", "Duplicate Waste", WHITE),
                ("large", "Large Files (≥ threshold)", WHITE), ("freed", "Reclaimed Space", WHITE)]
        for i, (key, title, color) in enumerate(spec):
            c = tk.Frame(cards, bg=CARD, highlightthickness=1, highlightbackground=SURFACE0)
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else S(10), 0))
            cards.columnconfigure(i, weight=1, uniform="cards")
            tk.Frame(c, bg=WHITE, height=S(2)).pack(fill="x")
            tk.Label(c, text=title.upper(), fg=SUBTEXT, bg=CARD, font=(UI_SEMI, 8)).pack(
                anchor="w", padx=S(14), pady=(S(8), 0))
            v = tk.Label(c, text="—", fg=WHITE, bg=CARD, font=(UI_SEMI, 17))
            v.pack(anchor="w", padx=S(14))
            s = tk.Label(c, text="not scanned yet", fg=OVERLAY, bg=CARD, font=(UI, 8))
            s.pack(anchor="w", padx=S(14), pady=(0, S(9)))
            self.cards[key] = (v, s)

    def _build_statusbar(self):
        S = self.S
        bar = tk.Frame(self, bg=CRUST)
        bar.pack(fill="x", side="bottom")
        self.sb_left = tk.Label(bar, text="Ready", fg=SUBTEXT, bg=CRUST, font=(UI, 9), anchor="w")
        self.sb_left.pack(side="left", padx=S(14), pady=S(4))
        tk.Label(bar, text=f"Protected by internal system-folder blacklist  ·  v{APP_VERSION}", fg=OVERLAY,
                 bg=CRUST, font=(UI, 9)).pack(side="right", padx=S(14))

    def _toolbar(self, parent, pady=(0, 0)):
        f = tk.Frame(parent, bg=BASE)
        f.pack(fill="x", padx=self.S(18), pady=pady)
        return f

    def _btn(self, parent, text, cmd, style="TButton", side="left", busy=True):
        b = ttk.Button(parent, text=text, command=cmd, style=style)
        b.pack(side=side, padx=(0, self.S(8)) if side == "left" else (self.S(8), 0))
        if busy:
            self._busy_widgets.append(b)
        return b

    def _make_tree(self, parent, columns, show):
        wrap = tk.Frame(parent, bg=MANTLE, highlightthickness=1, highlightbackground=SURFACE0)
        tree = ttk.Treeview(wrap, columns=[c[0] for c in columns], show=show, selectmode="extended")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        for cid, title, width, anchor in columns:
            tree.heading(cid, text=title, anchor=anchor if anchor != "e" else "e")
            tree.column(cid, width=self.S(width), minwidth=self.S(50), anchor=anchor,
                        stretch=cid in ("desc", "path"))
        return wrap, tree

    def _hint(self, parent, text):
        tk.Label(parent, text=text, fg=SUBTEXT, bg=BASE, font=(UI, 9), anchor="w", justify="left").pack(
            side="left", fill="x", expand=True)

    # ------------------------------------------------------------- cache tab
    def _build_cache_tab(self):
        S, t = self.S, self.tab_cache
        top = self._toolbar(t, pady=(S(14), S(8)))
        self._hint(top, "Developer ecosystems, Windows system bloat, browser caches & temp files. "
                        "Click ☐ to select · double-click to open in Explorer · Space toggles selection.")
        self._btn(top, "↻  Rescan Caches", lambda: self._run_task("Cache & Junk Audit", self._task_scan_caches),
                  style="Accent.TButton", side="right")
        cols = [("category", "Category", 130, "w"), ("name", "Name", 300, "w"), ("size", "Size", 100, "e"),
                ("safety", "Safety Level", 110, "center"), ("path", "Path", 360, "w"),
                ("desc", "Description", 520, "w")]
        wrap, tree = self._make_tree(t, cols, "tree headings")
        tree.heading("#0", text="✔ Select", anchor="w")
        tree.column("#0", width=S(92), minwidth=S(80), stretch=False, anchor="w")
        wrap.pack(fill="both", expand=True, padx=S(18))
        tree.tag_configure("cat", background=CRUST, foreground=WHITE, font=(UI_SEMI, 10))
        tree.tag_configure("moderate", foreground=SUBTEXT)
        tree.tag_configure("review", foreground=OVERLAY)
        tree.tag_configure("dim", foreground=OVERLAY)
        tree.tag_configure("info", foreground=SUBTEXT)
        tree.bind("<Button-1>", self._on_cache_click)
        tree.bind("<Double-1>", lambda e: self._open_cache_selected())
        tree.bind("<space>", lambda e: self._toggle_cache_selection())
        self.cache_tree = tree

        bar = self._toolbar(t, pady=(S(10), S(14)))
        self._btn(bar, "★  Select Safe Defaults", self._cache_select_safe)
        self._btn(bar, "☑  Select All", lambda: self._cache_select_all(True))
        self._btn(bar, "☐  Deselect All", lambda: self._cache_select_all(False))
        self._btn(bar, "📂 Open in Explorer".replace("📂", "⧉"), self._open_cache_selected, busy=False)
        self.hib_btn = self._btn(bar, "☾  Hibernation: …", self._toggle_hibernation)
        self.clean_btn = self._btn(bar, "⚡  Clean Selected", self._clean_selected_caches, style="Danger.TButton",
                                   side="right")
        self.cache_sel_lbl = tk.Label(bar, text="", fg=SUBTEXT, bg=BASE, font=(UI_SEMI, 10))
        self.cache_sel_lbl.pack(side="right", padx=S(10))

    def _cache_row_values(self, it: CleanItem):
        if not it.scanned:
            size = "…"
        elif it.action == "command" and not it.size:
            size = "≈ 0 B"
        else:
            size = fmt_size(it.size)
        path = it.paths[0] if it.paths else ("docker engine" if it.action == "command" else "—")
        if len(it.paths) > 1:
            path += f"   (+{len(it.paths) - 1} more)"
        desc = it.desc
        if it.admin and not is_admin():
            desc = "⚠ Needs admin · " + desc
        return (it.category, it.name, size, SAFETY_LABEL.get(it.safety, it.safety), path, desc)

    def _cache_glyph(self, it: CleanItem):
        if not it.selectable:
            return f"  {CHECK_NA}"
        return f"  {CHECK_ON if it.selected else CHECK_OFF}"

    def _cache_tags(self, it: CleanItem):
        if not it.selectable:
            return ("info",)
        if it.scanned and it.size == 0 and it.action != "command":
            return ("dim",)
        return {"Moderate": ("moderate",), "Review": ("review",)}.get(it.safety, ())

    def _set_cache_items(self, items):
        old = {i.key: i.selected for i in self.cache_items}
        first = not self.cache_items
        for it in items:
            if it.key in old:
                it.selected = old[it.key] and it.size > 0
            elif first or True:
                it.selected = it.selectable and it.safety == "Safe" and it.size > 0
        self.cache_items = items
        self._render_cache_tree()

    def _render_cache_tree(self):
        tree = self.cache_tree
        tree.delete(*tree.get_children())
        self.cache_iids.clear()
        self.cat_iids.clear()
        for cat in CATEGORY_ORDER:
            members = [i for i in self.cache_items if i.category == cat]
            if not members:
                continue
            members.sort(key=lambda i: (not i.selectable, -i.size, i.name))
            pid = tree.insert("", "end", text="", open=True, tags=("cat",))
            self.cat_iids[pid] = cat
            for it in members:
                iid = tree.insert(pid, "end", text=self._cache_glyph(it), values=self._cache_row_values(it),
                                  tags=self._cache_tags(it))
                self.cache_iids[iid] = it
        self._refresh_cache_rows()

    def _refresh_cache_rows(self):
        tree = self.cache_tree
        for iid, it in self.cache_iids.items():
            tree.item(iid, text=self._cache_glyph(it), values=self._cache_row_values(it), tags=self._cache_tags(it))
        for pid, cat in self.cat_iids.items():
            members = [i for i in self.cache_items if i.category == cat]
            sel = [i for i in members if i.selectable]
            chosen = [i for i in sel if i.selected]
            glyph = CHECK_ON if sel and len(chosen) == len(sel) else (CHECK_PART if chosen else CHECK_OFF)
            total = sum(i.size for i in sel)
            tree.item(pid, text=f" {glyph}", values=(cat.upper(), f"{len(members)} locations",
                                                     fmt_size(total), "", "", ""))
        chosen = [i for i in self.cache_items if i.selected and i.selectable]
        self.cache_sel_lbl.configure(
            text=f"Selected: {len(chosen)} · {fmt_size(sum(i.size for i in chosen))}")
        self._update_cards()

    def _on_cache_click(self, event):
        tree = self.cache_tree
        if tree.identify_region(event.x, event.y) not in ("tree", "cell"):
            return None
        if tree.identify_column(event.x) != "#0":
            return None
        iid = tree.identify_row(event.y)
        if not iid or "indicator" in str(tree.identify_element(event.x, event.y)):
            return None
        self._toggle_cache_iid(iid)
        self._refresh_cache_rows()
        return "break"

    def _toggle_cache_iid(self, iid):
        if iid in self.cat_iids:
            cat = self.cat_iids[iid]
            sel = [i for i in self.cache_items if i.category == cat and i.selectable]
            target = not all(i.selected for i in sel)
            for i in sel:
                i.selected = target
        elif iid in self.cache_iids:
            it = self.cache_iids[iid]
            if it.selectable:
                it.selected = not it.selected
            else:
                self.sb_left.configure(text=f"'{it.name}' is report-only and cannot be cleaned directly.")

    def _toggle_cache_selection(self):
        for iid in self.cache_tree.selection():
            self._toggle_cache_iid(iid)
        self._refresh_cache_rows()
        return "break"

    def _cache_select_safe(self):
        for i in self.cache_items:
            i.selected = i.selectable and i.safety == "Safe" and i.size > 0
        self._refresh_cache_rows()

    def _cache_select_all(self, value: bool):
        for i in self.cache_items:
            i.selected = value and i.selectable
        self._refresh_cache_rows()

    def _open_cache_selected(self):
        for iid in self.cache_tree.selection():
            it = self.cache_iids.get(iid)
            if it and it.paths:
                open_in_explorer(it.paths[0])
                return

    def _clean_selected_caches(self):
        items = [i for i in self.cache_items if i.selected and i.selectable]
        if not items:
            messagebox.showinfo(APP_NAME, "Nothing selected. Use 'Select Safe Defaults' or tick items first.",
                                parent=self)
            return
        total = sum(i.size for i in items)
        lines = "\n".join(f"  • {i.name} — {fmt_size(i.size)}" for i in sorted(items, key=lambda i: -i.size)[:12])
        if len(items) > 12:
            lines += f"\n  … and {len(items) - 12} more"
        msg = f"Clean {len(items)} selected locations?\n\nEstimated reclaim: {fmt_size(total)}\n\n{lines}\n"
        review = [i for i in items if i.safety == "Review"]
        if review:
            msg += (f"\n⚠ {len(review)} REVIEW-level item(s) selected (e.g. {review[0].name}). These may contain "
                    f"data you want to keep.\n")
        if any(i.admin for i in items) and not is_admin():
            msg += "\nSome locations need Administrator rights; protected files will be skipped safely.\n"
        if any(i.action == "hibernate" for i in items):
            msg += "\nHibernation & Fast Startup will be disabled (UAC prompt).\n"
        if not messagebox.askyesno("Confirm Deep Clean", msg, icon="warning", parent=self):
            return
        self._run_task("Cleaning caches", self._task_clean_caches, items)

    # ----------------------------------------------------------- hibernation
    def _refresh_hibernation(self):
        on = hiberfil_size() is not None
        self.hib_btn.configure(text=f"☾  Hibernation: {'ON' if on else 'OFF'}")

    def _toggle_hibernation(self):
        size = hiberfil_size()
        on = size is not None
        if on:
            q = (f"Disable hibernation?\n\nThis runs 'powercfg -h off' (UAC prompt), deletes hiberfil.sys "
                 f"({fmt_size(size or 0)}) and turns off Fast Startup.")
        else:
            q = "Re-enable hibernation?\n\nThis runs 'powercfg -h on' (UAC prompt) and recreates hiberfil.sys."
        if messagebox.askyesno("Hibernation", q, parent=self):
            self._run_task("Hibernation toggle", self._task_hibernation, not on)

    def _task_hibernation(self, ctx, enable: bool):
        before = hiberfil_size() or 0
        ctx.stats.detail = "Waiting for UAC elevation…"
        code = set_hibernation(enable)
        if code is None:
            self.logger.log("Hibernation change cancelled (UAC declined).", "WARN")
        elif code != 0:
            self.logger.log(f"powercfg returned exit code {code}.", "WARN")
        else:
            time.sleep(1.0)
            after = hiberfil_size() or 0
            if enable:
                self.logger.log("Hibernation enabled.", "OK")
            else:
                self.logger.log(f"Hibernation disabled — reclaimed {fmt_size(max(0, before - after))}.", "OK")
                self.ui(self._add_freed, max(0, before - after), 0)
        self.ui(self._refresh_hibernation)
        self.ui(self._refresh_drive)

    # --------------------------------------------------------------- dup tab
    def _build_dup_tab(self):
        S, t = self.S, self.tab_dups
        top = self._toolbar(t, pady=(S(14), S(4)))
        tk.Label(top, text="Scan folders:", fg=TEXT, bg=BASE, font=(UI_SEMI, 10)).pack(side="left")
        self.dup_roots_lbl = tk.Label(top, text="", fg=SUBTEXT, bg=BASE, font=(UI, 9), anchor="w",
                                      justify="left", wraplength=S(700))
        self.dup_roots_lbl.pack(side="left", fill="x", expand=True, padx=(S(8), S(8)))
        self._btn(top, "⌕  Find Duplicates", self._start_dup_scan, style="Mauve.TButton", side="right")
        self._btn(top, "Reset Folders", self._dup_reset_roots, side="right")
        self._btn(top, "+  Add Folder", self._dup_add_root, side="right")

        opts = self._toolbar(t, pady=(S(4), S(8)))
        tk.Label(opts, text="Minimum file size (KB):", fg=SUBTEXT, bg=BASE, font=(UI, 9)).pack(side="left")
        self.dup_min = ttk.Spinbox(opts, from_=1, to=10_000_000, increment=64, width=9)
        self.dup_min.set("100")
        self.dup_min.pack(side="left", padx=(S(6), S(14)))
        tk.Label(opts, text="3-tier filter: size clustering → 4 KB head hash → full SHA-256 · hard links collapsed · "
                            "cloud-only files, .git, node_modules & venvs skipped",
                 fg=OVERLAY, bg=BASE, font=(UI, 9)).pack(side="left")

        cols = [("name", "File Name", 300, "w"), ("size", "Size", 100, "e"), ("modified", "Modified", 150, "center"),
                ("path", "Full Path", 700, "w")]
        wrap, tree = self._make_tree(t, cols, "tree headings")
        tree.heading("#0", text="✔ Select / Cluster", anchor="w")
        tree.column("#0", width=S(260), minwidth=S(120), stretch=False, anchor="w")
        wrap.pack(fill="both", expand=True, padx=S(18))
        tree.tag_configure("group", background=CRUST, foreground=WHITE, font=(UI_SEMI, 10))
        tree.tag_configure("marked", foreground=WHITE)
        tree.tag_configure("keep", foreground=OVERLAY)
        tree.bind("<Button-1>", self._on_dup_click)
        tree.bind("<Double-1>", lambda e: self._open_dup_selected())
        tree.bind("<space>", lambda e: self._toggle_dup_selection())
        self.dup_tree = tree

        bar = self._toolbar(t, pady=(S(10), S(14)))
        self._btn(bar, "Auto-Select Older Copies", lambda: self._dup_auto(keep_newest=True))
        self._btn(bar, "Auto-Select Newer Copies", lambda: self._dup_auto(keep_newest=False))
        self._btn(bar, "Clear Selection", self._dup_clear)
        self._btn(bar, "⧉ Open in Explorer", self._open_dup_selected, busy=False)
        self._btn(bar, "✖  Delete Permanently", lambda: self._dup_delete(recycle=False), style="Danger.TButton",
                  side="right")
        self._btn(bar, "♻  Move Selected to Recycle Bin", lambda: self._dup_delete(recycle=True),
                  style="Accent.TButton", side="right")
        self.dup_sum_lbl = tk.Label(bar, text="No scan yet", fg=SUBTEXT, bg=BASE, font=(UI_SEMI, 10))
        self.dup_sum_lbl.pack(side="right", padx=S(10))
        self._update_dup_roots_label()

    def _update_dup_roots_label(self):
        self.dup_roots_lbl.configure(text="  ·  ".join(self.dup_roots) if self.dup_roots else "(none)")

    def _dup_add_root(self):
        d = filedialog.askdirectory(parent=self, title="Add folder to duplicate scan")
        if d:
            d = os.path.abspath(d)
            if os.path.normcase(d) not in {os.path.normcase(r) for r in self.dup_roots}:
                self.dup_roots.append(d)
                self._update_dup_roots_label()

    def _dup_reset_roots(self):
        self.dup_roots = default_duplicate_roots()
        self._update_dup_roots_label()

    def _dup_min_bytes(self) -> int:
        try:
            return max(1, int(float(self.dup_min.get()))) * 1024
        except ValueError:
            return 100 * 1024

    def _start_dup_scan(self):
        self._run_task("Duplicate Engine", self._task_dups, list(self.dup_roots), self._dup_min_bytes())

    def _set_dups(self, groups):
        self.dup_groups = groups
        self.dup_marked = set()
        self._dup_auto(keep_newest=True, render=False)
        self._render_dups()

    def _dup_glyph(self, path):
        return f"  {CHECK_ON} delete" if path in self.dup_marked else f"  {CHECK_OFF} keep"

    def _render_dups(self):
        tree = self.dup_tree
        tree.delete(*tree.get_children())
        self.dup_iid_map.clear()
        shown = self.dup_groups[:MAX_DUP_GROUPS_SHOWN]
        for gi, g in enumerate(shown):
            gid = tree.insert("", "end", open=True, tags=("group",),
                              text=f" Cluster {gi + 1}  ·  {len(g.files)} copies",
                              values=(os.path.basename(g.files[0].path), fmt_size(g.size), "",
                                      f"Reclaimable: {fmt_size(g.waste)}   ·   SHA-256 {g.digest[:16]}…"))
            for fi, f in enumerate(g.files):
                iid = tree.insert(gid, "end", text=self._dup_glyph(f.path),
                                  values=(os.path.basename(f.path), fmt_size(f.size), fmt_time(f.mtime), f.path),
                                  tags=("marked",) if f.path in self.dup_marked else ("keep",))
                self.dup_iid_map[iid] = (gi, fi)
        if len(self.dup_groups) > MAX_DUP_GROUPS_SHOWN:
            self.logger.log(f"Showing the {MAX_DUP_GROUPS_SHOWN:,} largest clusters of {len(self.dup_groups):,}.",
                            "INFO")
        self._update_dup_summary()

    def _refresh_dup_rows(self):
        tree = self.dup_tree
        for iid, (gi, fi) in self.dup_iid_map.items():
            p = self.dup_groups[gi].files[fi].path
            tree.item(iid, text=self._dup_glyph(p), tags=("marked",) if p in self.dup_marked else ("keep",))
        self._update_dup_summary()

    def _update_dup_summary(self):
        waste = sum(g.waste for g in self.dup_groups)
        sel = 0
        for g in self.dup_groups:
            sel += sum(f.size for f in g.files if f.path in self.dup_marked)
        self.dup_sum_lbl.configure(
            text=f"{len(self.dup_groups):,} clusters · {fmt_size(waste)} reclaimable · "
                 f"Selected {len(self.dup_marked):,} ({fmt_size(sel)})")
        self._update_cards()

    def _dup_auto(self, keep_newest=True, render=True):
        self.dup_marked = set()
        for g in self.dup_groups:
            keeper = max(g.files, key=lambda f: f.mtime) if keep_newest else min(g.files, key=lambda f: f.mtime)
            for f in g.files:
                if f is not keeper:
                    self.dup_marked.add(f.path)
        if render:
            self._refresh_dup_rows()

    def _dup_clear(self):
        self.dup_marked = set()
        self._refresh_dup_rows()

    def _toggle_dup_iid(self, iid):
        if iid not in self.dup_iid_map:
            return
        gi, fi = self.dup_iid_map[iid]
        g = self.dup_groups[gi]
        p = g.files[fi].path
        if p in self.dup_marked:
            self.dup_marked.discard(p)
        else:
            if sum(1 for f in g.files if f.path not in self.dup_marked) <= 1:
                self.sb_left.configure(text="Safety: at least one copy of every cluster must be kept.")
                return
            self.dup_marked.add(p)

    def _on_dup_click(self, event):
        tree = self.dup_tree
        if tree.identify_region(event.x, event.y) not in ("tree", "cell") or tree.identify_column(event.x) != "#0":
            return None
        iid = tree.identify_row(event.y)
        if not iid or iid not in self.dup_iid_map or "indicator" in str(tree.identify_element(event.x, event.y)):
            return None
        self._toggle_dup_iid(iid)
        self._refresh_dup_rows()
        return "break"

    def _toggle_dup_selection(self):
        for iid in self.dup_tree.selection():
            self._toggle_dup_iid(iid)
        self._refresh_dup_rows()
        return "break"

    def _open_dup_selected(self):
        for iid in self.dup_tree.selection():
            if iid in self.dup_iid_map:
                gi, fi = self.dup_iid_map[iid]
                open_in_explorer(self.dup_groups[gi].files[fi].path)
                return

    def _dup_delete(self, recycle: bool):
        targets = []
        for g in self.dup_groups:
            marked = [f for f in g.files if f.path in self.dup_marked]
            if not marked:
                continue
            if len(marked) >= len(g.files):
                self.logger.log(f"Safety: skipped cluster with all copies selected ({g.files[0].path}).", "WARN")
                continue
            targets.extend(marked)
        if not targets:
            messagebox.showinfo(APP_NAME, "No duplicate copies selected.", parent=self)
            return
        total = sum(f.size for f in targets)
        verb = "Move to the Recycle Bin" if recycle else "PERMANENTLY DELETE"
        msg = (f"{verb} {len(targets):,} duplicate file(s) totalling {fmt_size(total)}?\n\n"
               f"At least one copy of every cluster is always kept.")
        if not recycle:
            msg += "\n\n⚠ Permanent deletion cannot be undone."
        if messagebox.askyesno("Confirm duplicate removal", msg, icon="warning", parent=self):
            self._run_task("Removing duplicates", self._task_delete_files, targets, recycle, self._after_dup_delete)

    def _after_dup_delete(self, deleted: set, freed: int, recycled: int):
        groups = []
        for g in self.dup_groups:
            g.files = [f for f in g.files if f.path not in deleted]
            if len(g.files) > 1:
                groups.append(g)
        self.dup_groups = groups
        self.dup_marked -= deleted
        self._render_dups()
        self._add_freed(freed, recycled)

    # ------------------------------------------------------------- large tab
    LARGE_COLS = [("name", "Name", 280, "w"), ("size", "Size", 100, "e"), ("ext", "Extension", 90, "center"),
                  ("modified", "Last Modified", 140, "center"), ("insight", "Insight", 260, "w"),
                  ("path", "Path", 620, "w")]

    def _build_large_tab(self):
        S, t = self.S, self.tab_large
        top = self._toolbar(t, pady=(S(14), S(8)))
        tk.Label(top, text="Threshold (MB):", fg=TEXT, bg=BASE, font=(UI_SEMI, 10)).pack(side="left")
        self.large_thr = ttk.Spinbox(top, from_=10, to=1_000_000, increment=100, width=8)
        self.large_thr.set("500")
        self.large_thr.pack(side="left", padx=(S(6), S(14)))
        self._hint(top, "Multi-threaded full-drive radar · click column headers to sort · right-click for actions")
        self._btn(top, "◉  Scan Drive for Large Files", self._start_large_scan, style="Accent.TButton", side="right")

        wrap, tree = self._make_tree(t, self.LARGE_COLS, "headings")
        wrap.pack(fill="both", expand=True, padx=S(18))
        for cid, title, _w, _a in self.LARGE_COLS:
            tree.heading(cid, command=lambda c=cid: self._sort_large(c))
        tree.tag_configure("huge", foreground=WHITE)
        tree.tag_configure("big", foreground=SUBTEXT)
        tree.tag_configure("prot", foreground=OVERLAY)
        tree.bind("<Double-1>", lambda e: self._large_open())
        tree.bind("<Button-3>", self._large_context)
        tree.bind("<Delete>", lambda e: self._large_delete(recycle=True))
        self.large_tree = tree

        self.large_menu = tk.Menu(self, tearoff=0, bg=SURFACE0, fg=TEXT, activebackground=BLUE,
                                  activeforeground=CRUST, bd=0, font=(UI, 10))
        self.large_menu.add_command(label="⧉  Open in File Explorer", command=self._large_open)
        self.large_menu.add_command(label="⎘  Copy Path", command=self._large_copy)
        self.large_menu.add_separator()
        self.large_menu.add_command(label="♻  Move to Recycle Bin", command=lambda: self._large_delete(True))
        self.large_menu.add_command(label="✖  Delete Permanently", command=lambda: self._large_delete(False))

        bar = self._toolbar(t, pady=(S(10), S(14)))
        self._btn(bar, "⧉ Open in Explorer", self._large_open, busy=False)
        self._btn(bar, "⎘ Copy Path", self._large_copy, busy=False)
        self._btn(bar, "✖  Delete Permanently", lambda: self._large_delete(False), style="Danger.TButton",
                  side="right")
        self._btn(bar, "♻  Move to Recycle Bin", lambda: self._large_delete(True), style="Accent.TButton",
                  side="right")
        self.large_sum_lbl = tk.Label(bar, text="No scan yet", fg=SUBTEXT, bg=BASE, font=(UI_SEMI, 10))
        self.large_sum_lbl.pack(side="right", padx=S(10))

    def _large_threshold(self) -> int:
        try:
            return max(1, int(float(self.large_thr.get()))) * 1024 * 1024
        except ValueError:
            return 500 * 1024 * 1024

    def _start_large_scan(self):
        self._run_task("Large File Radar", self._task_large, self._large_threshold())

    def _set_large(self, recs):
        self.large_files = recs
        self._render_large()

    def _render_large(self):
        key, desc = self.large_sort
        keyf = {"name": lambda r: os.path.basename(r.path).lower(), "size": lambda r: r.size,
                "ext": lambda r: r.ext, "modified": lambda r: r.mtime, "insight": lambda r: r.insight,
                "path": lambda r: r.path.lower()}[key]
        self.large_files.sort(key=keyf, reverse=desc)
        tree = self.large_tree
        tree.delete(*tree.get_children())
        self.large_iid_map.clear()
        for cid, title, _w, _a in self.LARGE_COLS:
            arrow = (" ▼" if desc else " ▲") if cid == key else ""
            tree.heading(cid, text=title + arrow)
        for r in self.large_files:
            tag = ("prot",) if r.protected else ("huge",) if r.size >= 5 * 1024 ** 3 else \
                ("big",) if r.size >= 2 * 1024 ** 3 else ()
            name = ("⛔ " if r.protected else "") + os.path.basename(r.path)
            iid = tree.insert("", "end", values=(name, fmt_size(r.size), r.ext, fmt_time(r.mtime), r.insight, r.path),
                              tags=tag)
            self.large_iid_map[iid] = r
        self.large_sum_lbl.configure(
            text=f"{len(self.large_files):,} files · {fmt_size(sum(r.size for r in self.large_files))}")
        self._update_cards()

    def _sort_large(self, col):
        key, desc = self.large_sort
        self.large_sort = (col, not desc if col == key else col in ("size", "modified"))
        self._render_large()

    def _large_selected(self):
        return [self.large_iid_map[i] for i in self.large_tree.selection() if i in self.large_iid_map]

    def _large_context(self, event):
        iid = self.large_tree.identify_row(event.y)
        if iid and iid not in self.large_tree.selection():
            self.large_tree.selection_set(iid)
        if iid:
            try:
                self.large_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.large_menu.grab_release()

    def _large_open(self):
        sel = self._large_selected()
        if sel:
            open_in_explorer(sel[0].path)

    def _large_copy(self):
        sel = self._large_selected()
        if sel:
            self.clipboard_clear()
            self.clipboard_append("\n".join(r.path for r in sel))
            self.sb_left.configure(text=f"Copied {len(sel)} path(s) to clipboard.")

    def _large_delete(self, recycle: bool):
        if self.busy:
            return
        sel = self._large_selected()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select one or more files first.", parent=self)
            return
        prot = [r for r in sel if r.protected]
        sel = [r for r in sel if not r.protected]
        if prot:
            self.logger.log(f"{len(prot)} protected system file(s) excluded from deletion.", "WARN")
        if not sel:
            messagebox.showwarning(APP_NAME, "The selected files are protected system files and cannot be deleted.",
                                   parent=self)
            return
        total = sum(r.size for r in sel)
        verb = "Move to the Recycle Bin" if recycle else "PERMANENTLY DELETE"
        names = "\n".join(f"  • {os.path.basename(r.path)} ({fmt_size(r.size)})" for r in sel[:10])
        msg = f"{verb} {len(sel)} file(s) totalling {fmt_size(total)}?\n\n{names}"
        if not recycle:
            msg += "\n\n⚠ Permanent deletion cannot be undone."
        if messagebox.askyesno("Confirm", msg, icon="warning", parent=self):
            recs = [FileRec(r.path, r.size, r.mtime) for r in sel]
            self._run_task("Removing large files", self._task_delete_files, recs, recycle, self._after_large_delete)

    def _after_large_delete(self, deleted: set, freed: int, recycled: int):
        self.large_files = [r for r in self.large_files if r.path not in deleted]
        self._render_large()
        self._add_freed(freed, recycled)

    # ----------------------------------------------------------- console tab
    def _build_console_tab(self):
        S, t = self.S, self.tab_console
        top = self._toolbar(t, pady=(S(14), S(8)))
        self._hint(top, "Real-time log of scanned files, permissions handled, cleaned bytes and reclaimed space.")
        ttk.Button(top, text="Open Log Folder", command=lambda: open_in_explorer(self.logger.dir)).pack(
            side="right", padx=(S(8), 0))
        ttk.Button(top, text="Save Log As…", command=self._save_console).pack(side="right", padx=(S(8), 0))
        ttk.Button(top, text="Clear", command=self._clear_console).pack(side="right", padx=(S(8), 0))
        self.autoscroll = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Auto-scroll", variable=self.autoscroll).pack(side="right", padx=S(8))

        wrap = tk.Frame(t, bg=CRUST, highlightthickness=1, highlightbackground=SURFACE0)
        wrap.pack(fill="both", expand=True, padx=S(18), pady=(0, S(14)))
        txt = tk.Text(wrap, bg=CRUST, fg=TEXT, insertbackground=TEXT, relief="flat", bd=0, wrap="none",
                      font=(self.mono, 9), padx=S(12), pady=S(10), state="disabled",
                      selectbackground=SURFACE1)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=txt.yview)
        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=txt.xview)
        txt.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        txt.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        txt.tag_configure("ts", foreground=OVERLAY)
        for lvl, color in (("INFO", SUBTEXT), ("OK", WHITE), ("WARN", SUBTEXT), ("ERROR", WHITE),
                           ("PERM", OVERLAY), ("SCAN", SUBTEXT), ("CLEAN", WHITE), ("DEBUG", OVERLAY)):
            txt.tag_configure(lvl, foreground=color, font=(self.mono, 9, "bold"))
            txt.tag_configure(lvl + "_m", foreground=WHITE if lvl in ("OK", "CLEAN") else SUBTEXT)
        self.console = txt

    def _append_console(self, lines):
        t = self.console
        t.configure(state="normal")
        for ts, lvl, msg in lines:
            t.insert("end", f"{ts}  ", ("ts",))
            t.insert("end", f"{lvl:<5}  ", (lvl,))
            t.insert("end", msg + "\n", (lvl + "_m",))
        count = int(t.index("end-1c").split(".")[0])
        if count > 8000:
            t.delete("1.0", f"{count - 6000}.0")
        t.configure(state="disabled")
        if self.autoscroll.get():
            t.see("end")

    def _clear_console(self):
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

    def _save_console(self):
        p = filedialog.asksaveasfilename(parent=self, defaultextension=".log", initialfile="deepclean_console.log",
                                         filetypes=[("Log files", "*.log"), ("Text files", "*.txt")])
        if p:
            try:
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(self.console.get("1.0", "end"))
                self.logger.log(f"Console saved to {p}", "OK")
            except OSError as ex:
                messagebox.showerror(APP_NAME, f"Could not save log:\n{ex}", parent=self)

    # ----------------------------------------------------------- drive meter
    def _refresh_drive(self):
        try:
            self.drive = shutil.disk_usage(DRIVE_ROOT)
        except OSError:
            return
        du = self.drive
        pct = du.used / du.total if du.total else 0
        self.drive_legend.configure(
            text=f"Used {fmt_size(du.used)}   ·   Free {fmt_size(du.free)}   ·   Total {fmt_size(du.total)}")
        if pct >= 0.9:
            self.drive_state.configure(text="CRITICAL · SPACE LOW", fg=WHITE)
        elif pct >= 0.75:
            self.drive_state.configure(text="WARNING · DRIVE FILLING", fg=SUBTEXT)
        else:
            self.drive_state.configure(text="OPTIMAL · DRIVE HEALTHY", fg=WHITE)
        self._draw_meter()

    def _auto_drive_refresh(self):
        self._refresh_drive()
        self.after(5000, self._auto_drive_refresh)

    def _draw_meter(self):
        c = self.meter
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 20 or not self.drive:
            return
        du = self.drive
        pct = du.used / du.total if du.total else 0
        r = h / 2
        # Clean monochrome trough with 1px border
        c.create_oval(0, 0, h, h, fill=CRUST, outline=SURFACE0)
        c.create_oval(w - h, 0, w, h, fill=CRUST, outline=SURFACE0)
        c.create_rectangle(r, 0, w - r, h, fill=CRUST, outline=SURFACE0)
        fw = max(h, int(w * pct))
        draw_pill_gradient(c, 0, 0, fw, h, WHITE, "#f0f0f0", r)
        label = f"{pct * 100:.1f}% used"
        if fw > self.S(120):
            c.create_text(self.S(12), h / 2, anchor="w", text=label, fill=BLACK, font=(UI_SEMI, 9))
        else:
            c.create_text(fw + self.S(10), h / 2, anchor="w", text=label, fill=WHITE, font=(UI_SEMI, 9))
        c.create_text(w - self.S(12), h / 2, anchor="e", text=f"{fmt_size(du.free)} free", fill=SUBTEXT,
                      font=(UI_SEMI, 9))

    # ----------------------------------------------------------------- cards
    def _update_cards(self):
        scanned = [i for i in self.cache_items if i.scanned and i.selectable]
        if scanned:
            v, s = self.cards["cache"]
            v.configure(text=fmt_size(sum(i.size for i in scanned)))
            safe = sum(i.size for i in scanned if i.safety == "Safe")
            s.configure(text=f"{fmt_size(safe)} rated Safe · {len(scanned)} locations")
        if self.dup_groups or self.dup_sum_lbl.cget("text") != "No scan yet":
            v, s = self.cards["dups"]
            v.configure(text=fmt_size(sum(g.waste for g in self.dup_groups)))
            s.configure(text=f"{len(self.dup_groups):,} clusters · {sum(len(g.files) - 1 for g in self.dup_groups):,}"
                             f" redundant copies")
        if self.large_files or self.large_sum_lbl.cget("text") != "No scan yet":
            v, s = self.cards["large"]
            v.configure(text=fmt_size(sum(r.size for r in self.large_files)))
            s.configure(text=f"{len(self.large_files):,} files ≥ {fmt_size(self._large_threshold())}")
        v, s = self.cards["freed"]
        v.configure(text=fmt_size(self.session_freed))
        s.configure(text=f"+ {fmt_size(self.session_recycled)} moved to Recycle Bin" if self.session_recycled
                    else "permanently reclaimed space")

    def _add_freed(self, freed: int, recycled: int):
        self.session_freed += freed
        self.session_recycled += recycled
        self._update_cards()
        self._refresh_drive()

    # ---------------------------------------------------------- task runner
    def _set_busy(self, busy: bool, name: str = ""):
        self.busy = busy
        for w in self._busy_widgets:
            try:
                w.state(["disabled"] if busy else ["!disabled"])
            except tk.TclError:
                pass
        self.hero.set_enabled(not busy)
        self.stop_btn.state(["!disabled"] if busy else ["disabled"])
        if busy:
            self.busy_name = name
            self.progress["value"] = 0
            self.sb_left.configure(text=f"Working: {name}…")
        else:
            elapsed = time.time() - self.stats.started
            self.progress["value"] = 0 if self.stop_event.is_set() else 100
            done = "■ Stopped" if self.stop_event.is_set() else "✔ Finished"
            self.status_lbl.configure(text=f"{done}: {self.busy_name} in {fmt_elapsed(elapsed)}")
            self.sb_left.configure(text="Ready")
            self._refresh_drive()

    def _run_task(self, name, target, *args, quiet=False):
        if self.busy:
            messagebox.showinfo(APP_NAME, f"Please wait — '{self.busy_name}' is still running.", parent=self)
            return
        self.stop_event.clear()
        self.stats.reset(name)
        ctx = OpContext(self.logger, self.stop_event, self.stats)
        self._set_busy(True, name)
        if not quiet:
            self.logger.log(f"▶ {name} started", "SCAN")

        def runner():
            com_init()
            try:
                target(ctx, *args)
            except Exception as ex:
                self.logger.log(f"{name} failed: {ex}\n{traceback.format_exc()}", "ERROR")
            finally:
                if not quiet or ctx.perm_errors + ctx.os_errors > 0:
                    ctx.summarize()
                if ctx.stopped:
                    self.logger.log(f"■ {name} stopped by user", "WARN")
                elif not quiet:
                    self.logger.log(f"✔ {name} finished in {fmt_elapsed(time.time() - self.stats.started)}", "OK")
                self.ui(self._set_busy, False)

        threading.Thread(target=runner, daemon=True, name=f"task:{name}").start()

    def _stop(self):
        if self.busy:
            self.stop_event.set()
            self.status_lbl.configure(text="Stopping… finishing current file safely")

    def _pump(self):
        try:
            for _ in range(300):
                fn, args = self.ui_q.get_nowait()
                try:
                    fn(*args)
                except Exception:
                    self.logger.log("UI update error: " + traceback.format_exc(), "ERROR")
        except queue.Empty:
            pass
        lines = []
        try:
            while len(lines) < 400:
                lines.append(self.logger.q.get_nowait())
        except queue.Empty:
            pass
        if lines:
            self._append_console(lines)
        if self.busy:
            st = self.stats
            self._spin = (self._spin + 1) % (len(SPINNER) * 3)
            self.progress["value"] = st.overall() * 100
            detail = st.detail if len(st.detail) < 110 else st.detail[:107] + "…"
            self.status_lbl.configure(
                text=f"{SPINNER[self._spin // 3]}  {st.phase}  ·  {st.overall() * 100:4.1f}%   {detail}")
            self.counter_lbl.configure(
                text=f"files {st.files:,}  ·  folders {st.dirs:,}  ·  indexed {fmt_size(st.bytes_seen)}  ·  "
                     f"skipped {st.errors:,}  ·  {fmt_elapsed(time.time() - st.started)}")
        self.after(80, self._pump)

    # --------------------------------------------------------- worker tasks
    def _task_scan_caches(self, ctx: OpContext, base=0.0, weight=1.0, quiet=False):
        st = ctx.stats
        st.set_phase("Cache & Junk Audit", base, weight)
        st.detail = "Discovering developer, system, browser and temp locations…"
        items = build_catalog()
        self.ui(self._set_cache_items, items)
        total = len(items)
        done = 0
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(measure_item, it, ctx): it for it in items}
            for fut in as_completed(futs):
                done += 1
                it = futs[fut]
                st.phase_frac = done / max(1, total)
                st.detail = f"Measured {it.name}"
                if done % 6 == 0:
                    self.ui(self._refresh_cache_rows)
        st.phase_frac = 1.0
        self.ui(self._set_cache_items, items)
        sel = [i for i in items if i.selectable]
        tot = sum(i.size for i in sel)
        safe = sum(i.size for i in sel if i.safety == "Safe")
        self.logger.log(f"Cache audit: {total} locations · {fmt_size(tot)} cleanable · {fmt_size(safe)} rated Safe",
                        "OK")
        for it in sorted(sel, key=lambda i: -i.size)[:8]:
            if it.size:
                self.logger.log(f"   {fmt_size(it.size):>10}  {it.category} › {it.name}", "INFO")

    def _task_large(self, ctx: OpContext, threshold: int, base=0.0, weight=1.0):
        ctx.stats.set_phase("Large File Radar", base, weight)
        recs = scan_large_files(ctx, threshold)
        if not ctx.stopped or recs:
            self.ui(self._set_large, recs)

    def _task_dups(self, ctx: OpContext, roots, min_size: int, base=0.0, weight=1.0):
        ctx.stats.set_phase("Duplicate Engine", base, weight)
        groups = find_duplicates(ctx, roots, min_size)
        if not ctx.stopped:
            self.ui(self._set_dups, groups)

    def _task_deep(self, ctx: OpContext, threshold: int, roots, min_size: int):
        t0 = time.time()
        self.logger.log("═" * 30 + "  DEEP SCAN  " + "═" * 30, "SCAN")
        self._task_scan_caches(ctx, 0.0, 0.22)
        if ctx.stopped:
            return
        self._task_large(ctx, threshold, 0.22, 0.43)
        if ctx.stopped:
            return
        self._task_dups(ctx, roots, min_size, 0.65, 0.35)
        if ctx.stopped:
            return
        self.ui(self._deep_summary, time.time() - t0)

    def _deep_summary(self, elapsed):
        cache = sum(i.size for i in self.cache_items if i.selectable)
        dups = sum(g.waste for g in self.dup_groups)
        large = sum(r.size for r in self.large_files if not r.protected)
        self.logger.log(f"Deep scan complete in {fmt_elapsed(elapsed)} — caches {fmt_size(cache)} · duplicates "
                        f"{fmt_size(dups)} · large files {fmt_size(large)}", "OK")
        self.nb.select(self.tab_cache)

    def _start_deep_scan(self):
        self._run_task("Deep Scan Entire Drive", self._task_deep, self._large_threshold(), list(self.dup_roots),
                       self._dup_min_bytes())

    def _task_clean_caches(self, ctx: OpContext, items):
        st = ctx.stats
        st.set_phase("Deep Clean", 0, 1)
        freed_total = 0
        before_free = shutil.disk_usage(DRIVE_ROOT).free
        for idx, it in enumerate(items):
            if ctx.stopped:
                break
            st.detail = it.name
            st.phase_frac = idx / max(1, len(items))
            self.logger.log(f"Cleaning › {it.category} › {it.name}", "CLEAN")
            try:
                freed = clean_item(it, ctx)
            except Exception as ex:
                self.logger.log(f"  {it.name} failed: {ex}", "ERROR")
                freed = 0
            freed_total += freed
            self.logger.log(f"  ✔ {it.name}: reclaimed {fmt_size(freed)}", "OK")
            measure_item(it, ctx)
            if it.size == 0:
                it.selected = False
            self.ui(self._refresh_cache_rows)
        st.phase_frac = 1.0
        after_free = shutil.disk_usage(DRIVE_ROOT).free
        self.logger.log(f"Deep clean complete — {fmt_size(freed_total)} reclaimed "
                        f"(drive free space change: {fmt_size(max(0, after_free - before_free))})", "OK")
        self.ui(self._add_freed, freed_total, 0)
        self.ui(self._refresh_hibernation)

    def _task_delete_files(self, ctx: OpContext, recs, recycle: bool, on_done):
        st = ctx.stats
        st.set_phase("Recycling files" if recycle else "Deleting files", 0, 1)
        deleted, freed, recycled = set(), 0, 0
        for i, rec in enumerate(recs):
            if ctx.stopped:
                break
            st.phase_frac = i / max(1, len(recs))
            st.detail = rec.path
            reason = GUARD.is_protected(rec.path)
            if reason:
                self.logger.log(f"Refused: {rec.path} is protected ({reason})", "WARN")
                continue
            try:
                size = os.stat(rec.path).st_size
                if recycle:
                    send_to_recycle_bin(rec.path)
                    recycled += size
                    self.logger.log(f"♻ Recycled {rec.path} ({fmt_size(size)})", "CLEAN")
                else:
                    _unlink(rec.path)
                    freed += size
                    self.logger.log(f"✖ Deleted {rec.path} ({fmt_size(size)})", "CLEAN")
                deleted.add(rec.path)
            except FileNotFoundError:
                deleted.add(rec.path)
                self.logger.log(f"Already gone: {rec.path}", "INFO")
            except OSError as ex:
                ctx.fs_error("Delete", rec.path, ex)
        st.phase_frac = 1.0
        if recycle and recycled:
            self.logger.log(f"{fmt_size(recycled)} moved to the Recycle Bin — space is returned once the bin is "
                            f"emptied.", "OK")
        if freed:
            self.logger.log(f"{fmt_size(freed)} permanently reclaimed.", "OK")
        self.ui(on_done, deleted, freed, recycled)

    # ----------------------------------------------------------- lifecycle
    def _relaunch_admin(self):
        if getattr(sys, "frozen", False):
            exe, params = sys.executable, ""
        else:
            exe, params = sys.executable, f'"{os.path.abspath(sys.argv[0])}"'
        r = _shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        if int(r or 0) > 32:
            self.stop_event.set()
            self.destroy()
        else:
            self.logger.log("Elevation cancelled.", "WARN")

    def _on_close(self):
        if self.busy and not messagebox.askyesno(APP_NAME, f"'{self.busy_name}' is running. Stop and exit?",
                                                 parent=self):
            return
        self.stop_event.set()
        self.destroy()


# =============================================================================
#  Entry point
# =============================================================================
def main():
    if IS_WINDOWS:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("XCleaner.Optimizer")
        except Exception:
            pass

    def _thread_hook(args):
        LOGGER.log(f"Thread error: {args.exc_value}\n"
                   + "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)), "ERROR")

    threading.excepthook = _thread_hook
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
