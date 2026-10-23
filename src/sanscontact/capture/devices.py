"""List cameras by name without opening them, and exclude infrared cameras.

OpenCV only knows camera indexes. The index order of each backend is the
order of its own enumeration API, so we ask the same API for names:
Media Foundation for CAP_MSMF, DirectShow for CAP_DSHOW. Windows Hello
infrared cameras are never offered.
"""

from __future__ import annotations

import ctypes
import re
from ctypes import wintypes
from dataclasses import dataclass

from sanscontact import _win32 as w

_INFRARED = re.compile(r"(\bIR\b|infra\s*-?\s*red|infrarouge|windows\s+hello|\bdepth\b)", re.IGNORECASE)

# Media Foundation attribute keys (mfidl.h)
_MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE = w.GUID.parse("c60ac5fe-252a-478f-a0ef-bc8fa5f7cad3")
_MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID = w.GUID.parse("8ac3587a-4ae7-42d8-99e0-0a6013eef90f")
_MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME = w.GUID.parse("60d0e559-52f8-4fa2-bbce-acdb34a8ec01")
_MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK = w.GUID.parse("58f0aad8-22bf-4f8a-bb3d-d2c4978c6e2f")
_MF_VERSION = 0x00020070

# DirectShow (strmif.h / uuids.h)
_CLSID_SYSTEM_DEVICE_ENUM = w.GUID.parse("62be5d10-60eb-11d0-bd3b-00a0c911ce86")
_IID_ICREATE_DEV_ENUM = w.GUID.parse("29840822-5b84-11d0-bd3b-00a0c911ce86")
_CLSID_VIDEO_INPUT_DEVICE_CATEGORY = w.GUID.parse("860bb310-5d01-11d0-bd3b-00a0c911ce86")
_IID_IPROPERTY_BAG = w.GUID.parse("55272a00-42cb-11ce-8135-00aa004bb851")
_VT_BSTR = 8


@dataclass(frozen=True)
class CameraDevice:
    backend: str
    index: int
    name: str
    infrared: bool

    @property
    def eligible(self) -> bool:
        return not self.infrared


def is_infrared(name: str) -> bool:
    return bool(_INFRARED.search(name))


def list_cameras(backend: str) -> list[CameraDevice]:
    if backend == "msmf":
        names = _media_foundation_names()
    elif backend == "dshow":
        names = _directshow_names()
    else:
        raise ValueError(f"unknown backend {backend!r}")
    return [CameraDevice(backend, i, name, is_infrared(name)) for i, name in enumerate(names)]


def eligible_cameras(backend: str) -> list[CameraDevice]:
    return [c for c in list_cameras(backend) if c.eligible]


def find_camera(backend: str, name: str | None) -> CameraDevice | None:
    """The chosen camera, or the only eligible one when nothing was chosen yet."""
    cameras = eligible_cameras(backend)
    if name is not None:
        return next((c for c in cameras if c.name == name), None)
    return cameras[0] if len(cameras) == 1 else None


class _ComApartment:
    def __enter__(self):
        hr = w.CoInitializeEx(None, w.COINIT_MULTITHREADED)
        self._owned = hr in (w.S_OK, w.S_FALSE)
        if not self._owned and hr != w.RPC_E_CHANGED_MODE:
            raise OSError(hr, "CoInitializeEx failed")
        return self

    def __exit__(self, *exc):
        if self._owned:
            w.CoUninitialize()


def _media_foundation_names() -> list[str]:
    mfplat = ctypes.WinDLL("mfplat")
    mf = ctypes.WinDLL("mf")
    mfplat.MFStartup.argtypes = (wintypes.ULONG, wintypes.DWORD)
    mfplat.MFStartup.restype = w.HRESULT
    mfplat.MFShutdown.restype = w.HRESULT
    mfplat.MFCreateAttributes.argtypes = (ctypes.POINTER(ctypes.c_void_p), wintypes.UINT)
    mfplat.MFCreateAttributes.restype = w.HRESULT
    mf.MFEnumDeviceSources.argtypes = (
        ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)), ctypes.POINTER(wintypes.UINT)
    )
    mf.MFEnumDeviceSources.restype = w.HRESULT

    names: list[str] = []
    with _ComApartment():
        if mfplat.MFStartup(_MF_VERSION, 0) < 0:
            raise OSError("MFStartup failed")
        try:
            attributes = ctypes.c_void_p()
            _check(mfplat.MFCreateAttributes(ctypes.byref(attributes), 1), "MFCreateAttributes")
            try:
                set_guid = w.com_method(attributes, 24, w.HRESULT, ctypes.POINTER(w.GUID), ctypes.POINTER(w.GUID))
                _check(set_guid(ctypes.byref(_MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE),
                                ctypes.byref(_MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID)), "SetGUID")
                devices = ctypes.POINTER(ctypes.c_void_p)()
                count = wintypes.UINT(0)
                _check(mf.MFEnumDeviceSources(attributes, ctypes.byref(devices), ctypes.byref(count)),
                       "MFEnumDeviceSources")
                try:
                    for i in range(count.value):
                        names.append(_mf_string(devices[i], _MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME) or f"Camera {i}")
                finally:
                    for i in range(count.value):
                        w.com_release(devices[i])
                    w.CoTaskMemFree(devices)
            finally:
                w.com_release(attributes)
        finally:
            mfplat.MFShutdown()
    return names


