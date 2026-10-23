"""Shared ctypes declarations for the Win32 APIs used by SansContact.

Declarations only: importing this module has no side effect besides loading
system DLLs. Every function gets explicit argtypes/restype so that handles and
pointers keep their full 64-bit width.
"""

from __future__ import annotations

import ctypes
import uuid
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)
iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
ole32 = ctypes.WinDLL("ole32", use_last_error=True)
oleaut32 = ctypes.WinDLL("oleaut32", use_last_error=True)
shcore = ctypes.WinDLL("shcore", use_last_error=True)

LRESULT = wintypes.LPARAM
HRESULT = ctypes.c_long
ULONG_PTR = wintypes.WPARAM
HANDLE = wintypes.HANDLE

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
)


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def parse(cls, text: str) -> GUID:
        return cls.from_buffer_copy(uuid.UUID(text).bytes_le)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class POWERBROADCAST_SETTING(ctypes.Structure):
    _fields_ = [("PowerSetting", GUID), ("DataLength", wintypes.DWORD), ("Data", ctypes.c_ubyte * 1)]


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _declare(dll: ctypes.WinDLL, name: str, restype, *argtypes):
    func = getattr(dll, name)
    func.restype = restype
    func.argtypes = argtypes
    return func


P = ctypes.POINTER

# --- user32: windows, messages, input -------------------------------------------------------
RegisterClassExW = _declare(user32, "RegisterClassExW", wintypes.ATOM, P(WNDCLASSEXW))
UnregisterClassW = _declare(user32, "UnregisterClassW", wintypes.BOOL, wintypes.LPCWSTR, wintypes.HINSTANCE)
CreateWindowExW = _declare(
    user32, "CreateWindowExW", wintypes.HWND,
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
)
DestroyWindow = _declare(user32, "DestroyWindow", wintypes.BOOL, wintypes.HWND)
DefWindowProcW = _declare(
    user32, "DefWindowProcW", LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)
GetMessageW = _declare(user32, "GetMessageW", wintypes.BOOL, P(wintypes.MSG), wintypes.HWND, wintypes.UINT,
                       wintypes.UINT)
TranslateMessage = _declare(user32, "TranslateMessage", wintypes.BOOL, P(wintypes.MSG))
DispatchMessageW = _declare(user32, "DispatchMessageW", LRESULT, P(wintypes.MSG))
PostMessageW = _declare(user32, "PostMessageW", wintypes.BOOL, wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                        wintypes.LPARAM)
PostQuitMessage = _declare(user32, "PostQuitMessage", None, ctypes.c_int)
RegisterWindowMessageW = _declare(user32, "RegisterWindowMessageW", wintypes.UINT, wintypes.LPCWSTR)
RegisterHotKey = _declare(user32, "RegisterHotKey", wintypes.BOOL, wintypes.HWND, ctypes.c_int, wintypes.UINT,
                          wintypes.UINT)
UnregisterHotKey = _declare(user32, "UnregisterHotKey", wintypes.BOOL, wintypes.HWND, ctypes.c_int)
CreatePopupMenu = _declare(user32, "CreatePopupMenu", wintypes.HMENU)
AppendMenuW = _declare(user32, "AppendMenuW", wintypes.BOOL, wintypes.HMENU, wintypes.UINT, ULONG_PTR,
                       wintypes.LPCWSTR)
TrackPopupMenuEx = _declare(user32, "TrackPopupMenuEx", wintypes.BOOL, wintypes.HMENU, wintypes.UINT,
                            ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.LPVOID)
DestroyMenu = _declare(user32, "DestroyMenu", wintypes.BOOL, wintypes.HMENU)
SetForegroundWindow = _declare(user32, "SetForegroundWindow", wintypes.BOOL, wintypes.HWND)
GetForegroundWindow = _declare(user32, "GetForegroundWindow", wintypes.HWND)
GetCursorPos = _declare(user32, "GetCursorPos", wintypes.BOOL, P(wintypes.POINT))
SendInput = _declare(user32, "SendInput", wintypes.UINT, wintypes.UINT, P(INPUT), ctypes.c_int)
WindowFromPoint = _declare(user32, "WindowFromPoint", wintypes.HWND, wintypes.POINT)
GetAncestor = _declare(user32, "GetAncestor", wintypes.HWND, wintypes.HWND, wintypes.UINT)
GetWindowThreadProcessId = _declare(user32, "GetWindowThreadProcessId", wintypes.DWORD, wintypes.HWND,
                                    P(wintypes.DWORD))
