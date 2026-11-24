import asyncio
import atexit
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
import webbrowser

import websockets

IS_WINDOWS = os.name == "nt"
IS_MAC = sys.platform == "darwin"

BUNDLE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def _resolve_app_dir():
    """Directory that holds storage.json.

    Frozen (PyInstaller): next to the executable. On macOS the executable
    lives inside SpotifyUITweaker.app/Contents/MacOS/, so walk up to the
    .app's parent folder instead — that keeps storage.json OUTSIDE the
    bundle, where rebuilding the app won't wipe your saved settings.
    """
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        if exe_dir.endswith(os.path.join("Contents", "MacOS")):
            return os.path.dirname(os.path.dirname(os.path.dirname(exe_dir)))
        return exe_dir
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR = _resolve_app_dir()
STORAGE_PATH = os.path.join(APP_DIR, "storage.json")

# A launcher (or built .app) placed in /Applications or any other read-only
# spot cannot hold storage.json — fall back to the proper per-user location
# so saving a theme can never hard-crash the launcher.
if not os.access(APP_DIR, os.W_OK):
    _FALLBACK_DIR = os.path.join(
        os.path.expanduser("~"), "Library", "Application Support", "SpotifyUITweaker"
    )
    try:
        os.makedirs(_FALLBACK_DIR, exist_ok=True)
        if os.access(_FALLBACK_DIR, os.W_OK):
            STORAGE_PATH = os.path.join(_FALLBACK_DIR, "storage.json")
    except OSError:
        pass

SESSION_LOCK_PATH = os.path.join(os.path.dirname(STORAGE_PATH), "launcher-session.lock")

