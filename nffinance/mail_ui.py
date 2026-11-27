"""月底打包发送：选择文件夹 → 打包 zip → 作为附件发送到指定邮箱（Microsoft 365 登录 或 SMTP）。"""
import os
import tempfile
import threading

from PySide6.QtCore import QDate, QObject, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout,
)

from . import mailer as M
from . import secret
from .paths import get_config, set_config
from .widgets import MonthPicker


class _BG(QObject):
    done = Signal(object, object, object)  # 结果, 异常, 回调


class MailDialog(QDialog):
    def __init__(self, db, tr, parent=None, ym=None):
        super().__init__(parent)
        self.db, self.tr = db, tr
        self._bgs = []
        t = tr
        self.setWindowTitle(t("mail_title"))
        self.resize(660, 780)

        # ---- 通用 ----
        self.folder = QLineEdit()
        btn_browse = QPushButton(t("browse"))
        frow = QHBoxLayout()
        frow.addWidget(self.folder, 1)
        frow.addWidget(btn_browse)
        self.month = MonthPicker()
        if ym:
            self.month.setDate(QDate(ym[0], ym[1], 1))
        self.only_month = QCheckBox(t("mail_only_month"))
        self.to = QLineEdit()
        self.subject = QLineEdit()
        self.body = QPlainTextEdit()
        self.body.setMinimumHeight(130)
        self.method = QComboBox()
        self.method.addItem(t("method_graph"), "graph")
        self.method.addItem(t("method_smtp"), "smtp")
        self.remind = QCheckBox(t("mail_remind"))
        form = QFormLayout()
        form.addRow(t("mail_folder"), frow)
        form.addRow(t("month"), self.month)
        form.addRow("", self.only_month)
        form.addRow(t("mail_to"), self.to)
        form.addRow(t("mail_subject"), self.subject)
        form.addRow(t("mail_body"), self.body)
        form.addRow(t("mail_method"), self.method)

        # ---- Microsoft 365 ----
        self.client_id = QLineEdit()
        self.tenant_id = QLineEdit()
        self.lbl_login = QLabel()
        self.btn_login = QPushButton(t("graph_login"))
        self.btn_logout = QPushButton(t("graph_logout"))
        lrow = QHBoxLayout()
        lrow.addWidget(self.lbl_login, 1)
        lrow.addWidget(self.btn_login)
        lrow.addWidget(self.btn_logout)
        ghint = QLabel(t("graph_hint"))
        ghint.setWordWrap(True)
        ghint.setStyleSheet("color: #999;")
        self.graph_box = QGroupBox("Microsoft 365")
        gform = QFormLayout(self.graph_box)
        gform.addRow(t("graph_client_id"), self.client_id)
        gform.addRow(t("graph_tenant_id"), self.tenant_id)
        gform.addRow("", lrow)
        gform.addRow("", ghint)

        # ---- SMTP ----
        self.sender = QLineEdit()
        self.host = QLineEdit()
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.sec = QComboBox()
        self.sec.addItem(t("sec_ssl"), "ssl")
        self.sec.addItem(t("sec_starttls"), "starttls")
        self.user = QLineEdit()
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        hint = QLabel(t("mail_pw_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #999;")
        self.smtp_box = QGroupBox("SMTP")
        sform = QFormLayout(self.smtp_box)
        sform.addRow(t("mail_from"), self.sender)
        sform.addRow(t("mail_smtp"), self.host)
        sform.addRow(t("mail_port"), self.port)
        sform.addRow(t("mail_security"), self.sec)
        sform.addRow(t("mail_user"), self.user)
        sform.addRow(t("mail_password"), self.pw)
        sform.addRow("", hint)

        self.status = QLabel()
        self.btn_test = QPushButton(t("mail_test"))
        self.btn_zip = QPushButton(t("mail_zip_only"))
        self.btn_save = QPushButton(t("mail_save"))
        self.btn_send = QPushButton(t("mail_send"))
        self.btn_send.setDefault(True)
        btn_close = QPushButton(t("close"))
        row = QHBoxLayout()
        for b in (self.btn_test, self.btn_zip, self.btn_save):
            row.addWidget(b)
        row.addStretch()
        row.addWidget(self.btn_send)
        row.addWidget(btn_close)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.graph_box)
        lay.addWidget(self.smtp_box)
        lay.addWidget(self.remind)
        lay.addWidget(self.status)
        lay.addLayout(row)

        btn_browse.clicked.connect(self.browse)
        self.method.currentIndexChanged.connect(self.on_method)
        self.btn_login.clicked.connect(self.login)
        self.btn_logout.clicked.connect(self.logout)
        self.btn_test.clicked.connect(self.test)
        self.btn_zip.clicked.connect(self.zip_only)
        self.btn_save.clicked.connect(self.save_settings)
        self.btn_send.clicked.connect(self.send)
        btn_close.clicked.connect(self.accept)
        self.load()

    # ---------- 设置读写（密码和令牌缓存只存本机并加密；其余存数据库） ----------
    def load(self):
        g, t = self.db.get_setting, self.tr
        self.folder.setText(g("mail_folder", ""))
        self.only_month.setChecked(g("mail_only_month", "0") == "1")
        self.to.setText(g("mail_to", ""))
        self.subject.setText(g("mail_subject", t("mail_default_subject")))
        self.body.setPlainText(g("mail_body", t("mail_default_body")))
        self.method.setCurrentIndex(0 if g("mail_method", "graph") == "graph" else 1)
        self.client_id.setText(g("mail_graph_client", ""))
        self.tenant_id.setText(g("mail_graph_tenant", ""))
        self.sender.setText(g("mail_from", ""))
        self.host.setText(g("mail_host", ""))
        self.port.setValue(int(g("mail_port", "465")))
        self.sec.setCurrentIndex(0 if g("mail_sec", "ssl") == "ssl" else 1)
        self.user.setText(g("mail_user", ""))
        self.remind.setChecked(g("mail_remind", "0") == "1")
        self.pw.setPlaceholderText(t("mail_pw_saved") if get_config("mail_pw") else "")
        self.show_login_state()
        self.on_method()

    def show_login_state(self):
        u = self.db.get_setting("mail_graph_user", "")
        has_cache = bool(get_config("mail_graph_cache"))
        self.lbl_login.setText(self.tr("graph_signed_in", u=u) if (u and has_cache) else self.tr("graph_not_signed"))

    def on_method(self):
        graph = self.method.currentData() == "graph"
        self.graph_box.setVisible(graph)
        self.smtp_box.setVisible(not graph)

    def save_settings(self):
        s = self.db.set_setting
        s("mail_folder", self.folder.text().strip())
        s("mail_only_month", "1" if self.only_month.isChecked() else "0")
        s("mail_to", self.to.text().strip())
        s("mail_subject", self.subject.text())
        s("mail_body", self.body.toPlainText())
        s("mail_method", self.method.currentData())
        s("mail_graph_client", self.client_id.text().strip())
        s("mail_graph_tenant", self.tenant_id.text().strip())
        s("mail_from", self.sender.text().strip())
        s("mail_host", self.host.text().strip())
        s("mail_port", self.port.value())
        s("mail_sec", self.sec.currentData())
        s("mail_user", self.user.text().strip())
        s("mail_remind", "1" if self.remind.isChecked() else "0")
        if self.pw.text():
            enc = secret.protect(self.pw.text())
            if enc:
                set_config("mail_pw", enc)
                self.pw.clear()
                self.pw.setPlaceholderText(self.tr("mail_pw_saved"))
        self.status.setText(self.tr("saved"))

    def password(self):
        """输入框 → 本机加密保存的密码 → 询问；用户取消返回 None。"""
        if self.pw.text():
            return self.pw.text()
        pw = secret.unprotect(get_config("mail_pw"))
        if pw:
            return pw
        text, ok = QInputDialog.getText(self, self.tr("mail_password"), self.tr("mail_ask_pw"), QLineEdit.Password)
        return text if ok and text else None

    def login_name(self):
        return self.user.text().strip() or self.sender.text().strip()

    # ---------- 后台线程 ----------
    def run_bg(self, fn, cb, busy_text):
        self.set_busy(True, busy_text)
        bg = _BG()
        self._bgs.append(bg)
        bg.done.connect(self._on_bg)  # 绑定方法 → 回到界面线程执行

        def work():
            try:
                bg.done.emit(fn(), None, cb)
            except Exception as e:  # noqa: BLE001
                bg.done.emit(None, e, cb)

        threading.Thread(target=work, daemon=True).start()

    def _on_bg(self, res, err, cb):
        self.set_busy(False, "")
        cb(res, err)

    def set_busy(self, busy, text):
        for b in (self.btn_test, self.btn_zip, self.btn_save, self.btn_send, self.btn_login, self.btn_logout):
            b.setEnabled(not busy)
        self.status.setText(text)

    # ---------- Microsoft 365 登录 ----------
    def _graph_ids(self):
        cid, tid = self.client_id.text().strip(), self.tenant_id.text().strip()
        if not (cid and tid):
            QMessageBox.warning(self, self.tr("mail_title"), self.tr("graph_need_ids"))
            return None
        return cid, tid

    def _graph_job(self, cid, tid, send_args=None):
        """后台：静默刷新令牌，没有登录记录就打开浏览器登录；可选地随后发送邮件。"""
        from . import graph as G
        cache = secret.unprotect(get_config("mail_graph_cache"))
        hint = self.db.get_setting("mail_graph_user", "") or None

        def job():
            auth = G.GraphAuth(cid, tid, cache)
            r = auth.token(interactive=True, login_hint=hint)
            if send_args:
                G.send(r["access_token"], *send_args)
            return auth.username(), auth.cache_text()

        return job

    def _graph_done(self, res):
        user, cache = res
        if cache:
            enc = secret.protect(cache)
            if enc:
                set_config("mail_graph_cache", enc)
        if user:
            self.db.set_setting("mail_graph_user", user)
        self.show_login_state()

    def login(self):
        ids = self._graph_ids()
        if not ids:
            return
        self.save_settings()

        def done(res, err):
            if err:
                QMessageBox.warning(self, self.tr("graph_login"), self.tr("mail_failed") + str(err))
                return
            self._graph_done(res)
            QMessageBox.information(self, self.tr("graph_login"), self.tr("graph_signed_in", u=res[0]))

        self.run_bg(self._graph_job(*ids), done, self.tr("graph_waiting"))

    def logout(self):
        set_config("mail_graph_cache", None)
        self.db.set_setting("mail_graph_user", "")
        self.show_login_state()

    # ---------- 动作 ----------
    def browse(self):
        d = QFileDialog.getExistingDirectory(self, self.tr("mail_folder"), self.folder.text())
        if d:
            self.folder.setText(d)

    def _folder_ok(self):
        if not os.path.isdir(self.folder.text().strip()):
            QMessageBox.warning(self, self.tr("mail_title"), self.tr("mail_need_folder"))
            return False
        return True

    def _ready(self):
        """收件人 + 所选发送方式的必填项。"""
        ok = bool(M.parse_recipients(self.to.text()))
        if self.method.currentData() == "graph":
            if not (self.client_id.text().strip() and self.tenant_id.text().strip()):
                QMessageBox.warning(self, self.tr("mail_title"), self.tr("graph_need_ids"))
                return False
        else:
            ok = ok and bool(self.sender.text().strip() and self.host.text().strip())
        if not ok:
            QMessageBox.warning(self, self.tr("mail_title"), self.tr("mail_need_fields"))
        return ok

    def test(self):
        if self.method.currentData() == "graph":
            self.login()
            return
        if not self.host.text().strip():
            QMessageBox.warning(self, self.tr("mail_title"), self.tr("mail_need_fields"))
            return
        pw = self.password()
        if pw is None:
            return
        args = (self.host.text().strip(), self.port.value(), self.sec.currentData(), self.login_name(), pw)

        def done(_res, err):
            if err:
                QMessageBox.warning(self, self.tr("mail_test"), self.tr("mail_failed") + str(err))
            else:
                QMessageBox.information(self, self.tr("mail_test"), self.tr("mail_test_ok"))

        self.run_bg(lambda: M.test_login(*args), done, self.tr("mail_sending"))

    def _zip(self, dest, cb):
        y, m = self.month.ym()
        only = (y, m) if self.only_month.isChecked() else None
        folder = self.folder.text().strip()
        self.run_bg(lambda: M.make_zip(folder, dest, only), cb, self.tr("mail_zipping"))

    def zip_only(self):
        if not self._folder_ok():
            return
        y, m = self.month.ym()
        dest, _ = QFileDialog.getSaveFileName(self, self.tr("mail_zip_only"), f"NoodleFun_{y}-{m:02d}.zip", "ZIP (*.zip)")
        if not dest:
            return

        def done(res, err):
            if err:
                QMessageBox.warning(self, self.tr("mail_zip_only"), self.tr("mail_failed") + str(err))
            else:
                QMessageBox.information(self, self.tr("mail_zip_only"),
                                        self.tr("mail_zip_saved") + f"{dest}\n{res[0]} ({M.human_size(res[1])})")

        self._zip(dest, done)

    def send(self):
        if not (self._folder_ok() and self._ready()):
            return
        self.save_settings()
        use_graph = self.method.currentData() == "graph"
        pw = None
        if not use_graph:
            pw = self.password()
            if pw is None:
                return
        y, m = self.month.ym()
        tmp = os.path.join(tempfile.mkdtemp(prefix="nff_mail_"), f"NoodleFun_{y}-{m:02d}.zip")

        def after_zip(res, err):
            if err:
                QMessageBox.warning(self, self.tr("mail_title"), self.tr("mail_failed") + str(err))
                return
            count, size, skipped = res
            if count == 0:
                QMessageBox.information(self, self.tr("mail_title"), self.tr("mail_empty"))
                return
            rcpt = M.parse_recipients(self.to.text())
            q = self.tr("mail_confirm", n=count, size=M.human_size(size), to=", ".join(rcpt))
            if skipped:
                q += "\n\n" + self.tr("mail_skipped", n=len(skipped))
            if size > 18 * 1024 * 1024:
                q += "\n\n" + self.tr("mail_big", size=M.human_size(size))
            if QMessageBox.question(self, self.tr("mail_title"), q) != QMessageBox.Yes:
                return
            subject = M.fill(self.subject.text(), y, m, count, M.human_size(size))
            body = M.fill(self.body.toPlainText(), y, m, count, M.human_size(size))

            def after_send(r, e):
                if e:
                    QMessageBox.warning(self, self.tr("mail_title"), self.tr("mail_failed") + str(e))
                    return
                if use_graph:
                    self._graph_done(r)
                self.db.set_setting("mail_last_sent", f"{y}-{m:02d}")
                QMessageBox.information(self, self.tr("mail_title"), self.tr("mail_sent_ok") + ", ".join(rcpt))

            if use_graph:
                cid, tid = self.client_id.text().strip(), self.tenant_id.text().strip()
                job = self._graph_job(cid, tid, (rcpt, subject, body, tmp))
                self.run_bg(job, after_send, self.tr("graph_waiting"))
            else:
                args = (self.host.text().strip(), self.port.value(), self.sec.currentData(), self.login_name(), pw,
                        self.sender.text().strip(), rcpt, subject, body, tmp)
                self.run_bg(lambda: M.send_mail(*args), after_send, self.tr("mail_sending"))

        self._zip(tmp, after_zip)
