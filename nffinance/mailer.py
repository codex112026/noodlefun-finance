"""月底打包文件夹为 zip，并通过 SMTP 发送（zip 作为附件）。"""
import os
import smtplib
import ssl
import zipfile
from datetime import datetime
from email.message import EmailMessage

SKIP_NAMES = {"desktop.ini", "thumbs.db", ".ds_store"}


def make_zip(folder: str, zip_path: str, only_ym=None):
    """打包 folder 内全部文件（含子文件夹）。only_ym=(年,月) 时只打包该月内修改过的文件。
    返回 (文件数, zip 大小字节, 跳过的文件列表)。"""
    count, skipped = 0, []
    folder = os.path.abspath(folder)
    zip_abs = os.path.abspath(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(folder):
            for name in files:
                if name.startswith("~$") or name.lower() in SKIP_NAMES:
                    continue
                full = os.path.join(root, name)
                if os.path.abspath(full) == zip_abs:
                    continue
                try:
                    if only_ym:
                        t = datetime.fromtimestamp(os.path.getmtime(full))
                        if (t.year, t.month) != tuple(only_ym):
                            continue
                    z.write(full, os.path.relpath(full, folder))
                    count += 1
                except OSError as e:
                    skipped.append(f"{full}: {e}")
    return count, os.path.getsize(zip_path), skipped


def parse_recipients(text: str):
    return [a.strip() for a in text.replace(";", ",").replace("\n", ",").split(",") if a.strip()]


def fill(text: str, y: int, m: int, count: int = 0, size: str = "") -> str:
    """替换 {month} {year} {count} {size}（用简单替换，正文里出现其他花括号也不会出错）。"""
    return (text.replace("{month}", f"{m:02d}/{y}").replace("{year}", str(y))
            .replace("{count}", str(count)).replace("{size}", size))


def human_size(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB" if n >= 1024 * 1024 else f"{max(1, n // 1024)} KB"


def _connect(host, port, security, user, password):
    ctx = ssl.create_default_context()
    if security == "ssl":
        s = smtplib.SMTP_SSL(host, int(port), context=ctx, timeout=60)
    else:
        s = smtplib.SMTP(host, int(port), timeout=60)
        s.ehlo()
        if security == "starttls":
            s.starttls(context=ctx)
            s.ehlo()
    if user and password:
        s.login(user, password)
    return s


def test_login(host, port, security, user, password):
    s = _connect(host, port, security, user, password)
    s.quit()


def send_mail(host, port, security, user, password, sender, recipients, subject, body, attachment):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)
    with open(attachment, "rb") as f:
        msg.add_attachment(f.read(), maintype="application", subtype="zip", filename=os.path.basename(attachment))
    s = _connect(host, port, security, user, password)
    try:
        s.send_message(msg)
    finally:
        s.quit()