SPOTIFY_CANDIDATES = (
    [os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe")]
    if IS_WINDOWS
    else [
        "/Applications/Spotify.app/Contents/MacOS/Spotify",
        os.path.expanduser("~/Applications/Spotify.app/Contents/MacOS/Spotify"),
    ]
)

DEBUG_PORT = 9222
RELEASE_PAGE = "https://github.com/CoolDev111/SpotifyUITweaker/releases"

LAUNCHER_VERSION = "1.5.8"

LAUNCHER_AUMID = SPOTIFY_CANDIDATES[0] if IS_WINDOWS else "SpotifyUITweaker.Client"
_SHORTCUT_NAME = "SpotifyUITweaker.lnk"

if IS_WINDOWS:
    import ctypes
    import struct
    import threading

    _ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    _shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    _propsys = ctypes.WinDLL("propsys", use_last_error=True)
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    class _PROPERTYKEY(ctypes.Structure):
        _fields_ = [("fmtid", _GUID), ("pid", ctypes.c_ulong)]

    class _PROPVARIANT(ctypes.Structure):
        _fields_ = [
            ("vt", ctypes.c_ushort),
            ("reserved", ctypes.c_ubyte * 6),
            ("pwszVal", ctypes.c_void_p),
            ("pad", ctypes.c_ubyte * 8),
        ]

    _VT_LPWSTR = 31
    _COINIT_APARTMENTTHREADED = 0x2
    _RPC_E_CHANGED_MODE = -2147417850
    _CLSCTX_INPROC_SERVER = 0x1
    _GWL_EXSTYLE = -20
    _WS_EX_TOOLWINDOW = 0x00000080
    _PROC_QUERY_LIMITED_INFORMATION = 0x1000
    _SWP_NOSIZE = 0x0001
    _SWP_NOMOVE = 0x0002
    _SWP_NOZORDER = 0x0004
    _SWP_NOACTIVATE = 0x0010
    _SWP_SHOWWINDOW = 0x0040
    _SWP_HIDEWINDOW = 0x0080
    _SWP_TOGGLE = _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOZORDER | _SWP_NOACTIVATE

    _IID_IPropertyStore_STR = "{886D8EEB-8CF2-444E-8D5F-B48F88E7B7A5}"
    _IID_IShellLinkW_STR = "{000214F9-0000-0000-C000-000000000046}"
    _IID_IPersistFile_STR = "{0000010B-0000-0000-C000-000000000046}"
    _CLSID_ShellLink_STR = "{00021401-0000-0000-C000-000000000046}"
    _FOLDERID_Desktop_STR = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"

    _IID_IShellItem2_STR = "{7E9FB11D-B6DB-4412-83AC-A32778CB5136}"
    _CLSID_GIT_STR = "{00000323-0000-0000-C000-000000000046}"
    _IID_IUnknown_STR = "{00000000-0000-0000-C000-000000000046}"

    _WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)

    class _SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong), ("fMask", ctypes.c_ulong),
            ("hwnd", ctypes.c_void_p), ("lpVerb", ctypes.c_wchar_p),
            ("lpFile", ctypes.c_wchar_p), ("lpParameters", ctypes.c_wchar_p),
            ("lpDirectory", ctypes.c_wchar_p), ("nShow", ctypes.c_int),
            ("hInstApp", ctypes.c_void_p), ("lpIDList", ctypes.c_void_p),
            ("lpClass", ctypes.c_wchar_p), ("hkeyClass", ctypes.c_void_p),
            ("dwHotKey", ctypes.c_ulong), ("hIcon", ctypes.c_void_p),
            ("hProcess", ctypes.c_void_p),
        ]

    _GPS_READWRITE = 0x2
    _SEE_MASK_NOCLOSEPROCESS = 0x00000040
    _SEE_MASK_NOASYNC = 0x00001000

    _ole32.CLSIDFromString.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(_GUID)]
    _ole32.CLSIDFromString.restype = ctypes.HRESULT
    _ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    _ole32.CoInitializeEx.restype = ctypes.c_long
    _ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_GUID), ctypes.c_void_p, ctypes.c_ulong,
        ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p),
    ]
    _ole32.CoCreateInstance.restype = ctypes.HRESULT
    _ole32.PropVariantClear.argtypes = [ctypes.POINTER(_PROPVARIANT)]
    _ole32.PropVariantClear.restype = ctypes.HRESULT
    _ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    _shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
    _shell32.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.HRESULT
    _shell32.SHGetPropertyStoreForWindow.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p),
    ]
    _shell32.SHGetPropertyStoreForWindow.restype = ctypes.c_long
    _shell32.SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(_GUID), ctypes.c_ulong, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    _shell32.SHGetKnownFolderPath.restype = ctypes.HRESULT
    _user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    _user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _user32.GetWindowLongW.restype = ctypes.c_long
    _user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    _user32.EnumWindows.argtypes = [_WNDENUMPROC, ctypes.c_void_p]
    _user32.SetWindowPos.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint,
    ]
    _kernel32.OpenProcess.restype = ctypes.c_void_p
    _kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong),
    ]
    _kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    _user32.CreateWindowExW.argtypes = [
        ctypes.c_ulong, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_ulong,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
    ]
    _user32.CreateWindowExW.restype = ctypes.c_void_p
    _user32.DestroyWindow.argtypes = [ctypes.c_void_p]
    _shell32.SHCreateItemFromParsingName.argtypes = [
        ctypes.c_wchar_p, ctypes.c_void_p, ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _shell32.SHCreateItemFromParsingName.restype = ctypes.c_long
    _shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_SHELLEXECUTEINFOW)]
    _shell32.ShellExecuteExW.restype = ctypes.c_long

    def _tblog(msg):
        pass

    def _guid(string):
        g = _GUID()
        if _ole32.CLSIDFromString(ctypes.c_wchar_p(string), ctypes.byref(g)) != 0:
            raise OSError("CLSIDFromString failed: " + string)
        return g

    def _hr(hr):
        return f"0x{hr & 0xFFFFFFFF:08X}"

    def _vtbl(obj, slots):
        """Extract a COM object's vtable as an indexable array."""
        table_ptr = ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p)).contents.value
        return ctypes.cast(table_ptr, ctypes.POINTER(ctypes.c_void_p * slots)).contents

    def _com_release(obj):
        """IUnknown::Release via the vtable; safe on null pointers."""
        try:
            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(_vtbl(obj, 3)[2])(obj)
        except Exception:
            pass

    def _exc_hr(exc):
        """Compact '0x...... text' for an exception raised by a ctypes call."""
        hr = getattr(exc, "winerror", None)
        if isinstance(hr, int):
            return _hr(hr) + " " + str(exc).split("] ", 1)[-1]
        return repr(exc)

    _HR_NAMES = {
        0x80004002: "E_NOINTERFACE",
        0x80004005: "E_FAIL",
        0x80070005: "E_ACCESSDENIED",
        0x8007000E: "E_OUTOFMEMORY",
        0x80070057: "E_INVALIDARG",
        0x800401F0: "CO_E_NOTINITIALIZED",
        0x80040154: "REGDB_E_CLASSNOTREG",
        0x8002802B: "TYPE_E_ELEMENTNOTFOUND",
        0x8007139F: "ERROR_INVALID_INDEX",
        0x80070490: "ERROR_NOT_FOUND",
    }

    def _hr_name(hr):
        """HRESULT with its SDK nickname, e.g. '0x80004002 E_NOINTERFACE'."""
        base = hr & 0xFFFFFFFF
        nick = _HR_NAMES.get(base)
        return _hr(hr) + ((" " + nick) if nick else "")

    def _com_try_init():
        """CoInitializeEx (STA) for the CURRENT thread; never raises.

        Returns a short human-readable status string. S_FALSE (apartment
        already initialized) and RPC_E_CHANGED_MODE (MTA already active)
        both count as usable.
        """
        try:
            hr = _ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
        except Exception as exc:
            return "raised " + _exc_hr(exc)
        if hr == 0:
            return "ok (S_OK)"
        if hr == 1:
            return "ok (S_FALSE: apartment already initialized)"
        if hr == _RPC_E_CHANGED_MODE:
            return "ok (MTA apartment already active)"
        return "failed: " + _hr(hr)

    _COM_INITED_THREADS = set()

    def _com_ensure_thread():
        """CoInitializeEx once per thread; returns the status string or None
        when this thread was already initialized successfully."""
        ident = threading.get_ident()
        if ident in _COM_INITED_THREADS:
            return None
        status = _com_try_init()
        if status.startswith("ok"):
            _COM_INITED_THREADS.add(ident)
        return status

    def _com_probe():
        """Diagnostic line: which COM paths work in THIS process?

        globaliftable               - plain (non-shell) in-proc COM sanity
        shelllink+IUnknown          - object creation for the shortcut class
        shelllink+IShellLinkW       - the exact creation the shortcut path makes
        shelllinkQI+IPropertyStore  - the exact QueryInterface the identity
                                      stamp needs (raw HRESULT, never raised)
        """
        global _SHELLLINK_PS_OK
        parts = []

        def _try(label, clsid_str, iid_str):
            try:
                obj = ctypes.c_void_p()
                _ole32.CoCreateInstance(
                    ctypes.byref(_guid(clsid_str)), None, _CLSCTX_INPROC_SERVER,
                    ctypes.byref(_guid(iid_str)), ctypes.byref(obj),
                )
                _com_release(obj)
                parts.append(label + "=ok")
            except Exception as exc:
                parts.append(label + "=FAILED " + _exc_hr(exc))

        def _qi(label, clsid_str, iid_str):
            try:
                obj = ctypes.c_void_p()
                iid = _guid(iid_str)
                _ole32.CoCreateInstance(
                    ctypes.byref(_guid(clsid_str)), None, _CLSCTX_INPROC_SERVER,
                    ctypes.byref(iid), ctypes.byref(obj),
                )
                qi = ctypes.WINFUNCTYPE(
                    ctypes.c_long, ctypes.c_void_p,
                    ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p),
                )(_vtbl(obj, 3)[0])
                out = ctypes.c_void_p()
                hr = qi(obj, ctypes.byref(iid), ctypes.byref(out))
                parts.append(label + "=" + _hr_name(hr))
                if out:
                    _com_release(out)
                _com_release(obj)
                return hr == 0 and bool(out)
            except Exception as exc:
                parts.append(label + "=FAILED " + _exc_hr(exc))
                return False

        _try("globaliftable", _CLSID_GIT_STR, _IID_IUnknown_STR)
        _try("shelllink+IUnknown", _CLSID_ShellLink_STR, _IID_IUnknown_STR)
        _try("shelllink+IShellLinkW", _CLSID_ShellLink_STR, _IID_IShellLinkW_STR)
        _SHELLLINK_PS_OK = _qi("shelllinkQI+IPropertyStore", _CLSID_ShellLink_STR,
                               _IID_IPropertyStore_STR)
        _tblog("COM probe: " + "  ".join(parts))
    _tblog("python " + sys.version.split()[0]
           + f" ({'64' if sys.maxsize > 2 ** 32 else '32'}-bit)")
    _COM_MAIN_STATUS = _com_try_init()
    _tblog("COM apartment (main thread): " + _COM_MAIN_STATUS)
    if _COM_MAIN_STATUS.startswith("ok"):
        _COM_INITED_THREADS.add(threading.get_ident())
    _PKEY_AppUserModel_ID = None
    try:
        _PKEY_AppUserModel_ID = _PROPERTYKEY(
            _guid("{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}"), 5
        )
        _IID_IPROPERTYSTORE = _guid(_IID_IPropertyStore_STR)
        _IID_ISHELLLINKW = _guid(_IID_IShellLinkW_STR)
        _IID_IPERSISTFILE = _guid(_IID_IPersistFile_STR)
        _IID_ISHELLITEM2 = _guid(_IID_IShellItem2_STR)
        _CLSID_SHELLLINK = _guid(_CLSID_ShellLink_STR)
        _tblog("AppUserModelID system ready (PKEY 9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3, pid 5)")
        for _name, (_want, _obj) in {
            "IID_IPropertyStore": ("eb8e6d88f28c4e448d5fb48f88e7b7a5", _IID_IPROPERTYSTORE),
            "IID_IShellLinkW": ("f914020000000000c000000000000046", _IID_ISHELLLINKW),
            "IID_IPersistFile": ("0b01000000000000c000000000000046", _IID_IPERSISTFILE),
            "IID_IShellItem2": ("1db19f7edbb6124483aca32778cb5136", _IID_ISHELLITEM2),
            "PKEY_AppUserModel_ID.fmtid": (
                "55284c9f799f394ba8d0e1d42de1d5f3", _PKEY_AppUserModel_ID.fmtid),
        }.items():
            _have = ctypes.string_at(ctypes.byref(_obj), 16).hex()
            _tblog("guid check " + _name + ": " + _have
                   + (" OK" if _have == _want else " MISMATCH! expected " + _want))
        try:
            _propsys.PSGetPropertyKeyFromName.argtypes = [
                ctypes.c_wchar_p, ctypes.POINTER(_PROPERTYKEY),
            ]
            _propsys.PSGetPropertyKeyFromName.restype = ctypes.HRESULT
            chk = _PROPERTYKEY()
            hr = _propsys.PSGetPropertyKeyFromName("System.AppUserModel.ID", ctypes.byref(chk))
            if hr == 0:
                live = ctypes.string_at(ctypes.byref(chk.fmtid), 16).hex()
                mine = ctypes.string_at(ctypes.byref(_PKEY_AppUserModel_ID.fmtid), 16).hex()
                if live == mine:
                    _tblog("property system cross-check: key matches SDK header")
                else:
                    _PKEY_AppUserModel_ID = chk
                    _tblog("property system returned a different key than the SDK header; using the live one")
            else:
                _tblog("PSGetPropertyKeyFromName failed (hr=" + _hr(hr) + "); using SDK header key")
        except Exception as exc:
            _tblog(f"PSGetPropertyKeyFromName unavailable ({exc!r}); using SDK header key")
    except Exception as exc:
        _PKEY_AppUserModel_ID = None
        try:
            _tblog(f"AppUserModelID init failed: {exc!r}")
        except Exception:
            pass

    _AUMID_OK = _PKEY_AppUserModel_ID is not None
    _SHELLLINK_PS_OK = False
    _WINDOW_STORE_OK = False
    _ATOM_FALLBACK_ANNOUNCED = False

    def _set_process_aumid():
        """Claim LAUNCHER_AUMID for the launcher process itself.

        Only affects windows the launcher creates (normally none - this
        covers error dialogs). The Spotify merge is done by stamping windows.
        """
        try:
            _shell32.SetCurrentProcessExplicitAppUserModelID(LAUNCHER_AUMID)
            _tblog("process AUMID set to " + LAUNCHER_AUMID)
        except Exception as exc:
            _tblog("SetCurrentProcessExplicitAppUserModelID failed: " + _exc_hr(exc))

    def _window_is_spotify(hwnd):
        """True if the window belongs to a process named Spotify.exe."""
        pid = ctypes.c_ulong()
        _user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
        if not pid.value:
            return False
        proc = _kernel32.OpenProcess(_PROC_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not proc:
            return False
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = ctypes.c_ulong(1024)
            if not _kernel32.QueryFullProcessImageNameW(proc, 0, buf, ctypes.byref(size)):
                return False
            return buf.value.lower().endswith("\\spotify.exe")
        finally:
            _kernel32.CloseHandle(proc)

    def _spotify_taskbar_windows():
        """Visible, non-toolwindow top-level windows owned by Spotify.exe."""
        found = []

        def _cb(hwnd, _lparam):
            try:
                if hwnd and _user32.IsWindowVisible(hwnd):
                    if not (_user32.GetWindowLongW(hwnd, _GWL_EXSTYLE) & _WS_EX_TOOLWINDOW):
                        if _window_is_spotify(hwnd):
                            found.append(hwnd)
            except Exception:
                pass
            return 1

        _user32.EnumWindows(_WNDENUMPROC(_cb), None)
        return found

    _AUMID_ATOM = 0

    def _aumid_atom():
        """Global atom holding LAUNCHER_AUMID. Created once and never freed -
        Explorer dereferences this atom whenever it rebuilds the window's
        taskbar button, so deleting it would break grouping."""
        global _AUMID_ATOM
        if not _AUMID_ATOM:
            try:
                _kernel32.GlobalAddAtomW.argtypes = [ctypes.c_wchar_p]
                _kernel32.GlobalAddAtomW.restype = ctypes.c_ushort
                _AUMID_ATOM = int(_kernel32.GlobalAddAtomW(LAUNCHER_AUMID) or 0)
            except Exception:
                _AUMID_ATOM = 0
        return _AUMID_ATOM

    def _stamp_window_aumid_atom(hwnd):
        """SetPropW fallback for broken property systems.

        Explorer reads the raw window property 'AppUserModelID' (value =
        MAKEINTATOM of a global atom holding the ID string) when it groups
        taskbar buttons. Setting it from a foreign process is legal: window
        property names live in the global atom table and the atom HANDLE
        crosses the process boundary. No COM, no property system involved.
        Returns (ok, previous_id, error).
        """
        try:
            at = _aumid_atom()
            if not at:
                return False, "", "GlobalAddAtomW failed"
            _user32.GetPropW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
            _user32.GetPropW.restype = ctypes.c_void_p
            _user32.SetPropW.argtypes = [
                ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_void_p]
            _user32.SetPropW.restype = ctypes.c_int
            cur = _user32.GetPropW(ctypes.c_void_p(hwnd),
                                   ctypes.c_wchar_p("AppUserModelID"))
            if cur is not None and (int(cur) & 0xFFFF) == at:
                return True, LAUNCHER_AUMID, ""
            if not _user32.SetPropW(ctypes.c_void_p(hwnd),
                                    ctypes.c_wchar_p("AppUserModelID"),
                                    ctypes.c_void_p(at)):
                return False, "", ("SetPropW failed (lasterror="
                                   + str(ctypes.get_last_error()) + ")")
            return True, "", ""
        except Exception as exc:
            return False, "", f"exception: {_exc_hr(exc)}"

    def _stamp_window_aumid(hwnd):
        """Write LAUNCHER_AUMID into a window's property store.

        A window-level System.AppUserModel.ID overrides Spotify's own
        process-level ID, which is what lets the window regroup into our
        pinned shortcut. Returns (ok, previous_id, error).
        Falls back to the SetProp atom route when the property-store COM
        is broken on this machine (E_NOINTERFACE).
        """
        global _ATOM_FALLBACK_ANNOUNCED
        if not _AUMID_OK:
            return False, "", "property system unavailable"
        _com_ensure_thread()
        store = ctypes.c_void_p()
        try:
            hr = _shell32.SHGetPropertyStoreForWindow(
                ctypes.c_void_p(hwnd), ctypes.byref(_IID_IPROPERTYSTORE),
                ctypes.byref(store),
            )
        except Exception as exc:
            return False, "", f"SHGetPropertyStoreForWindow raised: {_exc_hr(exc)}"
        if hr != 0 or not store:
            detail = "SHGetPropertyStoreForWindow: " + _hr_name(hr)
            a_ok, a_prev, a_err = _stamp_window_aumid_atom(hwnd)
            if a_ok:
                if not _ATOM_FALLBACK_ANNOUNCED:
                    _ATOM_FALLBACK_ANNOUNCED = True
                    _tblog("property-store window stamping unavailable (" + detail
                           + "); SetProp atom fallback engaged")
                return True, a_prev, ""
            return False, "", detail + "; atom fallback: " + a_err

        prev = ""
        try:
            t = _vtbl(store, 8)
            _GetValue = ctypes.WINFUNCTYPE(
                ctypes.HRESULT, ctypes.c_void_p,
                ctypes.POINTER(_PROPERTYKEY), ctypes.POINTER(_PROPVARIANT),
            )(t[5])
            _SetValue = ctypes.WINFUNCTYPE(
                ctypes.HRESULT, ctypes.c_void_p,
                ctypes.POINTER(_PROPERTYKEY), ctypes.POINTER(_PROPVARIANT),
            )(t[6])
            _Commit = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p)(t[7])
            _Release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(t[2])
            prev = ""
            try:
                got = _PROPVARIANT()
                _GetValue(store, ctypes.byref(_PKEY_AppUserModel_ID), ctypes.byref(got))
                if got.vt == _VT_LPWSTR and got.pwszVal:
                    prev = ctypes.wstring_at(got.pwszVal)
                _ole32.PropVariantClear(ctypes.byref(got))
            except Exception:
                pass

            if prev == LAUNCHER_AUMID:
                return True, prev, ""

            pv = _PROPVARIANT()
            pv.vt = _VT_LPWSTR
            buf = ctypes.create_unicode_buffer(LAUNCHER_AUMID)
            pv.pwszVal = ctypes.cast(buf, ctypes.c_void_p)
            try:
                _SetValue(store, ctypes.byref(_PKEY_AppUserModel_ID), ctypes.byref(pv))
                _Commit(store)
            except Exception as exc:
                return False, prev, "SetValue/Commit: " + _exc_hr(exc)
            return True, prev, ""
        except Exception as exc:
            return False, prev, f"exception: {exc}"
        finally:
            try:
                _Release(store)
            except Exception:
                pass

    def _force_regroup(hwnd):
        """Briefly hide/show the window so the taskbar rebuilds its button
        under the new AUMID (no activation, no z-order change, no flicker)."""
        try:
            _user32.SetWindowPos(ctypes.c_void_p(hwnd), None, 0, 0, 0, 0,
                                 _SWP_TOGGLE | _SWP_HIDEWINDOW)
            _user32.SetWindowPos(ctypes.c_void_p(hwnd), None, 0, 0, 0, 0,
                                 _SWP_TOGGLE | _SWP_SHOWWINDOW)
        except Exception:
            pass

    def _known_desktop_dir():
        """Real (possibly OneDrive-redirected) Desktop folder path."""
        try:
            g = _guid(_FOLDERID_Desktop_STR)
            out = ctypes.c_wchar_p()
            hr = _shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(out))
            if hr == 0 and out.value:
                path = out.value
                _ole32.CoTaskMemFree(out)
                return path
        except Exception:
            pass
        fallback = os.path.expandvars(r"%USERPROFILE%\Desktop")
        return fallback if os.path.isdir(fallback) else None

    def _stamp_store(ps, aumid, steps, tag):
        """Write System.AppUserModel.ID into an acquired IPropertyStore.
        Returns True when SetValue+Commit both returned S_OK."""
        try:
            pt = _vtbl(ps, 8)
            _SetValue = ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p,
                ctypes.POINTER(_PROPERTYKEY), ctypes.POINTER(_PROPVARIANT),
            )(pt[6])
            _Commit = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(pt[7])
            pv = _PROPVARIANT()
            pv.vt = _VT_LPWSTR
            buf = ctypes.create_unicode_buffer(aumid)
            pv.pwszVal = ctypes.cast(buf, ctypes.c_void_p)
            hr = _SetValue(ps, ctypes.byref(_PKEY_AppUserModel_ID), ctypes.byref(pv))
            steps.append(tag + ".SetValue=" + _hr_name(hr))
            if hr != 0:
                return False
            hr = _Commit(ps)
            steps.append(tag + ".Commit=" + _hr_name(hr))
            return hr == 0
        except Exception as exc:
            steps.append(tag + ".exception: " + _exc_hr(exc))
            return False

    def _read_store_aumid(ps, steps, tag):
        """Read System.AppUserModel.ID back out of a property store."""
        val = ""
        try:
            pt = _vtbl(ps, 8)
            _GetValue = ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p,
                ctypes.POINTER(_PROPERTYKEY), ctypes.POINTER(_PROPVARIANT),
            )(pt[5])
            got = _PROPVARIANT()
            hr = _GetValue(ps, ctypes.byref(_PKEY_AppUserModel_ID), ctypes.byref(got))
            if hr == 0 and got.vt == _VT_LPWSTR and got.pwszVal:
                val = ctypes.wstring_at(got.pwszVal)
            try:
                _ole32.PropVariantClear(ctypes.byref(got))
            except Exception:
                pass
            steps.append(tag + ".GetValue=" + _hr_name(hr)
                         + ("" if hr != 0 else " -> " + (val or "<missing>")))
        except Exception as exc:
            steps.append(tag + ".exception: " + _exc_hr(exc))
        return val

    def _stamp_store_shellitem2(path, aumid, steps):
        """Independent stamp route: IShellItem2::GetPropertyStore(GPS_READWRITE)
        on the ALREADY-SAVED .lnk file. Shares nothing with the ShellLink-QI
        route except the property key itself, so it works even when ShellLink
        refuses its own property store."""
        item = ctypes.c_void_p()
        ps = ctypes.c_void_p()
        try:
            hr = _shell32.SHCreateItemFromParsingName(
                ctypes.c_wchar_p(path), None,
                ctypes.byref(_IID_ISHELLITEM2), ctypes.byref(item),
            )
            steps.append("item2.create=" + _hr_name(hr))
            if hr != 0 or not item:
                return False
            it = _vtbl(item, 9)
            _GetPS = ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p, ctypes.c_ulong,
                ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p),
            )(it[8])
            hr = _GetPS(item, _GPS_READWRITE,
                        ctypes.byref(_IID_IPROPERTYSTORE), ctypes.byref(ps))
            steps.append("item2.GetPropertyStore=" + _hr_name(hr))
            if hr != 0 or not ps:
                return False
            return _stamp_store(ps, aumid, steps, "item2")
        except Exception as exc:
            steps.append("item2.exception: " + _exc_hr(exc))
            return False
        finally:
            _com_release(ps)
            _com_release(item)

    _AUMID_FMTID_HEX = "55284c9f799f394ba8d0e1d42de1d5f3"

    def _fmtid_bytes():
        """PKEY_AppUserModel_ID.fmtid as the 16 in-memory (little-endian GUID
        layout) bytes that live inside a serialized property store."""
        if _PKEY_AppUserModel_ID is not None:
            try:
                return ctypes.string_at(ctypes.byref(_PKEY_AppUserModel_ID.fmtid), 16)
            except Exception:
                pass
        return bytes.fromhex(_AUMID_FMTID_HEX)

    def _lnk_walk_layout(data):
        """Byte offset of a .lnk's ExtraData region, or None when the file
        does not parse cleanly. Only reads size fields - never content."""
        if len(data) < 0x4C:
            return None
        hdr_size, = struct.unpack_from("<I", data, 0)
        if hdr_size < 0x4C or hdr_size >= len(data):
            return None
        flags, = struct.unpack_from("<I", data, 20)
        off = hdr_size
        if flags & 0x01:
            if off + 2 > len(data):
                return None
            n, = struct.unpack_from("<H", data, off)
            off += 2 + n
        if flags & 0x02:
            if off + 4 > len(data):
                return None
            n, = struct.unpack_from("<I", data, off)
            off += n if n >= 4 else 4
        for bit in (0x04, 0x08, 0x10, 0x20, 0x40):
            if not (flags & bit):
                continue
            if off + 2 > len(data):
                return None
            cch, = struct.unpack_from("<H", data, off)
            off += 2 + cch * (2 if flags & 0x80 else 1)
        return off if off <= len(data) else None

    def _lnk_property_store_block(aumid):
        """PropertyStoreDataBlock bytes: one Serialized Property Storage
        (MS-PROPSTORE 2.2, Version 0x53505331, FormatID of the
        System.AppUserModel.* property set) holding one Serialized Property
        Value (Integer Name, MS-PROPSTORE 2.3.2: pid 5, VT_LPWSTR), each
        terminated by a zero-size sentinel rather than a count field."""
        wide = aumid.encode("utf-16-le") + b"\x00\x00"
        wide += b"\x00" * ((-len(wide)) % 4)
        value = struct.pack("<I", len(aumid) + 1) + wide
        typed = struct.pack("<HH", 31, 0) + value
        prop_rest = struct.pack("<I", 5) + b"\x00" + typed
        prop_value = struct.pack("<I", 4 + len(prop_rest)) + prop_rest
        store_body = _fmtid_bytes() + prop_value + struct.pack("<I", 0)
        store = struct.pack("<I", 8 + len(store_body)) + struct.pack("<I", 0x53505331) + store_body
        body = store + struct.pack("<I", 0)
        return struct.pack("<II", 8 + len(body), 0xA0000009) + body

    def _decode_property_store(payload):
        """Pull the AUMID string back out of a PropertyStoreDataBlock body
        (everything after size+signature). Returns "" when not found."""
        want = _fmtid_bytes()
        p = 0
        while p + 4 <= len(payload):
            storage_size, = struct.unpack_from("<I", payload, p)
            if storage_size == 0:
                break
            if storage_size < 24 or p + storage_size > len(payload):
                return ""
            version, = struct.unpack_from("<I", payload, p + 4)
            if version != 0x53505331:
                return ""
            fmtid = bytes(payload[p + 8:p + 24])
            vp, end = p + 24, p + storage_size
            while vp + 4 <= end:
                value_size, = struct.unpack_from("<I", payload, vp)
                if value_size == 0:
                    break
                if value_size < 13 or vp + value_size > end:
                    return ""
                pid, = struct.unpack_from("<I", payload, vp + 4)
                vt, = struct.unpack_from("<H", payload, vp + 9)
                if fmtid == want and pid == 5 and vt == 31:
                    cch, = struct.unpack_from("<I", payload, vp + 13)
                    chars = payload[vp + 17:vp + 17 + 2 * cch]
                    return chars.decode("utf-16-le", "replace").rstrip("\x00")
                vp += value_size
            p += storage_size
        return ""

    def _lnk_read_aumid_binary(data):
        """AUMID carried by raw .lnk bytes. None = no PropertyStoreDataBlock,
        "" = block present but no recognizable identity property."""
        off = _lnk_walk_layout(data)
        if off is None:
            return None
        while off + 4 <= len(data):
            size, = struct.unpack_from("<I", data, off)
            if size == 0:
                break
            if size < 8 or off + size > len(data):
                return None
            sig, = struct.unpack_from("<I", data, off + 4)
            if sig == 0xA0000009:
                try:
                    return _decode_property_store(data[off + 8:off + size])
                except Exception:
                    return ""
            off += size
        return None

    def _stamp_lnk_binary(path, aumid):
        """Splice the identity stamp straight into the saved .lnk bytes.

        No COM, no property system, no shell involvement - this is the
        fallback that works when the machine's property-store COM is broken.
        The result is verified by parsing the new bytes back BEFORE the file
        is replaced (temp file + os.replace, so a crash cannot corrupt the
        shortcut). Returns (ok, detail)."""
        try:
            with open(path, "rb") as fh:
                data = bytearray(fh.read())
            off = _lnk_walk_layout(bytes(data))
            if off is None:
                return False, "layout not recognized"
            blocks = []
            p = off
            while p + 4 <= len(data):
                size, = struct.unpack_from("<I", data, p)
                if size == 0:
                    break
                if size < 8 or p + size > len(data):
                    return False, "truncated extra-data block"
                sig, = struct.unpack_from("<I", data, p + 4)
                if sig != 0xA0000009:
                    blocks.append(bytes(data[p:p + size]))
                p += size
            if p + 4 > len(data) or any(data[p:p + 4]):
                return False, "terminal block missing (layout walk failed)"
            new = bytearray(data[:off])
            new += b"".join(blocks)
            new += _lnk_property_store_block(aumid)
            new += b"\x00\x00\x00\x00"
            got = _lnk_read_aumid_binary(bytes(new))
            if got != aumid:
                return False, "read-back mismatch (" + repr(got) + ")"
            tmp = path + ".spt-tmp"
            with open(tmp, "wb") as fh:
                fh.write(bytes(new))
            os.replace(tmp, path)
            return True, ("stamped (" + str(len(new)) + " bytes), read-back verified")
        except Exception as exc:
            return False, _exc_hr(exc)

    def _verify_lnk_inproc(path, expected):
        """Reload a saved .lnk in a FRESH ShellLink object and read its
        AppUserModelID back. Returns (ok, readback_value_or_reason, steps)."""
        steps = []
        link = ctypes.c_void_p()
        pf = ctypes.c_void_p()
        ps = ctypes.c_void_p()
        try:
            _ole32.CoCreateInstance(
                ctypes.byref(_CLSID_SHELLLINK), None, _CLSCTX_INPROC_SERVER,
                ctypes.byref(_IID_ISHELLLINKW), ctypes.byref(link),
            )
            lt = _vtbl(link, 21)
            _QueryInterface = ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p,
                ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p),
            )(lt[0])
            hr = _QueryInterface(link, ctypes.byref(_IID_IPERSISTFILE), ctypes.byref(pf))
            steps.append("verify.QI(IPersistFile)=" + _hr_name(hr))
            if hr != 0 or not pf:
                return False, "QI(IPersistFile) failed", steps
            ft = _vtbl(pf, 9)
            _Load = ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_ulong,
            )(ft[5])
            hr = _Load(pf, ctypes.c_wchar_p(path), 0)
            steps.append("verify.Load=" + _hr_name(hr))
            if hr != 0:
                return False, "Load failed", steps
            hr = _QueryInterface(link, ctypes.byref(_IID_IPROPERTYSTORE), ctypes.byref(ps))
            steps.append("verify.QI(IPropertyStore)=" + _hr_name(hr))
            if hr != 0 or not ps:
                return False, "QI(IPropertyStore) failed", steps
            got = _read_store_aumid(ps, steps, "verify")
            return (got == expected), (got or "<missing>"), steps
        except Exception as exc:
            steps.append("verify.exception: " + _exc_hr(exc))
            return False, _exc_hr(exc), steps
        finally:
            _com_release(ps)
            _com_release(pf)
            _com_release(link)

    def _write_lnk_inproc(spec):
        """Create ONE .lnk in-process, in the order the shell actually needs:

        set fields -> SAVE -> acquire IPropertyStore -> stamp -> SAVE again
        -> verify by reloading.

        The first Save matters: QueryInterface for IPropertyStore on a
        never-saved ShellLink answers E_NOINTERFACE on some systems, which is
        exactly what earlier builds hit. If the ShellLink QI still refuses,
        the IShellItem2 route on the saved file is tried next. Every step
        logs its own HRESULT.

        spec: {path, target, arguments, workdir, icon, aumid}
        Returns {saved, stamped, verified, steps}.
        """
        steps = []
        res = {"saved": False, "stamped": False, "verified": False, "steps": steps}
        link = ctypes.c_void_p()
        pf = ctypes.c_void_p()
        ps = ctypes.c_void_p()
        try:
            _ole32.CoCreateInstance(
                ctypes.byref(_CLSID_SHELLLINK), None, _CLSCTX_INPROC_SERVER,
                ctypes.byref(_IID_ISHELLLINKW), ctypes.byref(link),
            )
            lt = _vtbl(link, 21)
            _QueryInterface = ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p,
                ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p),
            )(lt[0])
            _SetPath = ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p, ctypes.c_wchar_p)(lt[20])
            _SetArguments = ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p, ctypes.c_wchar_p)(lt[11])
            _SetWorkingDirectory = ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p, ctypes.c_wchar_p)(lt[9])
            _SetIconLocation = ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)(lt[17])

            hr = _SetPath(link, spec["target"])
            steps.append("SetPath=" + _hr_name(hr))
            if spec.get("arguments"):
                hr = _SetArguments(link, spec["arguments"])
                steps.append("SetArguments=" + _hr_name(hr))
            if spec.get("workdir"):
                hr = _SetWorkingDirectory(link, spec["workdir"])
                steps.append("SetWorkDir=" + _hr_name(hr))
            hr = _SetIconLocation(link, spec.get("icon") or spec["target"], 0)
            steps.append("SetIcon=" + _hr_name(hr))

            hr = _QueryInterface(link, ctypes.byref(_IID_IPERSISTFILE), ctypes.byref(pf))
            steps.append("QI(IPersistFile)=" + _hr_name(hr))
            if hr != 0 or not pf:
                return res
            ft = _vtbl(pf, 9)
            _Save = ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)(ft[6])
            hr = _Save(pf, ctypes.c_wchar_p(spec["path"]), 1)
            steps.append("save#1=" + _hr_name(hr))
            if hr != 0:
                return res
            res["saved"] = True
            hr = _QueryInterface(link, ctypes.byref(_IID_IPROPERTYSTORE), ctypes.byref(ps))
            steps.append("QI(IPropertyStore)@saved-object=" + _hr_name(hr))
            if hr == 0 and ps:
                res["stamped"] = _stamp_store(ps, spec["aumid"], steps, "stamp")
            if not res["stamped"]:
                _com_release(ps)
                ps = ctypes.c_void_p()
                res["stamped"] = _stamp_store_shellitem2(spec["path"], spec["aumid"], steps)
            if res["stamped"]:
                hr = _Save(pf, ctypes.c_wchar_p(spec["path"]), 1)
                steps.append("save#2=" + _hr_name(hr))
                ok, val, vsteps = _verify_lnk_inproc(spec["path"], spec["aumid"])
                steps.extend(vsteps)
                res["verified"] = ok
            return res
        except Exception as exc:
            steps.append("exception: " + _exc_hr(exc))
            return res
        finally:
            _com_release(ps)
            _com_release(pf)
            _com_release(link)

    def _taskbar_selftest():
        """Rehearse the whole shortcut flow in %TEMP% before touching the real
        Desktop/Start-menu locations, so one log line names the exact breaking
        step on this machine."""
        path = os.path.join(tempfile.gettempdir(), "spt-taskbar-selftest.lnk")
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
        spec = {
            "path": path,
            "target": sys.executable,
            "arguments": "",
            "workdir": os.path.dirname(sys.executable),
            "icon": sys.executable,
            "aumid": LAUNCHER_AUMID,
        }
        r = _write_lnk_inproc(spec)
        _tblog("selftest: " + "  ".join(r["steps"]))
        if r["saved"] and not r["verified"]:
            b_ok, b_detail = _stamp_lnk_binary(path, LAUNCHER_AUMID)
            _tblog("selftest binary stamp: "
                   + ("OK - " + b_detail if b_ok else "FAILED - " + b_detail))
            r["verified"] = b_ok
        _tblog("selftest result: saved=" + str(r["saved"])
               + " stamped=" + str(r["stamped"]) + " verified=" + str(r["verified"]))
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
        return r["verified"]

    def _probe_window_store():
        """SHGetPropertyStoreForWindow on OUR OWN hidden window (in-proc).

        Comparing this against the watchdog's cross-process attempts tells a
        broken property store apart from Windows refusing foreign windows.
        """
        global _WINDOW_STORE_OK
        try:
            hwnd = _user32.CreateWindowExW(
                0, ctypes.c_wchar_p("STATIC"), None, 0,
                0, 0, 0, 0, None, None, None, None,
            )
            if not hwnd:
                _tblog("window-store probe: could not create probe window")
                return
            store = ctypes.c_void_p()
            hr = _shell32.SHGetPropertyStoreForWindow(
                ctypes.c_void_p(hwnd), ctypes.byref(_IID_IPROPERTYSTORE),
                ctypes.byref(store),
            )
            _tblog("window-store probe (own window): " + _hr_name(hr)
                   + (" + store acquired" if hr == 0 and store else ""))
            _WINDOW_STORE_OK = (hr == 0 and bool(store))
            if store:
                _com_release(store)
            _user32.DestroyWindow(ctypes.c_void_p(hwnd))
        except Exception as exc:
            _tblog("window-store probe failed: " + _exc_hr(exc))

    def _create_taskbar_shortcuts():
        """Create/refresh the pin-ready launcher shortcut.

        Points at the launcher (the .exe when frozen, pythonw + main.py when
        running from source), shows Spotify's icon and carries LAUNCHER_AUMID
        so the pinned item and the stamped Spotify windows match.

        Returns (desktop_lnk_path or None, newly_created).
        """
        if not _AUMID_OK:
            return None, False

        if getattr(sys, "frozen", False):
            target = sys.executable
            arguments = ""
        else:
            target = sys.executable
            pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if os.path.exists(pythonw):
                target = pythonw
            arguments = f'"{os.path.abspath(__file__)}"'

        workdir = os.path.dirname(sys.executable if not getattr(sys, "frozen", False) else target)
        icon_path = find_spotify() or target

        desktop_dir = _known_desktop_dir()
        start_menu = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")

        targets = []
        if desktop_dir and os.path.isdir(desktop_dir):
            targets.append(os.path.join(desktop_dir, _SHORTCUT_NAME))
        if os.path.isdir(start_menu):
            targets.append(os.path.join(start_menu, _SHORTCUT_NAME))
        if not targets:
            _tblog("no Desktop/Start-menu folder found; shortcut not created")
            return None, False

        desktop_lnk = targets[0]
        newly_created = not os.path.exists(desktop_lnk)

        _com_ensure_thread()
        _com_probe()
        if not _SHELLLINK_PS_OK and not _WINDOW_STORE_OK:
            _tblog("verdict: this machine's property-store COM answers "
                   "E_NOINTERFACE on every route (ShellLink QI and "
                   "SHGetPropertyStoreForWindow both failed); COM-free "
                   "fallbacks engaged (binary .lnk stamp + SetProp atom)")

        specs = [
            {"path": t, "target": target, "arguments": arguments,
             "workdir": workdir, "icon": icon_path, "aumid": LAUNCHER_AUMID}
            for t in targets
        ]

        saved = []
        verified = {}
        for spec in specs:
            r = _write_lnk_inproc(spec)
            _tblog("lnk " + spec["path"] + ": " + "  ".join(r["steps"]))
            if r["saved"]:
                saved.append(spec["path"])
            verified[spec["path"]] = r["saved"] and r["verified"]

        verified_all = bool(saved) and all(verified.get(p, False) for p in saved)

        if saved and not verified_all:
            _tblog("in-proc stamp incomplete; trying the COM-free binary stamp")
            for spec in specs:
                if verified.get(spec["path"]) or not os.path.exists(spec["path"]):
                    continue
                b_ok, b_detail = _stamp_lnk_binary(spec["path"], LAUNCHER_AUMID)
                _tblog("binary stamp " + spec["path"] + ": "
                       + ("OK - " + b_detail if b_ok else "FAILED - " + b_detail))
                verified[spec["path"]] = b_ok
            verified_all = bool(saved) and all(verified.get(p, False) for p in saved)

        if not verified_all and specs:
            _tblog("binary stamp insufficient; retrying out-of-proc via PowerShell")
            ps_saved, ps_ok = _stamp_links_via_powershell(specs, LAUNCHER_AUMID)
            if ps_ok:
                saved = list(ps_saved)
                verified_all = True
            else:
                for p in ps_saved:
                    if p not in saved:
                        saved.append(p)
                    if not os.path.exists(p):
                        continue
                    b_ok, b_detail = _stamp_lnk_binary(p, LAUNCHER_AUMID)
                    _tblog("binary stamp (post-PowerShell) " + p + ": "
                           + ("OK - " + b_detail if b_ok else "FAILED - " + b_detail))
                    verified[p] = b_ok
                verified_all = bool(saved) and all(verified.get(p, False) for p in saved)

        if saved:
            _tblog("shortcut written: " + ", ".join(saved)
                   + (" (identity VERIFIED)" if verified_all
                      else " (WARNING: identity stamp FAILED - pinning it will not merge Spotify)"))
            _tblog("pin THIS shortcut, not the .exe (unpin any older pin first)")
        else:
            _tblog("shortcut could not be created (in-proc COM, binary stamp and PowerShell all failed)")
        return (desktop_lnk if desktop_lnk in saved else None), newly_created

    _LNK_CSHARP = r"""
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;

namespace SpotifyUiTweaker
{
    [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
    public class ShellLinkClass {}

    [ComImport, Guid("000214F9-0000-0000-C000-000000000046"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IShellLinkW
    {
        void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszFile, int cch, IntPtr pfd, uint fFlags);
        void GetIDList(out IntPtr ppidl);
        void SetIDList(IntPtr pidl);
        void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszName, int cch);
        void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string pszName);
        void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszDir, int cch);
        void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string pszDir);
        void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszArgs, int cch);
        void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string pszArgs);
        void GetHotkey(out short pwHotkey);
        void SetHotkey(short pwHotkey);
        void GetShowCmd(out int piShowCmd);
        void SetShowCmd(int piShowCmd);
        void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszIconPath, int cch, out int piIcon);
        void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string pszIconPath, int iIcon);
        void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string pszPathRel, uint dwReserved);
        void Resolve(IntPtr hwnd, uint fFlags);
        void SetPath([MarshalAs(UnmanagedType.LPWStr)] string pszFile);
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct PROPERTYKEY
    {
        public Guid fmtid;
        public uint pid;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct PROPVARIANT
    {
        public ushort vt;
        public ushort wReserved1;
        public ushort wReserved2;
        public ushort wReserved3;
        public IntPtr unionMember;   // VT_LPWSTR: pointer to the string
        public IntPtr pad1;          // full PROPVARIANT is 24 bytes on x64
        public IntPtr pad2;
    }

    [ComImport, Guid("886D8EEB-8CF2-444E-8D5F-B48F88E7B7A5"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IPropertyStore
    {
        void GetCount(out uint cProps);
        void GetAt(uint iProp, out PROPERTYKEY pkey);
        void GetValue(ref PROPERTYKEY key, out PROPVARIANT pv);
        void SetValue(ref PROPERTYKEY key, ref PROPVARIANT pv);
        void Commit();
    }

    [ComImport, Guid("0000010B-0000-0000-C000-000000000046"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IPersistFile
    {
        new void GetClassID(out Guid pClassID);
        void IsDirty();
        void Load([MarshalAs(UnmanagedType.LPWStr)] string pszFileName, uint dwMode);
        void Save([MarshalAs(UnmanagedType.LPWStr)] string pszFileName, [MarshalAs(UnmanagedType.Bool)] bool fRemember);
        void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string pszFileName);
        void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string ppszFileName);
    }

    public static class LnkTools
    {
        public static string Create(string path, string target, string args,
                                    string workdir, string icon, string aumid)
        {
            object link = null;
            try
            {
                link = new ShellLinkClass();
                IShellLinkW sl = (IShellLinkW)link;
                sl.SetPath(target);
                if (!string.IsNullOrEmpty(args)) sl.SetArguments(args);
                if (!string.IsNullOrEmpty(workdir)) sl.SetWorkingDirectory(workdir);
                if (!string.IsNullOrEmpty(icon)) sl.SetIconLocation(icon, 0);

                IPersistFile pf = (IPersistFile)link;
                // Save FIRST: QueryInterface for IPropertyStore on a
                // never-saved ShellLink answers E_NOINTERFACE on some
                // systems. Save -> stamp -> save again.
                pf.Save(path, true);

                string stampError = null;
                try
                {
                    IPropertyStore ps = (IPropertyStore)link;
                    PROPERTYKEY key = new PROPERTYKEY();
                    key.fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");
                    key.pid = 5;
                    PROPVARIANT pv = new PROPVARIANT();
                    pv.vt = 31; // VT_LPWSTR
                    IntPtr mem = Marshal.StringToCoTaskMemUni(aumid);
                    pv.unionMember = mem;
                    try
                    {
                        ps.SetValue(ref key, ref pv);
                        ps.Commit();
                    }
                    finally
                    {
                        Marshal.FreeCoTaskMem(mem);
                    }
                    pf.Save(path, true); // land the stamp in the file
                }
                catch (Exception ex)
                {
                    stampError = ex.Message;
                }

                return stampError == null ? "OK" : ("STAMP_FAILED: " + stampError);
            }
            catch (Exception ex)
            {
                return "ERROR: " + ex.Message;
            }
            finally
            {
                if (link != null)
                {
                    try { Marshal.ReleaseComObject(link); } catch (Exception) {}
                }
            }
        }

        public static string Verify(string path)
        {
            object link = null;
            try
            {
                link = new ShellLinkClass();
                IPersistFile pf = (IPersistFile)link;
                pf.Load(path, 0);
                IPropertyStore ps = (IPropertyStore)link;
                PROPERTYKEY key = new PROPERTYKEY();
                key.fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");
                key.pid = 5;
                PROPVARIANT pv;
                ps.GetValue(ref key, out pv);
                if (pv.vt == 31 && pv.unionMember != IntPtr.Zero)
                {
                    return Marshal.PtrToStringUni(pv.unionMember) ?? "";
                }
                return "";
            }
            catch (Exception)
            {
                return "";
            }
            finally
            {
                if (link != null)
                {
                    try { Marshal.ReleaseComObject(link); } catch (Exception) {}
                }
            }
        }
    }
}
"""

    _PS_LNK_SCRIPT = r"""
 $ErrorActionPreference = 'Continue'
 $spec = $null
try {
  $spec = Get-Content -LiteralPath '__PAYLOAD__' -Raw | ConvertFrom-Json
} catch {
  Write-Output ('SPTFATAL payload: ' + $_.Exception.Message)
  exit 4
}
if (-not $spec) { Write-Output 'SPTFATAL payload missing'; exit 4 }
try {
  Add-Type -TypeDefinition @'
__CS__
'@
} catch {
  Write-Output ('SPTFATAL Add-Type: ' + $_.Exception.Message)
  exit 5
}
foreach ($lnk in $spec.links) {
  $r = ''
  try {
    $r = [SpotifyUiTweaker.LnkTools]::Create($lnk.path, $lnk.target, $lnk.arguments, $lnk.workdir, $lnk.icon, $spec.aumid)
  } catch {
    $r = 'ERROR: ' + $_.Exception.Message
  }
  if ($r -eq 'OK') {
    Write-Output ('SPTOK ' + $lnk.path)
  } elseif ($r.StartsWith('STAMP_FAILED')) {
    Write-Output ('SPTSAVED ' + $lnk.path + ' :: ' + $r)
  } else {
    Write-Output ('SPTFAIL ' + $lnk.path + ' :: ' + $r)
  }
}
foreach ($lnk in $spec.links) {
  $v = ''
  try {
    $v = [SpotifyUiTweaker.LnkTools]::Verify($lnk.path)
  } catch {
    $v = ''
  }
  if (-not $v) { $v = 'NONE' }
  Write-Output ('SPTVER ' + $lnk.path + ' :: ' + $v)
}
"""

    def _stamp_links_via_powershell(specs, aumid):
        """Build + stamp + VERIFY the .lnk files in a separate powershell.exe
        process.

        The helper has its own COM apartment, immune to whatever misbehaves
        inside this process. Returns (saved_paths, all_verified_ok).
        """
        payload = {"aumid": aumid, "links": specs}
        fd, payload_path = tempfile.mkstemp(prefix="spt-taskbar-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            script = (_PS_LNK_SCRIPT
                      .replace("__CS__", _LNK_CSHARP.strip())
                      .replace("__PAYLOAD__", payload_path.replace("'", "''")))
            try:
                proc = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                     "Bypass", "-Command", script],
                    timeout=180,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    **_quiet(stdout=subprocess.PIPE),
                )
            except Exception as exc:
                _tblog(f"PowerShell fallback could not run ({exc})")
                return [], False
            saved, verified = [], {}
            for line in (proc.stdout or "").splitlines():
                line = line.strip()
                if line.startswith("SPTOK "):
                    saved.append(line[6:].strip())
                elif line.startswith("SPTSAVED "):
                    path, _, reason = line[9:].partition(" :: ")
                    _tblog(f"PowerShell wrote {path} but its identity stamp failed: {reason}")
                elif line.startswith(("SPTFAIL", "SPTFATAL")):
                    _tblog("PowerShell fallback: " + line)
                elif line.startswith("SPTVER "):
                    path, _, value = line[7:].partition(" :: ")
                    verified[path.strip()] = (value.strip() == aumid)
            for p in saved:
                if not verified.get(p, False):
                    _tblog(f"PowerShell wrote {p} but read-back verification FAILED")
            return saved, bool(saved) and all(verified.get(p, False) for p in saved)
        finally:
            try:
                os.unlink(payload_path)
            except Exception:
                pass

    def _taskbar_pin_present(name=_SHORTCUT_NAME):
        try:
            return os.path.exists(os.path.join(
                os.path.expandvars(
                    r"%APPDATA%\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar"),
                name))
        except Exception:
            return False

    def _prompt_pin_once(lnk_path):
        """Pinning is blocked at the OS level for unpackaged shortcuts, so this
        only ever offers a one-click way to get there manually - and only
        until the user has pinned it, or storage.json records they declined."""
        if _taskbar_pin_present():
            return
        try:
            with open(STORAGE_PATH, "r", encoding="utf-8") as fh:
                state = json.load(fh)
        except Exception:
            state = {}
        if state.get("taskbarPinPrompted"):
            return
        try:
            subprocess.Popen(["explorer", "/select,", lnk_path], **_quiet())
        except Exception:
            pass
        state["taskbarPinPrompted"] = True
        try:
            with open(STORAGE_PATH, "w", encoding="utf-8") as fh:
                json.dump(state, fh)
        except Exception:
            pass
        print("[MSC] Right-click the selected shortcut and choose 'Pin to taskbar' "
              "if you'd like it there. This only shows once.")

    def _ensure_taskbar_identity():
        """Runs once on the main thread, before Spotify is launched."""
        if not _AUMID_OK:
            return
        _set_process_aumid()
        _taskbar_selftest()
        _probe_window_store()
        lnk, _created = _create_taskbar_shortcuts()
        if lnk:
            _prompt_pin_once(lnk)

    _SPOTIFY_LNK_DIR = os.path.join(os.path.expandvars(r"%LOCALAPPDATA%"), "SpotifyUITweaker")
    _SPOTIFY_LNK_PATH = os.path.join(_SPOTIFY_LNK_DIR, "Spotify (Tweaker).lnk")

    def _shellexec(path):
        """ShellExecuteEx - launches THROUGH the shell so the launched process
        gets associated with the .lnk it came from; that association is what
        makes a stamped shortcut's AppUserModelID propagate to the windows of
        apps that do not claim an explicit AUMID. Returns (ok, detail)."""
        sei = _SHELLEXECUTEINFOW()
        sei.cbSize = ctypes.sizeof(_SHELLEXECUTEINFOW)
        sei.fMask = _SEE_MASK_NOCLOSEPROCESS | _SEE_MASK_NOASYNC
        sei.lpFile = path
        sei.nShow = 1
        try:
            ok = bool(_shell32.ShellExecuteExW(ctypes.byref(sei)))
        except Exception as exc:
            return False, _exc_hr(exc)
        if sei.hProcess:
            _kernel32.CloseHandle(sei.hProcess)
        return ok, ("lasterror=" + str(ctypes.get_last_error()) if not ok else "ok")

    def _launch_spotify_stamped(spotify_exe, args):
        """Launch Spotify through a stamped .lnk so its windows inherit
        LAUNCHER_AUMID (applies whenever Spotify does not claim an explicit
        AUMID itself). Returns True when the shell accepted the launch."""
        try:
            os.makedirs(_SPOTIFY_LNK_DIR, exist_ok=True)
        except Exception:
            pass
        spec = {"path": _SPOTIFY_LNK_PATH, "target": spotify_exe,
                "arguments": args, "workdir": os.path.dirname(spotify_exe),
                "icon": spotify_exe, "aumid": LAUNCHER_AUMID}
        r = _write_lnk_inproc(spec)
        stamped = r["saved"] and r["verified"]
        if not stamped:
            _tblog("stamped Spotify .lnk in-proc: " + "  ".join(r["steps"]))
            if r["saved"]:
                b_ok, b_detail = _stamp_lnk_binary(_SPOTIFY_LNK_PATH, LAUNCHER_AUMID)
                _tblog("stamped Spotify .lnk binary stamp: "
                       + ("OK - " + b_detail if b_ok else "FAILED - " + b_detail))
                stamped = b_ok
        if not stamped:
            ps_saved, ps_ok = _stamp_links_via_powershell([spec], LAUNCHER_AUMID)
            if ps_ok:
                stamped = True
            elif ps_saved:
                b_ok, b_detail = _stamp_lnk_binary(_SPOTIFY_LNK_PATH, LAUNCHER_AUMID)
                _tblog("stamped Spotify .lnk binary stamp (post-PowerShell): "
                       + ("OK - " + b_detail if b_ok else "FAILED - " + b_detail))
                stamped = b_ok
        if not stamped:
            _tblog("stamped Spotify .lnk unavailable; falling back to a direct spawn")
            return False
        ok, detail = _shellexec(_SPOTIFY_LNK_PATH)
        _tblog("Spotify launched via stamped shortcut: " + ("yes" if ok else "no")
               + " (" + detail + ")")
        return ok

    def _start_taskbar_stamp_watchdog():
        """Keeps Spotify's windows stamped with the launcher AUMID.

        Fast polling right after launch (to catch the window before/as its
        taskbar button appears), then a lazy 1.5s cadence that also covers
        Spotify self-restarts and window recreation. Re-stamping a window
        that already carries our ID is a no-op, so the loop self-heals.
        """
        def _worker():
            status = _com_ensure_thread()
            if status:
                _tblog("stamper thread COM: " + status)
            last_err = ""
            fast_until = time.time() + 20.0
            while True:
                try:
                    for hwnd in _spotify_taskbar_windows():
                        ok, prev, err = _stamp_window_aumid(hwnd)
                        if not ok:
                            if err != last_err:
                                _tblog(f"could not stamp Spotify window 0x{hwnd:X}: {err}")
                                last_err = err
                            continue
                        last_err = ""
                        if prev != LAUNCHER_AUMID:
                            _force_regroup(hwnd)
                            _tblog(f"Spotify window 0x{hwnd:X} now grouped into the pinned launcher button")
                    time.sleep(0.25 if time.time() < fast_until else 1.5)
                except Exception as exc:
                    _tblog(f"watchdog error: {exc}")
                    time.sleep(2.0)

        threading.Thread(target=_worker, name="spt-taskbar-stamp", daemon=True).start()


