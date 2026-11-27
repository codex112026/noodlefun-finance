"""月底打包发送：选择文件夹 → 打包 zip → 作为附件发送到指定邮箱。"""
import os
import tempfile
import threading

from PySide6.QtCore import QDate, QObject, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout,
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
        self.resize(640, 700)

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
        self.sender = QLineEdit()
        self.subject = QLineEdit()
        self.body = QPlainTextEdit()
        self.body.setMinimumHeight(150)
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
        self.remind = QCheckBox(t("mail_remind"))

        form = QFormLayout()
        form.addRow(t("mail_folder"), frow)
        form.addRow(t("month"), self.month)
        form.addRow("", self.only_month)
        form.addRow(t("mail_to"), self.to)
        form.addRow(t("mail_from"), self.sender)
        form.addRow(t("mail_subject"), self.subject)
        form.addRow(t("mail_body"), self.body)
        form.addRow(t("mail_smtp"), self.host)
        form.addRow(t("mail_port"), self.port)
        form.addRow(t("mail_security"), self.sec)
        form.addRow(t("mail_user"), self.user)
        form.addRow(t("mail_password"), self.pw)
        form.addRow("", hint)
        form.addRow("", self.remind)

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
        lay.addWidget(self.status)
        lay.addLayout(row)

        btn_browse.clicked.connect(self.browse)
        self.btn_test.clicked.connect(self.test)
        self.btn_zip.clicked.connect(self.zip_only)
        self.btn_save.clicked.connect(self.save_settings)
        self.btn_send.clicked.connect(self.send)
        btn_close.clicked.connect(self.accept)
        self.load()

    # ---------- 设置读写（密码以外存数据库；密码 DPAPI 加密存本机） ----------
    def load(self):
        g, t = self.db.get_setting, self.tr
        self.folder.setText(g("mail_folder", ""))
        self.only_month.setChecked(g("mail_only_month", "0") == "1")
        self.to.setText(g("mail_to", ""))
        self.sender.setText(g("mail_from", ""))
        self.subject.setText(g("mail_subject", t("mail_default_subject")))
        self.body.setPlainText(g("mail_body", t("mail_default_body")))
        self.host.setText(g("mail_host", ""))
        self.port.setValue(int(g("mail_port", "465")))
        self.sec.setCurrentIndex(0 if g("mail_sec", "ssl") == "ssl" else 1)
        self.user.setText(g("mail_user", ""))
        self.remind.setChecked(g("mail_remind", "0") == "1")
        self.pw.setPlaceholderText(t("mail_pw_saved") if get_config("mail_pw") else "")

    def save_settings(self):
        s = self.db.set_setting
        s("mail_folder", self.folder.text().strip())
        s("mail_only_month", "1" if self.only_month.isChecked() else "0")
        s("mail_to", self.to.text().strip())
        s("mail_from", self.sender.text().strip())
        s("mail_subject", self.subject.text())
        s("mail_body", self.body.toPlainText())
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
        for b in (self.btn_test, self.btn_zip, self.btn_save, self.btn_send):
            b.setEnabled(not busy)
        self.status.setText(text)

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

    def _smtp_ok(self):
        if not (M.parse_recipients(self.to.text()) and self.sender.text().strip() and self.host.text().strip()):
            QMessageBox.warning(self, self.tr("mail_title"), self.tr("mail_need_fields"))
            return False
        return True

    def test(self):
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
        if not (self._folder_ok() and self._smtp_ok()):
            return
        self.save_settings()
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
            args = (self.host.text().strip(), self.port.value(), self.sec.currentData(), self.login_name(), pw,
                    self.sender.text().strip(), rcpt, subject, body, tmp)

            def after_send(_r, e):
                if e:
                    QMessageBox.warning(self, self.tr("mail_title"), self.tr("mail_failed") + str(e))
                    return
                self.db.set_setting("mail_last_sent", f"{y}-{m:02d}")
                QMessageBox.information(self, self.tr("mail_title"), self.tr("mail_sent_ok") + ", ".join(rcpt))

            self.run_bg(lambda: M.send_mail(*args), after_send, self.tr("mail_sending"))

        self._zip(tmp, after_zip)