def _mf_string(activate: int, key: w.GUID) -> str | None:
    get_allocated_string = w.com_method(
        activate, 13, w.HRESULT, ctypes.POINTER(w.GUID), ctypes.POINTER(ctypes.c_wchar_p),
        ctypes.POINTER(wintypes.UINT),
    )
    value = ctypes.c_wchar_p()
    length = wintypes.UINT(0)
    if get_allocated_string(ctypes.byref(key), ctypes.byref(value), ctypes.byref(length)) < 0:
        return None
    try:
        return value.value
    finally:
        w.CoTaskMemFree(value)


class _VARIANT(ctypes.Structure):
    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("r1", ctypes.c_ushort),
        ("r2", ctypes.c_ushort),
        ("r3", ctypes.c_ushort),
        ("value", ctypes.c_void_p),
        ("extra", ctypes.c_void_p),
    ]


def _directshow_names() -> list[str]:
    names: list[str] = []
    with _ComApartment():
        dev_enum = ctypes.c_void_p()
        _check(w.CoCreateInstance(ctypes.byref(_CLSID_SYSTEM_DEVICE_ENUM), None, w.CLSCTX_INPROC_SERVER,
                                  ctypes.byref(_IID_ICREATE_DEV_ENUM), ctypes.byref(dev_enum)),
               "CoCreateInstance(SystemDeviceEnum)")
        try:
            create_class_enumerator = w.com_method(
                dev_enum, 3, w.HRESULT, ctypes.POINTER(w.GUID), ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD
            )
            enum_moniker = ctypes.c_void_p()
            hr = create_class_enumerator(ctypes.byref(_CLSID_VIDEO_INPUT_DEVICE_CATEGORY),
                                         ctypes.byref(enum_moniker), 0)
            if hr == w.S_FALSE or not enum_moniker.value:
                return names
            _check(hr, "CreateClassEnumerator")
            try:
                next_moniker = w.com_method(
                    enum_moniker, 3, w.HRESULT, wintypes.ULONG, ctypes.POINTER(ctypes.c_void_p),
                    ctypes.POINTER(wintypes.ULONG),
                )
                while True:
                    moniker = ctypes.c_void_p()
                    fetched = wintypes.ULONG(0)
                    if next_moniker(1, ctypes.byref(moniker), ctypes.byref(fetched)) != w.S_OK or not fetched.value:
                        break
                    try:
                        names.append(_moniker_name(moniker) or f"Camera {len(names)}")
                    finally:
                        w.com_release(moniker)
            finally:
                w.com_release(enum_moniker)
        finally:
            w.com_release(dev_enum)
    return names


def _moniker_name(moniker: ctypes.c_void_p) -> str | None:
    bind_to_storage = w.com_method(
        moniker, 9, w.HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(w.GUID),
        ctypes.POINTER(ctypes.c_void_p),
    )
    bag = ctypes.c_void_p()
    if bind_to_storage(None, None, ctypes.byref(_IID_IPROPERTY_BAG), ctypes.byref(bag)) < 0:
        return None
    try:
        read = w.com_method(bag, 3, w.HRESULT, wintypes.LPCWSTR, ctypes.POINTER(_VARIANT), ctypes.c_void_p)
        variant = _VARIANT()
        variant.vt = _VT_BSTR
        if read("FriendlyName", ctypes.byref(variant), None) < 0 or variant.vt != _VT_BSTR or not variant.value:
            return None
        try:
            return ctypes.wstring_at(variant.value)
        finally:
            w.SysFreeString(variant.value)
    finally:
        w.com_release(bag)


def _check(hr: int, what: str) -> None:
    if hr < 0:
        raise OSError(hr, f"{what} failed (0x{hr & 0xFFFFFFFF:08X})")