def find_spotify():
    for path in SPOTIFY_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def _quiet(**extra):
    """Common subprocess kwargs; also hides console windows on Windows."""
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if IS_WINDOWS:
        kwargs["creationflags"] = 0x08000000
    kwargs.update(extra)
    return kwargs


def kill_spotify():
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/F", "/IM", "Spotify.exe"], **_quiet())
    elif IS_MAC:
        subprocess.run(["killall", "Spotify"], **_quiet())
    else:
        subprocess.run(["pkill", "-x", "Spotify"], **_quiet())


# ---------------------------------------------------------------------------
# Session ownership — the fix for "loading a theme again nukes Spotify"
# ---------------------------------------------------------------------------
# Chromium allows ONE debugger client per Spotify page target. When a second
# launcher attaches, the first one's socket is closed; when Spotify reloads
# its page or dies, the socket closes too. The old build answered EVERY such
# exit with kill_spotify() (atexit + finally), which murdered Spotify out
# from under a newer launcher and turned any hiccup into a full crash that
# took Spotify AND the launcher down together.
#
# The lock file records who owns the session so exit-time cleanup can tell
# "I was replaced by a newer run" (stand down, touch nothing) apart from
# "I am quitting for real" (close Spotify, as designed).

def _read_lock_pid():
    try:
        with open(SESSION_LOCK_PATH, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid):
    if not pid or pid <= 0:
        return False
    try:
        if IS_WINDOWS:
            import ctypes as _ctypes
            _k32 = _ctypes.WinDLL("kernel32", use_last_error=True)
            handle = _k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return False
            try:
                exit_code = _ctypes.c_ulong()
                if _k32.GetExitCodeProcess(handle, _ctypes.byref(exit_code)):
                    return exit_code.value == 259  # STILL_ACTIVE
                return False
            finally:
                _k32.CloseHandle(handle)
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but owned by another user
    except OSError:
        return False


