import json
import os
import sys
from pathlib import Path


def resource_path(rel: str) -> Path:
    """开发环境与 PyInstaller 打包后都能找到资源文件。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / rel
    return Path(__file__).resolve().parent.parent / rel


def default_data_dir() -> Path:
    """默认位置：%APPDATA%\\NoodleFunFinance；同时存放 config.json（只记录用户选择的数据文件夹）。"""
    root = os.environ.get("APPDATA") or str(Path.home() / ".local" / "share")
    p = Path(root) / "NoodleFunFinance"
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> Path:
    return default_data_dir() / "config.json"


def _cfg() -> dict:
    try:
        return json.loads(config_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_config(key, default=None):
    return _cfg().get(key, default)


def set_config(key, value) -> None:
    """本机配置（%APPDATA%\\NoodleFunFinance\\config.json）：数据文件夹位置、加密后的邮箱密码等。"""
    c = _cfg()
    c[key] = value
    config_path().write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")


def configured_data_dir():
    """用户选择的数据文件夹；尚未选择时返回 None。"""
    d = get_config("data_dir")
    return Path(d) if d else None


def save_data_dir(p) -> None:
    set_config("data_dir", str(p))


def data_dir() -> Path:
    return configured_data_dir() or default_data_dir()
