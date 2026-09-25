"""Recycle through Windows IFileOperation, with no permanent-delete fallback.

Flag semantics: https://learn.microsoft.com/windows/win32/api/shobjidl_core/nf-shobjidl_core-ifileoperation-setoperationflags
"""

import ctypes
import os
from pathlib import Path
import uuid


def recycle_file(path):
    if os.name != 'nt':
        raise RuntimeError('此平台尚不支持回收站操作；文件未删除。')
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError('视频不存在，未执行移除。')

    class GUID(ctypes.Structure):
        _fields_ = [('data1', ctypes.c_uint32), ('data2', ctypes.c_uint16),
                    ('data3', ctypes.c_uint16), ('data4', ctypes.c_ubyte * 8)]

    def guid(value):
        return GUID.from_buffer_copy(uuid.UUID(value).bytes_le)

    def checked(result):
        if result < 0:
            raise RuntimeError(f'无法移入回收站（0x{result & 0xffffffff:08X}），请检查文件占用、权限及回收站设置。')

    def method(pointer, index, *arguments):
        address = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents[index]
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *arguments)(address)

    ole = ctypes.OleDLL('ole32')
    shell = ctypes.WinDLL('shell32')
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, ctypes.c_ulong,
                                     ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    ole.CoCreateInstance.restype = ctypes.c_long
    shell.SHCreateItemFromParsingName.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p,
                                                  ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    shell.SHCreateItemFromParsingName.restype = ctypes.c_long
    operation, item = ctypes.c_void_p(), ctypes.c_void_p()
    checked(ole.CoInitializeEx(None, 2))  # STA, initialized independently per request thread.
    try:
        clsid = guid('3ad05575-8857-4850-9277-11b85bdb8e09')
        iid = guid('947aab5f-0a5c-4c13-b4d6-4bf7836fc9f8')
        checked(ole.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(operation)))
        # RECYCLEONDELETE | ADDUNDORECORD | EARLYFAILURE | NOERRORUI | NOCONFIRMATION | SILENT
        flags = 0x80000 | 0x20000000 | 0x100000 | 0x400 | 0x10 | 0x04
        checked(method(operation, 5, ctypes.c_ulong)(operation, flags))
        shell_iid = guid('43826d1e-e718-42ee-bc55-a1e261c37bfe')
        checked(shell.SHCreateItemFromParsingName(str(path), None, ctypes.byref(shell_iid), ctypes.byref(item)))
        checked(method(operation, 18, ctypes.c_void_p, ctypes.c_void_p)(operation, item, None))
        checked(method(operation, 21)(operation))
        aborted = ctypes.c_int()
        checked(method(operation, 22, ctypes.POINTER(ctypes.c_int))(operation, ctypes.byref(aborted)))
        if aborted.value or path.exists():
            raise RuntimeError('移入回收站未完成，文件未从审阅列表移除。')
    finally:
        if item.value:
            method(item, 2)(item)
        if operation.value:
            method(operation, 2)(operation)
        ole.CoUninitialize()
