"""通过 Microsoft Graph 发信（Microsoft 365 / Exchange Online）：登录一次（支持二次验证），令牌本机加密缓存。"""
import base64
import os

import msal
import requests

SCOPES = ["https://graph.microsoft.com/Mail.Send"]
GRAPH = "https://graph.microsoft.com/v1.0"
INLINE_MAX = 2_500_000          # 小于此大小的附件直接随邮件发送
CHUNK = 10 * 327680             # 上传分块（须为 320 KiB 的倍数，且小于 4 MB）


class GraphAuth:
    def __init__(self, client_id: str, tenant_id: str, cache_text=None):
        self.cache = msal.SerializableTokenCache()
        if cache_text:
            try:
                self.cache.deserialize(cache_text)
            except Exception:
                pass
        self.app = msal.PublicClientApplication(
            client_id.strip(), authority=f"https://login.microsoftonline.com/{tenant_id.strip()}",
            token_cache=self.cache)

    def account(self):
        accs = self.app.get_accounts()
        return accs[0] if accs else None

    def token(self, interactive=False, login_hint=None):
        """先静默刷新；没有登录记录且 interactive=True 时打开浏览器登录。"""
        acc = self.account()
        if acc:
            r = self.app.acquire_token_silent(SCOPES, account=acc)
            if r and "access_token" in r:
                return r
        if not interactive:
            return None
        r = self.app.acquire_token_interactive(SCOPES, login_hint=login_hint or None, timeout=240)
        if "access_token" not in r:
            raise RuntimeError(r.get("error_description") or r.get("error") or str(r))
        return r

    def username(self) -> str:
        acc = self.account()
        return acc["username"] if acc else ""

    def cache_text(self):
        return self.cache.serialize() if self.cache.has_state_changed else None

    def sign_out(self):
        for acc in self.app.get_accounts():
            self.app.remove_account(acc)


def _check(r: requests.Response, ok=(200, 201, 202, 204)):
    if r.status_code in ok:
        return r
    try:
        msg = r.json()["error"]["message"]
    except Exception:
        msg = r.text[:300]
    raise RuntimeError(f"HTTP {r.status_code}: {msg}")


def send(access_token: str, recipients, subject: str, body: str, attachment_path: str, base=None):
    """发送带附件的邮件（以登录用户的身份）。小附件一次发出；大附件走草稿 + 分块上传。"""
    base = base or GRAPH
    h = {"Authorization": f"Bearer {access_token}"}
    name = os.path.basename(attachment_path)
    size = os.path.getsize(attachment_path)
    msg = {
        "subject": subject,
        "body": {"contentType": "Text", "content": body},
        "toRecipients": [{"emailAddress": {"address": a}} for a in recipients],
    }
    if size <= INLINE_MAX:
        with open(attachment_path, "rb") as f:
            msg["attachments"] = [{
                "@odata.type": "#microsoft.graph.fileAttachment", "name": name, "contentType": "application/zip",
                "contentBytes": base64.b64encode(f.read()).decode()}]
        _check(requests.post(f"{base}/me/sendMail", headers=h, json={"message": msg, "saveToSentItems": True},
                             timeout=120))
        return
    r = _check(requests.post(f"{base}/me/messages", headers=h, json=msg, timeout=60))
    mid = r.json()["id"]
    try:
        r = _check(requests.post(
            f"{base}/me/messages/{mid}/attachments/createUploadSession", headers=h, timeout=60,
            json={"AttachmentItem": {"attachmentType": "file", "name": name, "size": size,
                                     "contentType": "application/zip"}}))
        url = r.json()["uploadUrl"]
        with open(attachment_path, "rb") as f:
            pos = 0
            while pos < size:
                chunk = f.read(CHUNK)
                end = pos + len(chunk) - 1
                _check(requests.put(url, data=chunk, timeout=300, headers={
                    "Content-Length": str(len(chunk)), "Content-Range": f"bytes {pos}-{end}/{size}"}),
                    ok=(200, 201, 202))  # 上传地址自带授权，不加 Authorization
                pos = end + 1
        _check(requests.post(f"{base}/me/messages/{mid}/send", headers=h, timeout=60))
    except Exception:
        try:
            requests.delete(f"{base}/me/messages/{mid}", headers=h, timeout=30)  # 失败时清理草稿
        except Exception:
            pass
        raise
