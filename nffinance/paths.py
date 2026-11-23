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


def configured_data_dir():
    """用户选择的数据文件夹；尚未选择时返回 None。"""
    try:
        d = json.loads(config_path().read_text(encoding="utf-8")).get("data_dir")
    except Exception:
        return None
    return Path(d) if d else None


def save_data_dir(p) -> None:
    config_path().write_text(json.dumps({"data_dir": str(p)}, ensure_ascii=False), encoding="utf-8")


def data_dir() -> Path:
    return configured_data_dir() or default_data_dir()