def claim_session_lock():
    """Atomically take session ownership. Returns the previous owner's PID."""
    previous = _read_lock_pid()
    tmp_path = f"{SESSION_LOCK_PATH}.{os.getpid()}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        os.replace(tmp_path, SESSION_LOCK_PATH)
    except OSError:
        previous = None  # unwritable dir; degrade to best-effort single instance
    return previous


def owns_session():
    return _read_lock_pid() == os.getpid()


_session_started = False  # True once this run has spawned or attached to Spotify


def _shutdown_kill_spotify():
    """Keeps the designed "quitting the launcher closes Spotify" behaviour,
    but ONLY while this run still owns the session. A launcher that was
    replaced by a newer run (or that hit an unexpected error after losing
    ownership) exits without touching Spotify."""
    if _session_started and owns_session():
        kill_spotify()


atexit.register(_shutdown_kill_spotify)
signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))


# ---------------------------------------------------------------------------
# macOS GPU-safety CSS sanitizer
# ---------------------------------------------------------------------------
# Spotify's macOS client composites through Metal/ANGLE, and the glass
# themes' heavy backdrop-filter blur + background-attachment: fixed combo
# is a known GPU-process killer on that path: the client exits the instant
# the theme style is applied. Windows renders the exact same CSS fine, so
# the rewrite only engages when the launcher itself runs on macOS.
_MAC_BLUR_CAP_PX = 8


