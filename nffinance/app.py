import os
import sys
import threading
from datetime import date as _date

from PySide6.QtCore import QDate, QLocale, Qt, QObject, Signal, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDateEdit, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox,
    QProgressDialog, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from . import report, updater
from .db import CHANNELS, Database
from .i18n import LANGS, Translator, fmt_eur
from pathlib import Path

from .paths import configured_data_dir, default_data_dir, resource_path, save_data_dir
from .version import __version__

GERMAN = QLocale(QLocale.German, QLocale.Austria)


class MoneyEdit(QDoubleSpinBox):
    def __init__(self):
        super().__init__()
        self.setLocale(GERMAN)
        self.setDecimals(2)
        self.setRange(0, 10_000_000)
        self.setSingleStep(10)
        self.setSuffix(" €")
        self.setAlignment(Qt.AlignRight)
        self.setGroupSeparatorShown(False)
        self.setMinimumWidth(140)

    def cents(self) -> int:
        return int(round(self.value() * 100))

    def set_cents(self, c: int):
        self.setValue(c / 100)


class MonthPicker(QDateEdit):
    def __init__(self):
        super().__init__(QDate.currentDate())
        self.setDisplayFormat("MM / yyyy")
        self.setCalendarPopup(True)

    def ym(self):
        d = self.date()
        return d.year(), d.month()


def make_table(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.verticalHeader().setVisible(False)
    t.setAlternatingRowColors(True)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    return t


def cell(text, right=False, bold=False):
    it = QTableWidgetItem(text)
    if right:
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if bold:
        f = it.font()
        f.setBold(True)
        it.setFont(f)
    return it


def qd(d: _date) -> QDate:
    return QDate(d.year, d.month, d.day)


def iso(qdate: QDate) -> str:
    return qdate.toString("yyyy-MM-dd")


# ---------------------------------------------------------------- 营业额
class RevenueTab(QWidget):
    changed = Signal()

    def __init__(self, db, tr):
        super().__init__()
        self.db, self.tr = db, tr
        t = tr
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd.MM.yyyy")
        self.edits = {c: MoneyEdit() for c in CHANNELS}
        self.total = QLabel("0,00 €")
        f = self.total.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 3)
        self.total.setFont(f)
        self.note = QLineEdit()
        form = QFormLayout()
        form.addRow(t("date"), self.date)
        for c in CHANNELS:
            form.addRow(t(c), self.edits[c])
        form.addRow(t("total"), self.total)
        form.addRow(t("note"), self.note)
        self.btn_save = QPushButton(t("save"))
        self.btn_del = QPushButton(t("delete"))
        btns = QHBoxLayout()
        btns.addWidget(self.btn_save)
        btns.addWidget(self.btn_del)
        btns.addStretch()
        box = QGroupBox(t("tab_revenue"))
        lay = QVBoxLayout(box)
        lay.addLayout(form)
        lay.addLayout(btns)

        self.table = make_table([t("date")] + [t(c) for c in CHANNELS] + [t("total")])
        top = QHBoxLayout()
        top.addWidget(box)
        top.addStretch()
        main = QVBoxLayout(self)
        main.addLayout(top)
        main.addWidget(QLabel(t("month_entries")))
        main.addWidget(self.table, 1)

        self.date.dateChanged.connect(self.on_date)
        for e in self.edits.values():
            e.valueChanged.connect(self.update_total)
        self.btn_save.clicked.connect(self.save)
        self.btn_del.clicked.connect(self.delete)
        self.table.cellClicked.connect(self.pick_row)
        self._month = None
        self.on_date()

    def update_total(self):
        self.total.setText(fmt_eur(sum(e.cents() for e in self.edits.values())))

    def on_date(self):
        r = self.db.get_revenue(iso(self.date.date()))
        for c in CHANNELS:
            self.edits[c].set_cents(r[c] if r else 0)
        self.note.setText(r["note"] if r else "")
        self.update_total()
        d = self.date.date()
        if self._month != (d.year(), d.month()):
            self.reload()

    def reload(self):
        d = self.date.date()
        self._month = (d.year(), d.month())
        rows = self.db.revenues_in_month(d.year(), d.month())
        self.table.setRowCount(0)
        for r in rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            self.table.setItem(i, 0, cell(_date.fromisoformat(r["date"]).strftime("%d.%m.%Y")))
            self.table.item(i, 0).setData(Qt.UserRole, r["date"])
            for j, c in enumerate(CHANNELS, 1):
                self.table.setItem(i, j, cell(fmt_eur(r[c]), right=True))
            self.table.setItem(i, 6, cell(fmt_eur(sum(r[c] for c in CHANNELS)), right=True, bold=True))

    def pick_row(self, row, _col):
        d = _date.fromisoformat(self.table.item(row, 0).data(Qt.UserRole))
        self.date.setDate(qd(d))

    def save(self):
        self.db.save_revenue(iso(self.date.date()), {c: e.cents() for c, e in self.edits.items()}, self.note.text())
        self.reload()
        self.changed.emit()
        self.window().statusBar().showMessage(self.tr("saved"), 3000)

    def delete(self):
        if QMessageBox.question(self, self.tr("delete"), self.tr("confirm_delete")) == QMessageBox.Yes:
            self.db.delete_revenue(iso(self.date.date()))
            self.on_date()
            self.reload()
            self.changed.emit()