MessageBoxW = _declare(user32, "MessageBoxW", ctypes.c_int, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
                       wintypes.UINT)
ShowWindow = _declare(user32, "ShowWindow", wintypes.BOOL, wintypes.HWND, ctypes.c_int)
SetWindowPos = _declare(user32, "SetWindowPos", wintypes.BOOL, wintypes.HWND, wintypes.HWND, ctypes.c_int,
                        ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
UpdateLayeredWindow = _declare(
    user32, "UpdateLayeredWindow", wintypes.BOOL,
    wintypes.HWND, wintypes.HDC, P(wintypes.POINT), P(wintypes.SIZE), wintypes.HDC, P(wintypes.POINT),
    wintypes.COLORREF, P(BLENDFUNCTION), wintypes.DWORD,
)
GetDC = _declare(user32, "GetDC", wintypes.HDC, wintypes.HWND)
ReleaseDC = _declare(user32, "ReleaseDC", ctypes.c_int, wintypes.HWND, wintypes.HDC)
CreateIconIndirect = _declare(user32, "CreateIconIndirect", wintypes.HICON, P(ICONINFO))
DestroyIcon = _declare(user32, "DestroyIcon", wintypes.BOOL, wintypes.HICON)
SetProcessDpiAwarenessContext = _declare(user32, "SetProcessDpiAwarenessContext", wintypes.BOOL, HANDLE)
GetDpiForSystem = _declare(user32, "GetDpiForSystem", wintypes.UINT)
GetSystemMetrics = _declare(user32, "GetSystemMetrics", ctypes.c_int, ctypes.c_int)
GetSystemMetricsForDpi = _declare(user32, "GetSystemMetricsForDpi", ctypes.c_int, ctypes.c_int, wintypes.UINT)
GetDoubleClickTime = _declare(user32, "GetDoubleClickTime", wintypes.UINT)
EnumDisplayMonitors = _declare(user32, "EnumDisplayMonitors", wintypes.BOOL, wintypes.HDC, P(wintypes.RECT),
                               MONITORENUMPROC, wintypes.LPARAM)
GetMonitorInfoW = _declare(user32, "GetMonitorInfoW", wintypes.BOOL, wintypes.HMONITOR, P(MONITORINFOEXW))
MonitorFromPoint = _declare(user32, "MonitorFromPoint", wintypes.HMONITOR, wintypes.POINT, wintypes.DWORD)
RegisterPowerSettingNotification = _declare(user32, "RegisterPowerSettingNotification", HANDLE, HANDLE,
                                            P(GUID), wintypes.DWORD)
UnregisterPowerSettingNotification = _declare(user32, "UnregisterPowerSettingNotification", wintypes.BOOL,
                                              HANDLE)

# --- kernel32 / advapi32: process, tokens, single instance ----------------------------------
GetModuleHandleW = _declare(kernel32, "GetModuleHandleW", wintypes.HMODULE, wintypes.LPCWSTR)
CreateMutexW = _declare(kernel32, "CreateMutexW", HANDLE, wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
CloseHandle = _declare(kernel32, "CloseHandle", wintypes.BOOL, HANDLE)
GetCurrentProcess = _declare(kernel32, "GetCurrentProcess", HANDLE)
OpenProcess = _declare(kernel32, "OpenProcess", HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
GetProcessTimes = _declare(kernel32, "GetProcessTimes", wintypes.BOOL, HANDLE, P(wintypes.FILETIME),
                           P(wintypes.FILETIME), P(wintypes.FILETIME), P(wintypes.FILETIME))
K32GetProcessMemoryInfo = _declare(kernel32, "K32GetProcessMemoryInfo", wintypes.BOOL, HANDLE,
                                   P(PROCESS_MEMORY_COUNTERS), wintypes.DWORD)
OpenProcessToken = _declare(advapi32, "OpenProcessToken", wintypes.BOOL, HANDLE, wintypes.DWORD, P(HANDLE))
GetTokenInformation = _declare(advapi32, "GetTokenInformation", wintypes.BOOL, HANDLE, ctypes.c_int,
                               wintypes.LPVOID, wintypes.DWORD, P(wintypes.DWORD))
GetSidSubAuthorityCount = _declare(advapi32, "GetSidSubAuthorityCount", P(ctypes.c_ubyte), wintypes.LPVOID)
GetSidSubAuthority = _declare(advapi32, "GetSidSubAuthority", P(wintypes.DWORD), wintypes.LPVOID,
                              wintypes.DWORD)

# --- session, shell, gdi, dpi -------------------------------------------------------------
WTSRegisterSessionNotification = _declare(wtsapi32, "WTSRegisterSessionNotification", wintypes.BOOL,
                                          wintypes.HWND, wintypes.DWORD)
WTSUnRegisterSessionNotification = _declare(wtsapi32, "WTSUnRegisterSessionNotification", wintypes.BOOL,
                                            wintypes.HWND)
Shell_NotifyIconW = _declare(shell32, "Shell_NotifyIconW", wintypes.BOOL, wintypes.DWORD, P(NOTIFYICONDATAW))
SHGetKnownFolderPath = _declare(shell32, "SHGetKnownFolderPath", HRESULT, P(GUID), wintypes.DWORD, HANDLE,
                                P(wintypes.LPWSTR))
CreateDIBSection = _declare(gdi32, "CreateDIBSection", wintypes.HBITMAP, wintypes.HDC, P(BITMAPINFOHEADER),
                            wintypes.UINT, P(wintypes.LPVOID), HANDLE, wintypes.DWORD)
CreateBitmap = _declare(gdi32, "CreateBitmap", wintypes.HBITMAP, ctypes.c_int, ctypes.c_int, wintypes.UINT,
                        wintypes.UINT, wintypes.LPVOID)
CreateCompatibleDC = _declare(gdi32, "CreateCompatibleDC", wintypes.HDC, wintypes.HDC)
SelectObject = _declare(gdi32, "SelectObject", wintypes.HGDIOBJ, wintypes.HDC, wintypes.HGDIOBJ)
DeleteObject = _declare(gdi32, "DeleteObject", wintypes.BOOL, wintypes.HGDIOBJ)
DeleteDC = _declare(gdi32, "DeleteDC", wintypes.BOOL, wintypes.HDC)
GetDpiForMonitor = _declare(shcore, "GetDpiForMonitor", HRESULT, wintypes.HMONITOR, ctypes.c_int,
                            P(wintypes.UINT), P(wintypes.UINT))

# --- networking tables (read-only inspection of our own endpoints) ----------------------------
GetExtendedTcpTable = _declare(iphlpapi, "GetExtendedTcpTable", wintypes.DWORD, wintypes.LPVOID,
                               P(wintypes.DWORD), wintypes.BOOL, wintypes.ULONG, ctypes.c_int, wintypes.ULONG)
GetExtendedUdpTable = _declare(iphlpapi, "GetExtendedUdpTable", wintypes.DWORD, wintypes.LPVOID,
                               P(wintypes.DWORD), wintypes.BOOL, wintypes.ULONG, ctypes.c_int, wintypes.ULONG)

# --- COM ------------------------------------------------------------------------------------
CoInitializeEx = _declare(ole32, "CoInitializeEx", HRESULT, wintypes.LPVOID, wintypes.DWORD)
CoUninitialize = _declare(ole32, "CoUninitialize", None)
CoCreateInstance = _declare(ole32, "CoCreateInstance", HRESULT, P(GUID), wintypes.LPVOID, wintypes.DWORD,
                            P(GUID), P(wintypes.LPVOID))
CoTaskMemFree = _declare(ole32, "CoTaskMemFree", None, wintypes.LPVOID)
SysFreeString = _declare(oleaut32, "SysFreeString", None, wintypes.LPVOID)

# --- constants ------------------------------------------------------------------------------
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_QUIT = 0x0012
WM_NULL = 0x0000
WM_POWERBROADCAST = 0x0218
WM_DISPLAYCHANGE = 0x007E
WM_HOTKEY = 0x0312
WM_WTSSESSION_CHANGE = 0x02B1
WM_CONTEXTMENU = 0x007B
WM_USER = 0x0400
WM_APP = 0x8000

PBT_APMSUSPEND = 0x0004
PBT_APMRESUMEAUTOMATIC = 0x0012
PBT_POWERSETTINGCHANGE = 0x8013

WTS_CONSOLE_DISCONNECT = 0x2
WTS_REMOTE_DISCONNECT = 0x4
WTS_SESSION_LOGOFF = 0x6
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8
NOTIFY_FOR_THIS_SESSION = 0

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
SM_CXSMICON = 49
SM_REMOTESESSION = 0x1000

DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = HANDLE(-4)
MDT_EFFECTIVE_DPI = 0
MONITOR_DEFAULTTONEAREST = 2
MONITORINFOF_PRIMARY = 1
GA_ROOT = 2

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIM_SETVERSION = 4
NIF_MESSAGE = 0x01
NIF_ICON = 0x02
NIF_TIP = 0x04
NIF_INFO = 0x10
NIF_SHOWTIP = 0x80
NIIF_INFO = 0x1
NIIF_WARNING = 0x2
NIIF_RESPECT_QUIET_TIME = 0x80
NOTIFYICON_VERSION_4 = 4
NIN_SELECT = WM_USER + 0
NIN_KEYSELECT = WM_USER + 1

MF_STRING = 0x0000
MF_GRAYED = 0x0001
MF_CHECKED = 0x0008
MF_POPUP = 0x0010
MF_SEPARATOR = 0x0800
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080

MB_OK = 0x0
MB_OKCANCEL = 0x1
MB_YESNO = 0x4
MB_ICONWARNING = 0x30
MB_ICONINFORMATION = 0x40
MB_DEFBUTTON2 = 0x100
MB_SETFOREGROUND = 0x10000
MB_TOPMOST = 0x40000
IDOK = 1
IDYES = 6

WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
ULW_ALPHA = 0x02
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
BI_RGB = 0
DIB_RGB_COLORS = 0

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TOKEN_INTEGRITY_LEVEL = 25
ERROR_ALREADY_EXISTS = 183
ERROR_ACCESS_DENIED = 5
ERROR_INSUFFICIENT_BUFFER = 122
NO_ERROR = 0

COINIT_MULTITHREADED = 0x0
RPC_E_CHANGED_MODE = -2147417850  # 0x80010106 as a signed HRESULT
CLSCTX_INPROC_SERVER = 0x1
S_OK = 0
S_FALSE = 1

DEVICE_NOTIFY_WINDOW_HANDLE = 0
GUID_CONSOLE_DISPLAY_STATE = GUID.parse("6fe69556-704a-47a0-8f24-c28d936fda47")
FOLDERID_DOCUMENTS = GUID.parse("fdd39ad0-238f-46af-adb4-6c85480369c7")
FOLDERID_DESKTOP = GUID.parse("b4bfcc3a-db2c-424c-b029-7fe99a87c641")


def com_method(pointer: int | ctypes.c_void_p, index: int, restype, *argtypes):
    """Return a callable for the COM method at ``index`` of the object's vtable."""
    address = pointer.value if isinstance(pointer, ctypes.c_void_p) else pointer
    vtable = ctypes.cast(address, P(P(ctypes.c_void_p)))[0]
    prototype = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    method = prototype(vtable[index])
    return lambda *args: method(address, *args)


def com_release(pointer: int | ctypes.c_void_p | None) -> None:
    address = pointer.value if isinstance(pointer, ctypes.c_void_p) else pointer
    if address:
        com_method(address, 2, wintypes.ULONG)()