def _sanitize_css_for_macos(css):
    """Neutralize GPU-crash-prone declarations for the macOS Metal path."""
    if not css:
        return css
    # 1) backdrop-filter (incl. -webkit- variant): force off. Keeping
    #    !important strength so Spotify's own glass rules cannot re-enable
    #    it later. Also disables any @supports conditions using it.
    css = re.sub(
        r"(?i)(-webkit-backdrop-filter|backdrop-filter)\s*:[^;}]*",
        lambda m: f"{m.group(1)}: none !important",
        css,
    )
    # 2) Cap remaining blur() radii (plain filter: blur and custom
    #    properties) so large surfaces cannot allocate exploding textures.
    css = re.sub(
        r"(?i)blur\(\s*([0-9]+(?:\.[0-9]+)?)px\s*\)",
        lambda m: f"blur({min(float(m.group(1)), _MAC_BLUR_CAP_PX):g}px)",
        css,
    )
    # 3) Fixed backgrounds force full-surface re-composites while scrolling.
    css = re.sub(
        r"(?i)background-attachment\s*:\s*fixed(\s*!important)?",
        lambda m: "background-attachment: scroll" + (m.group(1) or ""),
        css,
    )
    return css


def collect_extension_bundle():
    """Reads all extension HTML, CSS, JS, and theme files into a dictionary."""
    files = {}
    for root, _, filenames in os.walk(BUNDLE_DIR):
        for fname in filenames:
            if fname.endswith((".css", ".js", ".html", ".json")) and fname not in ("main.py", "storage.json"):
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, BUNDLE_DIR).replace("\\", "/")
                with open(full_path, "r", encoding="utf-8") as f:
                    text = f.read()
                if fname.endswith(".css") and IS_MAC:
                    text = _sanitize_css_for_macos(text)
                files[rel_path] = text

    storage = {}
    if os.path.exists(STORAGE_PATH):
        try:
            with open(STORAGE_PATH, "r", encoding="utf-8") as f:
                storage = json.load(f)
        except Exception:
            storage = {}

    return {"files": files, "storage": storage}