# ---------------------------------------------------------------- 支出
class CategoryDialog(QDialog):
    def __init__(self, db, tr, parent=None):
        super().__init__(parent)
        self.db, self.tr = db, tr
        self.setWindowTitle(tr("manage_categories"))
        self.list = QListWidget()
        add = QPushButton(tr("add"))
        rem = QPushButton(tr("remove"))
        close = QPushButton(tr("close"))
        row = QHBoxLayout()
        row.addWidget(add)
        row.addWidget(rem)
        row.addStretch()
        row.addWidget(close)
        lay = QVBoxLayout(self)
        lay.addWidget(self.list)
        lay.addLayout(row)
        add.clicked.connect(self.add)
        rem.clicked.connect(self.remove)
        close.clicked.connect(self.accept)
        self.refresh()

    def refresh(self):
        self.list.clear()
        self.list.addItems(self.db.categories())

    def add(self):
        name, ok = QInputDialog.getText(self, self.tr("add"), self.tr("new_category"))
        if ok and not self.db.add_category(name):
            QMessageBox.warning(self, self.tr("add"), self.tr("category_exists"))
        self.refresh()

    def remove(self):
        it = self.list.currentItem()
        if it:
            self.db.remove_category(it.text())
            self.refresh()


class ExpenseTab(QWidget):
    changed = Signal()

    def __init__(self, db, tr):
        super().__init__()
        self.db, self.tr = db, tr
        t = tr
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd.MM.yyyy")
        self.cat = QComboBox()
        self.cat.setMinimumWidth(180)
        self.btn_cat = QPushButton(t("manage_categories"))
        self.amount = MoneyEdit()
        self.note = QLineEdit()
        self.btn_add = QPushButton(t("add"))
        form = QFormLayout()
        form.addRow(t("date"), self.date)
        row = QHBoxLayout()
        row.addWidget(self.cat)
        row.addWidget(self.btn_cat)
        form.addRow(t("category"), row)
        form.addRow(t("amount"), self.amount)
        form.addRow(t("note"), self.note)
        box = QGroupBox(t("tab_expense"))
        lay = QVBoxLayout(box)
        lay.addLayout(form)
        lay.addWidget(self.btn_add)

        self.month = MonthPicker()
        self.table = make_table([t("date"), t("category"), t("note"), t("amount")])
        self.btn_del = QPushButton(t("remove"))
        self.lbl_total = QLabel()
        bar = QHBoxLayout()
        bar.addWidget(QLabel(t("month")))
        bar.addWidget(self.month)
        bar.addStretch()
        bar.addWidget(self.lbl_total)
        top = QHBoxLayout()
        top.addWidget(box)
        top.addStretch()
        main = QVBoxLayout(self)
        main.addLayout(top)
        main.addLayout(bar)
        main.addWidget(self.table, 1)
        main.addWidget(self.btn_del, 0, Qt.AlignLeft)

        self.btn_cat.clicked.connect(self.manage)
        self.btn_add.clicked.connect(self.add)
        self.btn_del.clicked.connect(self.remove)
        self.month.dateChanged.connect(self.reload)
        self.refresh_categories()
        self.reload()

    def refresh_categories(self):
        cur = self.cat.currentText()
        self.cat.clear()
        self.cat.addItems(self.db.categories())
        if cur:
            self.cat.setCurrentText(cur)

    def manage(self):
        CategoryDialog(self.db, self.tr, self).exec()
        self.refresh_categories()

    def add(self):
        if not self.cat.currentText():
            QMessageBox.information(self, self.tr("add"), self.tr("need_category"))
            return
        if self.amount.cents() <= 0:
            return
        self.db.add_expense(iso(self.date.date()), self.cat.currentText(), self.amount.cents(), self.note.text())
        self.amount.setValue(0)
        self.note.clear()
        d = self.date.date()
        self.month.setDate(d)
        self.reload()
        self.changed.emit()
        self.window().statusBar().showMessage(self.tr("saved"), 3000)

    def remove(self):
        row = self.table.currentRow()
        if row < 0:
            return
        if QMessageBox.question(self, self.tr("delete"), self.tr("confirm_delete")) == QMessageBox.Yes:
            self.db.delete_expense(self.table.item(row, 0).data(Qt.UserRole))
            self.reload()
            self.changed.emit()

    def reload(self):
        y, m = self.month.ym()
        rows = self.db.expenses_in_month(y, m)
        self.table.setRowCount(0)
        for r in rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            it = cell(_date.fromisoformat(r["date"]).strftime("%d.%m.%Y"))
            it.setData(Qt.UserRole, r["id"])
            self.table.setItem(i, 0, it)
            self.table.setItem(i, 1, cell(r["category"]))
            self.table.setItem(i, 2, cell(r["note"]))
            self.table.setItem(i, 3, cell(fmt_eur(r["amount"]), right=True))
        self.lbl_total.setText(f"{self.tr('total_expenses')}: {fmt_eur(sum(r['amount'] for r in rows))}")


