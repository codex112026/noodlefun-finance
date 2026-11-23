import os
import sys
from pathlib import Path


def resource_path(rel: str) -> Path:
    """开发环境与 PyInstaller 打包后都能找到资源文件。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / rel
    return Path(__file__).resolve().parent.parent / rel


def data_dir() -> Path:
    """数据库所在目录：%APPDATA%\\NoodleFunFinance（更新软件不会影响数据）。"""
    root = os.environ.get("APPDATA") or str(Path.home() / ".local" / "share")
    p = Path(root) / "NoodleFunFinance"
    p.mkdir(parents=True, exist_ok=True)
    return p