def extract_popup_parts(html_text):
    styles = re.findall(r"<style[^>]*>([\s\S]*?)</style>", html_text, re.IGNORECASE)
    combined_css = "\n".join(styles)

    combined_css = re.sub(
        r'(^|[\s,}])(?::root|html|body)(?=[\s,{:.#\[])',
        r'\1:host, #msc-popup-modal',
        combined_css,
        flags=re.MULTILINE
    )

    m = re.search(r"<body[^>]*>([\s\S]*?)</body>", html_text, re.IGNORECASE)
    body_inner = m.group(1) if m else html_text
    body_inner = re.sub(r"<script[\s\S]*?</script>", "", body_inner, flags=re.IGNORECASE)

    return body_inner, combined_css

def is_debug_port_open():
    try:
        with urllib.request.urlopen(f"http://localhost:{DEBUG_PORT}/json", timeout=0.5):
            return True
    except Exception:
        return False

def restart_spotify_with_debug():
    spotify_exe = find_spotify()
    if not spotify_exe:
        raise FileNotFoundError(
            "Spotify desktop client not found. Looked in:\n  "
            + "\n  ".join(SPOTIFY_CANDIDATES)
        )

    print("[MSC] Closing existing Spotify instances...")
    kill_spotify()
    time.sleep(1.0)

    args = f"--remote-debugging-port={DEBUG_PORT} --remote-debugging-address=127.0.0.1"
    launched = False
    if IS_WINDOWS:
        print(f"[MSC] Launching Spotify through a stamped shortcut (taskbar merge) with {args} ...")
        try:
            launched = _launch_spotify_stamped(spotify_exe, args)
        except Exception as exc:
            print(f"[MSC] [taskbar] stamped launch failed: {exc!r}")
    if not launched:
        print(f"[MSC] Launching Spotify directly with {args} ...")
        subprocess.Popen(
            [spotify_exe, f"--remote-debugging-port={DEBUG_PORT}", "--remote-debugging-address=127.0.0.1"],
            **_quiet()
        )