# ---------------------------------------------------------------- 汇总
class SummaryTab(QWidget):
    def __init__(self, db, tr):
        super().__init__()
        self.db, self.tr = db, tr
        t = tr
        self.month = MonthPicker()
        self.t_ch = make_table([t("channel"), t("amount")])
        self.t_cat = make_table([t("category"), t("amount")])
        self.lbl_bal = QLabel()
        f = self.lbl_bal.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 4)
        self.lbl_bal.setFont(f)
        self.btn_month = QPushButton(t("export_monthly"))
        self.day = QDateEdit(QDate.currentDate())
        self.day.setCalendarPopup(True)
        self.day.setDisplayFormat("dd.MM.yyyy")
        self.btn_day = QPushButton(t("export_daily"))

        bar = QHBoxLayout()
        bar.addWidget(QLabel(t("month")))
        bar.addWidget(self.month)
        bar.addWidget(self.btn_month)
        bar.addStretch()
        bar.addWidget(QLabel(t("daily_report_date")))
        bar.addWidget(self.day)
        bar.addWidget(self.btn_day)
        tables = QHBoxLayout()
        for title, tb in ((t("by_channel"), self.t_ch), (t("by_category"), self.t_cat)):
            col = QVBoxLayout()
            col.addWidget(QLabel(title))
            col.addWidget(tb)
            tables.addLayout(col)
        main = QVBoxLayout(self)
        main.addLayout(bar)
        main.addLayout(tables, 1)
        main.addWidget(self.lbl_bal, 0, Qt.AlignRight)

        self.month.dateChanged.connect(self.reload)
        self.btn_month.clicked.connect(self.export_month)
        self.btn_day.clicked.connect(self.export_day)
        self.reload()

    def reload(self):
        y, m = self.month.ym()
        rows = self.db.revenues_in_month(y, m)
        exps = self.db.expenses_in_month(y, m)
        tot = {c: sum(r[c] for r in rows) for c in CHANNELS}
        income = sum(tot.values())
        self.t_ch.setRowCount(0)
        for c in CHANNELS:
            i = self.t_ch.rowCount()
            self.t_ch.insertRow(i)
            self.t_ch.setItem(i, 0, cell(self.tr(c)))
            self.t_ch.setItem(i, 1, cell(fmt_eur(tot[c]), right=True))
        i = self.t_ch.rowCount()
        self.t_ch.insertRow(i)
        self.t_ch.setItem(i, 0, cell(self.tr("total_income"), bold=True))
        self.t_ch.setItem(i, 1, cell(fmt_eur(income), right=True, bold=True))
        cats = report._cat_totals(exps)
        self.t_cat.setRowCount(0)
        for k, v in cats.items():
            i = self.t_cat.rowCount()
            self.t_cat.insertRow(i)
            self.t_cat.setItem(i, 0, cell(k))
            self.t_cat.setItem(i, 1, cell(fmt_eur(v), right=True))
        i = self.t_cat.rowCount()
        self.t_cat.insertRow(i)
        self.t_cat.setItem(i, 0, cell(self.tr("total_expenses"), bold=True))
        self.t_cat.setItem(i, 1, cell(fmt_eur(sum(cats.values())), right=True, bold=True))
        self.lbl_bal.setText(f"{self.tr('balance')}: {fmt_eur(income - sum(cats.values()))}")

    def _ask_path(self, default):
        path, _ = QFileDialog.getSaveFileName(self, self.tr("export_monthly"), default, self.tr("pdf_filter"))
        return path

    def _done(self, path):
        box = QMessageBox.question(self, "PDF", self.tr("pdf_saved") + path + "\n\n" + self.tr("pdf_open"))
        if box == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def export_month(self):
        y, m = self.month.ym()
        path = self._ask_path(os.path.join(os.path.expanduser("~"), "Documents", f"NoodleFun_{y}-{m:02d}.pdf"))
        if not path:
            return
        try:
            report.build_monthly(path, self.db, y, m, self.tr)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "PDF", self.tr("pdf_error") + str(e))
            return
        self._done(path)

    def export_day(self):
        d = iso(self.day.date())
        path = self._ask_path(os.path.join(os.path.expanduser("~"), "Documents", f"NoodleFun_{d}.pdf"))
        if not path:
            return
        try:
            report.build_daily(path, self.db, d, self.tr)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "PDF", self.tr("pdf_error") + str(e))
            return
        self._done(path)


