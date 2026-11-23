"""通过 GitHub Releases 检查更新、下载安装包并静默安装（无第三方依赖，仅标准库）。"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

from .version import GITHUB_REPO, __version__

API = "https://api.github.com/repos/{repo}/releases/latest"
UA = {"User-Agent": "NoodleFunFinance-Updater", "Accept": "application/vnd.github+json"}


def repo_configured() -> bool:
    return bool(GITHUB_REPO) and "YOUR_GITHUB_USER" not in GITHUB_REPO


def _ver(s: str):
    s = s.strip().lstrip("vV")
    parts = []
    for p in s.split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def check_latest():
    """返回 None（已是最新）或 dict(version, url, sha_url, notes)。网络错误会抛异常。"""
    req = urllib.request.Request(API.format(repo=GITHUB_REPO), headers=UA)
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.load(r)
    tag = data.get("tag_name", "")
    if _ver(tag) <= _ver(__version__):
        return None
    assets = {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}
    setup = next((u for n, u in assets.items() if n.lower().endswith("setup.exe")), None)
    if not setup:
        raise RuntimeError("Release has no Setup.exe asset")
    sha = next((u for n, u in assets.items() if n.lower().endswith("setup.exe.sha256")), None)
    return {"version": tag.lstrip("vV"), "url": setup, "sha_url": sha, "notes": data.get("body", "")}


def download(info, progress_cb=None, cancelled=lambda: False) -> str:
    """下载安装包到临时目录，返回本地路径；若 Release 附带 .sha256 则校验。"""
    dest = os.path.join(tempfile.mkdtemp(prefix="nff_update_"), "NoodleFunFinance-Setup.exe")
    req = urllib.request.Request(info["url"], headers=UA)
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            if cancelled():
                raise RuntimeError("cancelled")
            chunk = r.read(64 * 1024)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            got += len(chunk)
            if progress_cb:
                progress_cb(got, total)
    if info.get("sha_url"):
        req = urllib.request.Request(info["sha_url"], headers=UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            expected = r.read().decode().split()[0].lower()
        if expected != h.hexdigest().lower():
            raise RuntimeError("SHA256 mismatch")
    return dest


def run_installer(path: str):
    """静默安装并在完成后自动重启程序；调用后应立即退出当前程序。"""
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [path, "/SILENT", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS", "/NOCANCEL"],
        creationflags=flags if sys.platform == "win32" else 0,
        close_fds=True,
    )