def wait_for_spotify_target(timeout=30):
    deadline = time.time() + timeout
    url = f"http://localhost:{DEBUG_PORT}/json"
    print("[MSC] Waiting for Spotify page target...")

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                targets = json.loads(resp.read().decode("utf-8"))
                for target in targets:
                    target_url = target.get("url", "")
                    if target.get("type") == "page" and "spotify.com" in target_url:
                        print(f"[MSC] Attached to: {target_url}")
                        return target["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.5)

    raise TimeoutError(f"Timed out after {timeout}s waiting for Spotify target.")

def build_extension_payload(bundle):
    files = bundle["files"]
    popup_html_body, popup_css = extract_popup_parts(files.get("popup.html", ""))
    content_js = files.get("content.js", "")
    popup_js = files.get("popup.js", "")

    serialized_files = json.dumps(files)
    serialized_storage = json.dumps(bundle["storage"])
    serialized_popup_html = json.dumps(popup_html_body)
    serialized_popup_css = json.dumps(popup_css)

    ver = "1.5.8"

    return f"""
    (() => {{
        if (window.__MSC_EXT_BOOTED__) return;
        window.__MSC_EXT_BOOTED__ = true;

        // 0. Allow innerHTML under Spotify's Trusted Types CSP
        if (window.trustedTypes && window.trustedTypes.createPolicy) {{
            try {{
                window.trustedTypes.createPolicy('default', {{
                    createHTML: (s) => s,
                    createScriptURL: (s) => s,
                    createScript: (s) => s
                }});
            }} catch (e) {{}}
        }}

        const EXT_FILES = {serialized_files};
        const STORAGE_DATA = {serialized_storage};
        const storageListeners = [];
        const messageListeners = [];

        // 1. Intercept fetch() for extension assets (default.css, themes/themes.json, themes/*.css)
        const origFetch = window.fetch.bind(window);
        window.fetch = (input, init) => {{
            const url = typeof input === 'string' ? input : (input && input.url) || '';
            if (url.startsWith('msc-ext://')) {{
                const key = url.replace('msc-ext://', '').replace(/^\\/+/, '');
                if (Object.prototype.hasOwnProperty.call(EXT_FILES, key)) {{
                    return Promise.resolve(new Response(EXT_FILES[key], {{
                        status: 200,
                        headers: {{ 'Content-Type': key.endsWith('.json') ? 'application/json' : 'text/plain' }}
                    }}));
                }}
                return Promise.resolve(new Response('', {{ status: 404 }}));
            }}
            return origFetch(input, init);
        }};

        // 2. Chrome Extension API Shim (runtime, storage.local, tabs)
        window.chrome = window.chrome || {{}};
        window.chrome.runtime = {{
            getURL: (p) => 'msc-ext://' + String(p || '').replace(/^\\/+/, ''),
            getManifest: () => ({{ version: '{ver}' }}),
            lastError: null,
            onMessage: {{
                addListener: (fn) => messageListeners.push(fn)
            }}
        }};

        window.chrome.storage = {{
            local: {{
                get: (keys, cb) => {{
                    const res = {{}};
                    const list = Array.isArray(keys) ? keys : (typeof keys === 'string' ? [keys] : Object.keys(STORAGE_DATA));
                    for (const k of list) {{
                        if (Object.prototype.hasOwnProperty.call(STORAGE_DATA, k)) {{
                            res[k] = STORAGE_DATA[k];
                        }}
                    }}
                    if (cb) setTimeout(() => cb(res), 0);
                    return Promise.resolve(res);
                }},
                set: (items, cb) => {{
                    const changes = {{}};
                    for (const [k, v] of Object.entries(items || {{}})) {{
                        changes[k] = {{ oldValue: STORAGE_DATA[k], newValue: v }};
                        STORAGE_DATA[k] = v;
                    }}
                    if (typeof window.mscPersistStorage === 'function') {{
                        window.mscPersistStorage(JSON.stringify(STORAGE_DATA));
                    }}
                    for (const fn of storageListeners) {{
                        try {{ fn(changes, 'local'); }} catch (e) {{}}
                    }}
                    if (cb) setTimeout(() => cb(), 0);
                    return Promise.resolve();
                }}
            }},
            onChanged: {{
                addListener: (fn) => storageListeners.push(fn)
            }}
        }};

        window.chrome.tabs = {{
            create: (properties) => {{
                const url = properties && properties.url;
                if (typeof window.mscOpenRelease !== 'function') {{
                    return Promise.reject(new Error('Launcher release opener is unavailable.'));
                }}
                window.mscOpenRelease(url || '');
                return Promise.resolve({{ id: 2 }});
            }},
            query: async () => [{{ id: 1, url: 'https://open.spotify.com' }}],
            sendMessage: (tabId, msg) => new Promise((resolve) => {{
                let responded = false;
                for (const fn of messageListeners) {{
                    fn(msg, {{ tab: {{ id: 1 }} }}, (resp) => {{
                        responded = true;
                        resolve(resp);
                    }});
                }}
                if (!responded) resolve(null);
            }})
        }};

        const mountFullExtension = () => {{
            // Run content.js on the main Spotify document
            (function() {{
                {content_js}
            }})();

            // Keep <style id="my-spotify-custom-css"> locked right above </head>
            const headObs = new MutationObserver(() => {{
                const st = document.getElementById('my-spotify-custom-css');
                if (st && document.head && document.head.lastElementChild !== st) {{
                    document.head.appendChild(st);
                }}
            }});
            if (document.head) headObs.observe(document.head, {{ childList: true }});

            // Mount popup.html + popup.css + popup.js inside an isolated Shadow DOM
            const host = document.createElement('div');
            host.id = 'msc-shadow-host';
            document.documentElement.appendChild(host);
            const shadow = host.attachShadow({{ mode: 'open' }});

            const wrapper = document.createElement('div');
            wrapper.id = 'msc-popup-modal';
            Object.assign(wrapper.style, {{
                display: 'none', // Closed on boot; click the top-bar button (or Alt+C) to open
                position: 'fixed',
                top: '56px',
                right: '24px',
                zIndex: '999999',
                borderRadius: '12px',
                overflow: 'hidden',
                boxShadow: '0 16px 40px rgba(0, 0, 0, 0.85)',
                border: '1px solid #2e2e32',
                maxHeight: '84vh',
                overflowY: 'auto',
                background: '#161618'
            }});

            const styleTag = document.createElement('style');
            styleTag.textContent = {serialized_popup_css};
            wrapper.innerHTML = {serialized_popup_html};

            shadow.appendChild(styleTag);
            shadow.appendChild(wrapper);

            // Scope document DOM lookups inside popup.js to the ShadowRoot
            const shadowDocProxy = new Proxy(document, {{
                get(target, prop) {{
                    if (prop === 'getElementById') return (id) => shadow.getElementById(id);
                    if (prop === 'querySelector') return (sel) => shadow.querySelector(sel);
                    if (prop === 'querySelectorAll') return (sel) => shadow.querySelectorAll(sel);
                    const val = target[prop];
                    return typeof val === 'function' ? val.bind(target) : val;
                }}
            }});

            ((document) => {{
                {popup_js}
            }})(shadowDocProxy);

            const togglePopup = () => {{
                const isHidden = wrapper.style.display === 'none';
                wrapper.style.display = isHidden ? 'block' : 'none';
            }};

            const ensureNavButton = () => {{
                const bellBtn = document.querySelector('button[data-testid="whats-new-feed-button"]');
                if (!bellBtn || !bellBtn.parentElement) return;
                if (document.getElementById('msc-nav-tweaker-btn')) return;

                const btn = document.createElement('button');
                btn.id = 'msc-nav-tweaker-btn';
                btn.type = 'button';
                btn.className = bellBtn.className;
                btn.setAttribute('aria-label', 'Spotify UI Tweaker');
                btn.setAttribute('title', 'Spotify UI Tweaker (Alt+C)');
                btn.setAttribute('data-encore-id', 'buttonTertiary');

                const bellSvg = bellBtn.querySelector('svg');
                const svgClass = bellSvg ? bellSvg.getAttribute('class') : '';
                const svgStyle = bellSvg
                    ? bellSvg.getAttribute('style')
                    : '--encore-icon-height: var(--encore-graphic-size-decorative-smaller); --encore-icon-width: var(--encore-graphic-size-decorative-smaller);';

                btn.innerHTML = `
                    <svg data-encore-id="icon" role="img" aria-hidden="true" class="${{svgClass}}" viewBox="0 0 16 16" style="${{svgStyle}}">
                        <path d="M8 1a7 7 0 0 0-7 7c0 3.866 3.134 7 7 7a1.5 1.5 0 0 0 1.41-2.012 1.5 1.5 0 0 1 1.41-2.012H12a3 3 0 0 0 3-3c0-3.866-3.134-6.976-7-6.976zm-3.25 7.5a1 1 0 1 1 0-2 1 1 0 0 1 0 2zm1.75-3a1 1 0 1 1 0-2 1 1 0 0 1 0 2zm3.5 0a1 1 0 1 1 0-2 1 1 0 0 1 0 2zm2 3a1 1 0 1 1 0-2 1 1 0 0 1 0 2z"></path>
                    </svg>
                `;

                btn.addEventListener('click', (e) => {{
                    e.stopPropagation();
                    togglePopup();
                }});

                bellBtn.parentElement.insertBefore(btn, bellBtn);
            }};

            ensureNavButton();
            const navObs = new MutationObserver(() => ensureNavButton());
            navObs.observe(document.body, {{ childList: true, subtree: true }});

            document.addEventListener(
                'mousedown',
                (e) => {{
                    if (wrapper.style.display === 'none') return;
                    const path = e.composedPath ? e.composedPath() : [];
                    const navBtn = document.getElementById('msc-nav-tweaker-btn');
                    if (!path.includes(host) && (!navBtn || !path.includes(navBtn))) {{
                        wrapper.style.display = 'none';
                    }}
                }},
                true,
            );

            window.addEventListener(
                'keydown',
                (e) => {{
                    if (e.altKey && e.key.toLowerCase() === 'c') {{
                        e.preventDefault();
                        e.stopPropagation();
                        togglePopup();
                    }}
                }},
                true,
            );

            window.addEventListener(
                'keydown',
                (e) => {{
                    const isDevShortcut = (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'd')
                                    || (e.altKey && e.key.toLowerCase() === 'd');
                    if (isDevShortcut) {{
                        e.preventDefault();
                        e.stopPropagation();
                        if (typeof window.mscOpenDevTools === 'function') {{
                            window.mscOpenDevTools();
                        }}
                    }}
                }},
                true,
            );
        }};

        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', mountFullExtension);
        }} else {{
            mountFullExtension();
        }}
    }})();
    """

def launch_devtools_window():
    """Opens the active Spotify DevTools inspector in a standalone browser window."""
    try:
        with urllib.request.urlopen(f"http://localhost:{DEBUG_PORT}/json", timeout=2) as resp:
            targets = json.loads(resp.read().decode("utf-8"))
            target = next((t for t in targets if t.get("type") == "page"), None)
            if not target:
                return

            ws_part = target["webSocketDebuggerUrl"].replace("ws://", "")
            inspector_url = f"http://localhost:{DEBUG_PORT}/devtools/inspector.html?ws={ws_part}"

            if IS_WINDOWS:
                browser_candidates = [
                    os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                    os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                    os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
                    os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
                    os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
                ]
            elif IS_MAC:
                browser_candidates = [
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                    "/Applications/Chromium.app/Contents/MacOS/Chromium",
                ]
            else:
                browser_candidates = [
                    shutil.which(name)
                    for name in ("google-chrome", "microsoft-edge", "brave-browser", "chromium", "chromium-browser")
                ]

            browser_exe = next((p for p in browser_candidates if p and os.path.exists(p)), None)

            if browser_exe:
                dev_profile = os.path.join(tempfile.gettempdir(), "msc-devtools-profile")
                subprocess.Popen(
                    [
                        browser_exe,
                        f"--user-data-dir={dev_profile}",
                        "--disable-web-security",
                        "--no-first-run",
                        "--no-default-browser-check",
                        f"--app={inspector_url}"
                    ],
                    **_quiet()
                )
            else:
                webbrowser.open(f"http://localhost:{DEBUG_PORT}")
    except Exception as e:
        print(f"[MSC] Failed to launch DevTools: {e}")

async def session_loop(ws_url, payload, state):
    async with websockets.connect(ws_url, max_size=None) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
        await ws.send(json.dumps({"id": 2, "method": "Runtime.enable"}))

        await ws.send(json.dumps({
            "id": 3,
            "method": "Runtime.addBinding",
            "params": {"name": "mscPersistStorage"}
        }))
        await ws.send(json.dumps({
            "id": 4,
            "method": "Runtime.addBinding",
            "params": {"name": "mscOpenDevTools"}
        }))
        await ws.send(json.dumps({
            "id": 5,
            "method": "Runtime.addBinding",
            "params": {"name": "mscOpenRelease"}
        }))

        await ws.send(json.dumps({
            "id": 6,
            "method": "Page.addScriptToEvaluateOnNewDocument",
            "params": {"source": payload}
        }))

        await ws.send(json.dumps({
            "id": 7,
            "method": "Runtime.evaluate",
            "params": {"expression": payload}
        }))

        print("[MSC] Extension injected! Click the palette icon left of the notification bell (or press Alt+C).")

        async for raw_msg in ws:
            try:
                msg = json.loads(raw_msg)
                if msg.get("method") == "Runtime.bindingCalled":
                    params = msg.get("params", {})
                    name = params.get("name")
                    if name == "mscPersistStorage":
                        incoming = params.get("payload", "{}")
                        # Timeline of what is on disk — the crash-revert in
                        # main() uses this to undo a save that killed Spotify.
                        state.setdefault("disk", []).append((time.time(), incoming))
                        state["last_write_at"] = time.time()
                        try:
                            with open(STORAGE_PATH, "w", encoding="utf-8") as f:
                                f.write(incoming)
                        except OSError as exc:
                            print(f"[MSC] Could not save storage.json ({exc!r}). The Tweaker keeps working; settings just will not persist.")
                    elif name == "mscOpenDevTools":
                        state["inspector"] = True
                        launch_devtools_window()
                    elif name == "mscOpenRelease":
                        if params.get("payload") != RELEASE_PAGE:
                            print("[MSC] Ignored request to open an unapproved release URL.")
                            continue
                        try:
                            if not webbrowser.open(RELEASE_PAGE, new=2):
                                print("[MSC] Failed to open the release page in a browser.")
                        except Exception as exc:
                            print(f"[MSC] Failed to open the release page: {exc}")
            except Exception as exc:
                # A single malformed/failed message must never kill the session.
                print(f"[MSC] Session message error (continuing): {exc!r}")

def _read_storage_seed():
    try:
        with open(STORAGE_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


CRASH_REVERT_WINDOW_S = 8.0


def _last_survived_storage(state):
    """Newest on-disk payload that stayed applied for a while while Spotify
    kept running — i.e. proven not to crash the client. None = no file."""
    disk = state.get("disk") or []
    now = time.time()
    for i in range(len(disk) - 1, -1, -1):
        applied_at = disk[i][0]
        end_at = disk[i + 1][0] if i + 1 < len(disk) else now
        if end_at - applied_at >= CRASH_REVERT_WINDOW_S:
            return disk[i][1]
    return None


def _revert_storage_if_crash(state):
    """If Spotify died seconds after a settings save, undo that save.
    Without this, one GPU-crashing theme would sit in storage.json and
    crash-loop every future launch."""
    last_write_at = state.get("last_write_at", 0.0)
    if not last_write_at or (time.time() - last_write_at) > 6.0:
        return
    rollback = _last_survived_storage(state)
    try:
        if rollback is None:
            if os.path.exists(STORAGE_PATH):
                os.remove(STORAGE_PATH)
                print("[MSC] Spotify died right after a settings save — removed the save so the next launch boots safe.")
        else:
            with open(STORAGE_PATH, "w", encoding="utf-8") as f:
                f.write(rollback)
            print("[MSC] Spotify died right after a settings save — rolled back to the last stable save so the next launch boots safe.")
    except OSError as exc:
        print(f"[MSC] Could not roll back the last settings save ({exc!r}).")


def main():
    print(f"[MSC] Launcher build {LAUNCHER_VERSION}")
    if IS_WINDOWS:
        try:
            _ensure_taskbar_identity()
        except Exception as exc:
            print(f"[MSC] [taskbar] setup failed: {exc}")
        try:
            _start_taskbar_stamp_watchdog()
        except Exception as exc:
            print(f"[MSC] [taskbar] watchdog failed to start: {exc}")

    bundle = collect_extension_bundle()
    payload = build_extension_payload(bundle)

    claim_session_lock()

    global _session_started
    _session_started = True

    if not is_debug_port_open():
        restart_spotify_with_debug()
    else:
        print("[MSC] Spotify already running with DevTools enabled, attaching directly...")

    # Seed the crash-revert timeline with what was on disk at boot. The seed
    # is back-dated past the revert window on purpose: the boot content was
    # already rendered by Spotify before this session saved anything, so it
    # counts as proven-stable no matter how fast the first theme click is.
    state = {
        "inspector": False,
        "disk": [(time.time() - (CRASH_REVERT_WINDOW_S + 1.0), _read_storage_seed())],
        "last_write_at": 0.0,
    }

    drops = 0
    while True:
        try:
            ws_url = wait_for_spotify_target()
        except TimeoutError as exc:
            if not is_debug_port_open():
                print(f"[MSC] {exc}")
                print("[MSC] Spotify closed. Exiting cleanly.")
                return
            drops += 1
            if drops >= 6:
                print("[MSC] Spotify never exposed its debugger. Leaving Spotify alone — re-run the launcher to attach.")
                return
            print(f"[MSC] Waiting for Spotify's debugger target (attempt {drops}/6)...")
            time.sleep(1.0)
            continue

        attached_at = time.time()
        try:
            asyncio.run(session_loop(ws_url, payload, state))
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as exc:
            print(f"[MSC] Debugger session error: {exc!r}")

        # The debugger socket closed (or errored). Work out WHY before doing
        # anything drastic — nuking Spotify here is what killed re-injection.
        if not owns_session():
            print("[MSC] A newer launcher instance took over the session. Exiting without closing Spotify.")
            return
        if not is_debug_port_open():
            _revert_storage_if_crash(state)
            print("[MSC] Spotify closed. Exiting cleanly.")
            return
        if state.get("inspector"):
            # We handed the debugger to the standalone DevTools window; do not
            # fight it for the socket. Stand by until Spotify itself closes.
            print("[MSC] DevTools window owns the debugger for now — standing by. (Re-run the launcher to take the session back.)")
            while is_debug_port_open():
                time.sleep(1.0)
            print("[MSC] Spotify closed. Exiting cleanly.")
            return
        if time.time() - attached_at >= 10.0:
            # We held a healthy session; reset the failure budget.
            drops = 0
            state["inspector"] = False
        else:
            drops += 1
        if drops >= 4:
            print("[MSC] Debugger connection keeps dropping. Leaving Spotify running — re-run the launcher to re-attach.")
            return
        print(f"[MSC] Debugger connection dropped but Spotify is still running — re-attaching (attempt {drops + 1}/4)...")
        time.sleep(1.5)


if __name__ == "__main__":
    try:
        main()
    finally:
        _shutdown_kill_spotify()