# ---------------------------------------------------------------- 更新
class UpdateSignals(QObject):
    found = Signal(object)    # info dict 或 None
    failed = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.tr = Translator(db.get_setting("lang", "zh"))
        self.sig = UpdateSignals()
        self.sig.found.connect(self.on_update_result)
        self.sig.failed.connect(self.on_update_error)
        self._manual = False
        self.setWindowIcon(QIcon(str(resource_path("assets/icon.ico"))))
        self.resize(1000, 700)
        self.build()

    # 切换语言时整体重建界面
    def build(self):
        t = self.tr
        self.setWindowTitle(f"{t('app_title')}  v{__version__}")
        tabs = QTabWidget()
        self.rev = RevenueTab(self.db, t)
        self.exp = ExpenseTab(self.db, t)
        self.sumt = SummaryTab(self.db, t)
        tabs.addTab(self.rev, t("tab_revenue"))
        tabs.addTab(self.exp, t("tab_expense"))
        tabs.addTab(self.sumt, t("tab_summary"))
        tabs.currentChanged.connect(lambda _i: (self.sumt.reload(), self.exp.refresh_categories()))
        self.rev.changed.connect(self.sumt.reload)
        self.exp.changed.connect(self.sumt.reload)
        self.setCentralWidget(tabs)
        self.build_menu()

    def build_menu(self):
        t = self.tr
        mb = self.menuBar()
        mb.clear()
        m = mb.addMenu(t("menu_file"))
        a = QAction(t("backup"), self, triggered=self.backup)
        m.addAction(a)
        m.addAction(QAction(t("open_data_dir"), self, triggered=lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.db.path.parent)))))
        m.addAction(QAction(t("change_data_dir"), self, triggered=self.change_data_dir))
        m.addSeparator()
        m.addAction(QAction(t("quit"), self, triggered=self.close))
        lm = mb.addMenu(t("menu_language"))
        for code, name in LANGS.items():
            act = QAction(name, self, checkable=True, checked=(code == t.lang))
            act.triggered.connect(lambda _=False, c=code: self.set_lang(c))
            lm.addAction(act)
        hm = mb.addMenu(t("menu_help"))
        hm.addAction(QAction(t("check_update"), self, triggered=lambda: self.check_update(manual=True)))
        hm.addAction(QAction(t("about"), self, triggered=lambda: QMessageBox.information(
            self, t("about"), t("about_text", v=__version__, p=str(self.db.path)))))

    def set_lang(self, code):
        self.db.set_setting("lang", code)
        self.tr = Translator(code)
        self.build()

    def change_data_dir(self):
        t = self.tr
        cur = self.db.path.parent
        d = QFileDialog.getExistingDirectory(self, t("choose_data_dir_title"), str(cur))
        if not d or Path(d) == cur:
            return
        target = Path(d) / "finance.db"
        try:
            if target.exists():
                QMessageBox.information(self, t("change_data_dir"), t("data_dir_found", p=d) + "\n\n" + t("data_dir_sync_hint"))
            else:
                if QMessageBox.question(self, t("change_data_dir"), t("data_dir_copy", p=d) + "\n\n" + t("data_dir_sync_hint")) != QMessageBox.Yes:
                    return
                self.db.backup_to(str(target))
            new_db = Database(target)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, t("change_data_dir"), t("data_dir_error") + str(e))
            return
        old = self.db
        self.db = new_db
        save_data_dir(d)
        old.close()
        self.tr = Translator(new_db.get_setting("lang", "zh"))  # 语言等设置随数据文件夹一起恢复
        self.build()
        self.statusBar().showMessage(self.tr("data_dir_switched") + d, 6000)

    def backup(self):
        path, _ = QFileDialog.getSaveFileName(self, self.tr("backup"), "NoodleFun_backup.db", "SQLite (*.db)")
        if path:
            self.db.backup_to(path)
            QMessageBox.information(self, self.tr("backup"), self.tr("backup_done") + path)

    # ---- 自动更新 ----
    def check_update(self, manual=False):
        self._manual = manual
        if not updater.repo_configured():
            if manual:
                QMessageBox.information(self, self.tr("check_update"), self.tr("update_repo_unset"))
            return

        def work():
            try:
                self.sig.found.emit(updater.check_latest())
            except Exception as e:  # noqa: BLE001
                self.sig.failed.emit(str(e))

        threading.Thread(target=work, daemon=True).start()

    def on_update_error(self, msg):
        if self._manual:
            QMessageBox.warning(self, self.tr("check_update"), self.tr("update_failed") + msg)

    def on_update_result(self, info):
        if not info:
            if self._manual:
                QMessageBox.information(self, self.tr("check_update"), self.tr("update_none"))
            return
        q = QMessageBox.question(self, self.tr("check_update"),
                                 self.tr("update_available", new=info["version"], cur=__version__))
        if q != QMessageBox.Yes:
            return
        dlg = QProgressDialog(self.tr("downloading"), self.tr("cancel"), 0, 100, self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.show()

        def prog(got, total):
            if total:
                dlg.setValue(int(got * 100 / total))
            QApplication.processEvents()

        try:
            path = updater.download(info, prog, dlg.wasCanceled)
        except Exception as e:  # noqa: BLE001
            dlg.close()
            if str(e) != "cancelled":
                QMessageBox.warning(self, self.tr("check_update"), self.tr("update_failed") + str(e))
            return
        dlg.close()
        self.db.conn.commit()
        updater.run_installer(path)
        QApplication.quit()


def open_database() -> Database:
    """首次运行让用户选择数据文件夹；重装后选回原文件夹即可恢复全部数据与设置。"""
    tr = Translator("zh")
    d = configured_data_dir()
    if d is None:
        if (default_data_dir() / "finance.db").exists():  # 旧版本已有数据：继续使用
            d = default_data_dir()
        else:
            QMessageBox.information(None, tr("choose_data_dir_title"), tr("first_run_msg"))
            chosen = QFileDialog.getExistingDirectory(None, tr("choose_data_dir_title"))
            d = Path(chosen) if chosen else default_data_dir()
        save_data_dir(d)
    while True:
        try:
            db = Database(Path(d) / "finance.db")
            return db
        except Exception as e:  # noqa: BLE001  例如 OneDrive 文件夹暂时不可用
            QMessageBox.warning(None, tr("choose_data_dir_title"), f"{tr('data_dir_error')}\n{d}\n{e}")
            chosen = QFileDialog.getExistingDirectory(None, tr("choose_data_dir_title"))
            d = Path(chosen) if chosen else default_data_dir()
            save_data_dir(d)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    db = open_database()
    w = MainWindow(db)
    w.show()
    if "--no-update-check" not in sys.argv:
        w.check_update(manual=False)  # 启动时静默检查
    sys.exit(app.exec())
