"""邮箱密码的本机加密保存：Windows 用 DPAPI（绑定当前 Windows 账户）。失败时返回 None，程序改为发送时询问密码。"""
import base64
import sys


def _blob(data: bytes):
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf, DATA_BLOB


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes

    inb, keep, DATA_BLOB = _blob(data)
    out = DATA_BLOB()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(inb), None, None, None, None, 0, ctypes.byref(out)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)
    del keep


def protect(text: str):
    """返回可存入 config.json 的字符串；无法加密时返回 None（此时不保存密码）。"""
    try:
        if sys.platform == "win32":
            return "dpapi:" + base64.b64encode(_dpapi(text.encode("utf-8"), True)).decode()
    except Exception:
        return None
    return None


def unprotect(value):
    if not value or not str(value).startswith("dpapi:") or sys.platform != "win32":
        return None
    try:
        return _dpapi(base64.b64decode(value[6:]), False).decode("utf-8")
    except Exception:
        return None
