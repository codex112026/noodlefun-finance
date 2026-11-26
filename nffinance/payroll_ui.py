"""工资结算页：工人档案、每日工时录入、月度计算、PDF 导出。"""
import os
from datetime import date as _date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDate, QRegularExpression, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from . import payroll as P
from . import payroll_report
from .i18n import fmt_eur
from .widgets import DateDelegate, MoneyEdit, MonthPicker, NavCombo, NavDateEdit, _commit, cell, iso, link_enter, make_table


def _validator(parent, pattern):
    return QRegularExpressionValidator(QRegularExpression(pattern), parent)


class TimeEdit(QLineEdit):
    """时间输入：9、930、9:30、0930 都可以，离开后自动整理成 HH:MM。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMaximumWidth(90)
        self.setValidator(_validator(self, r"^\d{0,2}:?\d{0,2}$"))
        self.editingFinished.connect(self._tidy)

    def minutes(self):
        return P.parse_hhmm(self.text())

    def set_minutes(self, m):
        self.setText("" if m is None else P.fmt_hhmm(m))

    def _tidy(self):
        m = self.minutes()
        if m is not None:
            self.set_minutes(m)


class IntEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignRight)
        self.setMaximumWidth(90)
        self.setValidator(_validator(self, r"^\d{0,3}$"))

    def value(self) -> int:
        return int(self.text() or 0)

    def set_value(self, v):
        self.setText("" if not v else str(int(v)))


class DecimalEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignRight)
        self.setMaximumWidth(90)
        self.setValidator(_validator(self, r"^\d{0,2}([.,]\d{0,2})?$"))

    def value(self) -> Decimal:
        try:
            return Decimal(self.text().replace(",", ".") or "0")
        except InvalidOperation:
            return Decimal(0)

    def set_value(self, v):
        d = Decimal(str(v))
        self.setText(str(int(d)) if d == d.to_integral() else str(d).replace(".", ","))


class HoursEdit(QLineEdit):
    """小时数输入（如 173,2）；内部以分钟保存。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignRight)
        self.setValidator(_validator(self, r"^\d{0,3}([.,]\d{0,2})?$"))

    def minutes(self) -> int:
        try:
            return int((Decimal(self.text().replace(",", ".") or "0") * 60).quantize(Decimal(1)))
        except InvalidOperation:
            return 0

    def set_minutes(self, m: int):
        s = f"{Decimal(m) / 60:.2f}".rstrip("0").rstrip(".") if m else ""
        self.setText(s.replace(".", ","))


class TimeDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        return TimeEdit(parent)

    def setEditorData(self, editor, index):
        editor.set_minutes(index.data(Qt.UserRole))
        editor.selectAll()

    def setModelData(self, editor, model, index):
        m = editor.minutes()
        if m is not None:
            _commit(model, index, P.fmt_hhmm(m), m)


class IntDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        return IntEdit(parent)

    def setEditorData(self, editor, index):
        editor.set_value(index.data(Qt.UserRole) or 0)
        editor.selectAll()

    def setModelData(self, editor, model, index):
        v = editor.value()
        _commit(model, index, str(v), v)


# ---------------------------------------------------------------- 工人管理
class WorkerDialog(QDialog):
    def __init__(self, db, tr, parent=None):
        super().__init__(parent)
        self.db, self.tr = db, tr
        self.current_id = None
        t = tr
        self.setWindowTitle(t("manage_workers"))
        self.resize(760, 460)
        self.list = QListWidget()
        self.list.setMaximumWidth(200)
        self.name = QLineEdit()
        self.salary = MoneyEdit()
        self.method = QComboBox()
        self.method.addItem(t("method_rough"), "rough")
        self.method.addItem(t("method_at"), "at")
        self.rest = IntEdit()
        self.daily = DecimalEdit()
        self.weekly = DecimalEdit()
        self.btn_calc = QPushButton(t("calc_rate"))
        self.formula = QLabel()
        self.formula.setWordWrap(True)
        self.hourly = MoneyEdit()
        self.cap = MoneyEdit()
        self.ot_mult = DecimalEdit()
        self.status = QComboBox()
        self.status.addItem(t("status_active"), 1)
        self.status.addItem(t("status_left"), 0)
        form = QFormLayout()
        form.addRow(t("worker_name"), self.name)
        form.addRow(t("monthly_salary"), self.salary)
        form.addRow(t("method"), self.method)
        form.addRow(t("rest_days"), self.rest)
        form.addRow(t("daily_hours"), self.daily)
        form.addRow(t("weekly_hours"), self.weekly)
        form.addRow("", self.btn_calc)
        form.addRow("", self.formula)
        form.addRow(t("hourly_rate"), self.hourly)
        form.addRow(t("monthly_cap"), self.cap)
        form.addRow(t("ot_mult"), self.ot_mult)
        form.addRow(t("status"), self.status)
        b_new, b_save, b_del, b_close = (QPushButton(t(k)) for k in ("new", "save_worker", "delete", "close"))
        row = QHBoxLayout()
        for b in (b_new, b_save, b_del):
            row.addWidget(b)
        row.addStretch()
        row.addWidget(b_close)
        right = QVBoxLayout()
        right.addLayout(form)
        right.addStretch()
        right.addLayout(row)
        lay = QHBoxLayout(self)
        lay.addWidget(self.list)
        lay.addLayout(right, 1)

        self.list.currentItemChanged.connect(self.on_pick)
        self.method.currentIndexChanged.connect(self.on_method)
        self.btn_calc.clicked.connect(self.calc)
        b_new.clicked.connect(self.clear_form)
        b_save.clicked.connect(self.save)
        b_del.clicked.connect(self.delete)
        b_close.clicked.connect(self.accept)
        self.refresh_list()
        self.clear_form()

    def on_method(self):
        rough = self.method.currentData() == "rough"
        self.rest.setEnabled(rough)
        self.daily.setEnabled(rough)
        self.weekly.setEnabled(not rough)

    def refresh_list(self, select_id=None):
        self.list.blockSignals(True)
        self.list.clear()
        for w in self.db.workers():
            it = QListWidgetItem(w["name"] + ("" if w["active"] else f"  ({self.tr('status_left')})"))
            it.setData(Qt.UserRole, w["id"])
            self.list.addItem(it)
            if w["id"] == select_id:
                self.list.setCurrentItem(it)
        self.list.blockSignals(False)

    def clear_form(self):
        self.list.blockSignals(True)
        self.list.clearSelection()
        self.list.setCurrentItem(None)
        self.list.blockSignals(False)
        self.current_id = None
        self.name.clear()
        self.salary.clear()
        self.method.setCurrentIndex(0)
        self.rest.set_value(8)
        self.daily.set_value(8)
        self.weekly.set_value(40)
        self.hourly.clear()
        self.cap.clear()
        self.ot_mult.set_value("1.5")
        self.status.setCurrentIndex(0)
        self.formula.clear()
        self.on_method()
        self.name.setFocus()

    def on_pick(self, item, _prev=None):
        if item is None:
            return
        w = self.db.get_worker(item.data(Qt.UserRole))
        if not w:
            return
        self.current_id = w["id"]
        self.name.setText(w["name"])
        self.salary.set_cents(w["salary"])
        self.method.setCurrentIndex(0 if w["method"] == "rough" else 1)
        self.rest.set_value(w["rest_days"])
        self.daily.set_value(w["daily_hours"])
        self.weekly.set_value(w["weekly_hours"])
        self.hourly.set_cents(w["hourly"])
        self.cap.set_cents(w["cap"])
        self.ot_mult.set_value(w["ot_mult"])
        self.status.setCurrentIndex(0 if w["active"] else 1)
        self.formula.clear()
        self.on_method()

    def calc(self):
        r = P.hourly_from_salary(self.method.currentData(), self.salary.cents(), self.rest.value(),
                                 self.daily.value(), self.weekly.value())
        if r is None:
            QMessageBox.information(self, self.tr("calc_rate"), self.tr("need_salary"))
            return
        self.hourly.set_cents(r[0])
        self.formula.setText(r[1])

    def save(self):
        data = {
            "name": self.name.text(), "hourly": self.hourly.cents(), "cap": self.cap.cents(),
            "salary": self.salary.cents(), "method": self.method.currentData(), "rest_days": self.rest.value(),
            "daily_hours": float(self.daily.value()), "weekly_hours": float(self.weekly.value()),
            "ot_mult": float(self.ot_mult.value() or 1), "active": self.status.currentData(),
        }
        wid = self.db.save_worker(data, self.current_id)
        if wid is None:
            QMessageBox.warning(self, self.tr("manage_workers"), self.tr("worker_exists"))
            return
        self.current_id = wid
        self.refresh_list(wid)

    def delete(self):
        if self.current_id is None:
            return
        if QMessageBox.question(self, self.tr("delete"), self.tr("confirm_delete_worker")) == QMessageBox.Yes:
            self.db.delete_worker(self.current_id)
            self.refresh_list()
            self.clear_form()


# ---------------------------------------------------------------- 工资结算页
class PayrollTab(QWidget):
    def __init__(self, db, tr):
        super().__init__()
        self.db, self.tr = db, tr
        self._loading = False
        t = tr
        self.worker = NavCombo()
        self.worker.setMinimumWidth(160)
        self.btn_workers = QPushButton(t("manage_workers"))
        self.month = MonthPicker()
        bar = QHBoxLayout()
        bar.addWidget(QLabel(t("worker")))
        bar.addWidget(self.worker)
        bar.addWidget(self.btn_workers)
        bar.addSpacing(20)
        bar.addWidget(QLabel(t("month")))
        bar.addWidget(self.month)
        bar.addStretch()

        # 工时录入
        self.date = NavDateEdit()
        self.start, self.end = TimeEdit(), TimeEdit()
        self.brk = IntEdit()
        self.btn_add = QPushButton(t("add"))
        entry = QHBoxLayout()
        for label, w in ((t("date"), self.date), (t("start_time"), self.start), (t("end_time"), self.end),
                         (t("break_min"), self.brk)):
            entry.addWidget(QLabel(label))
            entry.addWidget(w)
        entry.addWidget(self.btn_add)
        entry.addStretch()
        self.entry_box = QGroupBox(t("entries_month").split("（")[0].split(" (")[0])
        QVBoxLayout(self.entry_box).addLayout(entry)
        box = self.entry_box

        self.table = make_table([t("date"), t("start_time"), t("end_time"), t("break_min"), t("hours")],
                                editable=True)
        self.table.setItemDelegateForColumn(0, DateDelegate(self.table))
        self.table.setItemDelegateForColumn(1, TimeDelegate(self.table))
        self.table.setItemDelegateForColumn(2, TimeDelegate(self.table))
        self.table.setItemDelegateForColumn(3, IntDelegate(self.table))
        self.btn_del = QPushButton(t("remove"))
        left = QVBoxLayout()
        left.addWidget(box)
        left.addWidget(QLabel(t("entries_month")))
        left.addWidget(self.table, 1)
        left.addWidget(self.btn_del, 0, Qt.AlignLeft)

        # 结算面板
        self.mode = NavCombo()
        self.mode.addItem(t("mode_daily"), "daily")
        self.mode.addItem(t("mode_total"), "total")
        self.total_hours, self.ot_hours = HoursEdit(), HoursEdit()
        self.overtime = MoneyEdit()
        self.transfer, self.cash = MoneyEdit(), MoneyEdit()
        self.l_note = QLabel()
        self.l_note.setWordWrap(True)
        self.l_note.setStyleSheet("color: #e0a030;")
        self.l_hours, self.l_rate, self.l_regular = QLabel(), QLabel(), QLabel()
        self.l_cap = QLabel()
        self.l_cap.setWordWrap(True)
        self.l_cap.setStyleSheet("color: #d9534f;")
        self.l_otcalc, self.l_ottotal = QLabel(), QLabel()
        self.l_otcalc.setWordWrap(True)
        self.l_payable, self.l_paid, self.l_carry, self.l_cum = QLabel(), QLabel(), QLabel(), QLabel()
        for lab in (self.l_payable, self.l_cum):
            f = lab.font()
            f.setBold(True)
            f.setPointSize(f.pointSize() + 3)
            lab.setFont(f)
        form = QFormLayout()
        form.addRow(t("settle_mode"), self.mode)
        form.addRow(t("month_total_hours"), self.total_hours)
        form.addRow("", self.l_note)
        form.addRow(t("overtime_hours"), self.ot_hours)
        form.addRow(t("total_hours"), self.l_hours)
        form.addRow(t("hourly_rate"), self.l_rate)
        form.addRow(t("regular_pay"), self.l_regular)
        form.addRow("", self.l_cap)
        form.addRow(t("ot_calc"), self.l_otcalc)
        form.addRow(t("ot_extra"), self.overtime)
        form.addRow(t("overtime_pay"), self.l_ottotal)
        form.addRow(t("payable"), self.l_payable)
        form.addRow(t("transfer"), self.transfer)
        form.addRow(t("cash_paid"), self.cash)
        form.addRow(t("paid"), self.l_paid)
        form.addRow(t("carry"), self.l_carry)
        form.addRow(t("cum_payable"), self.l_cum)
        sbox = QGroupBox(t("tab_payroll"))
        sbox.setLayout(form)
        self.btn_pdf_all = QPushButton(t("export_payroll"))
        self.btn_pdf_one = QPushButton(t("export_payroll_one"))
        right = QVBoxLayout()
        right.addWidget(sbox)
        right.addWidget(self.btn_pdf_all)
        right.addWidget(self.btn_pdf_one)
        right.addStretch()
        inner = QWidget()
        inner.setLayout(right)
        rw = QScrollArea()
        rw.setWidgetResizable(True)
        rw.setWidget(inner)
        rw.setFixedWidth(440)

        body = QHBoxLayout()
        body.addLayout(left, 1)
        body.addWidget(rw)
        main = QVBoxLayout(self)
        main.addLayout(bar)
        main.addLayout(body, 1)

        self.btn_workers.clicked.connect(self.manage)
        self.worker.currentIndexChanged.connect(self.refresh)
        self.month.dateChanged.connect(self.on_month)
        self.btn_add.clicked.connect(lambda: self.add(False))
        self.btn_del.clicked.connect(self.remove)
        self.table.itemChanged.connect(self.on_item_changed)
        self.mode.currentIndexChanged.connect(self.save_month)
        for e in (self.total_hours, self.ot_hours, self.overtime, self.transfer, self.cash):
            e.editingFinished.connect(self.save_month)
        link_enter([self.mode, self.total_hours, self.ot_hours, self.overtime, self.transfer, self.cash],
                   lambda: self.date.setFocus(Qt.TabFocusReason))
        self.btn_pdf_all.clicked.connect(lambda: self.export(False))
        self.btn_pdf_one.clicked.connect(lambda: self.export(True))
        link_enter([self.date, self.start, self.end, self.brk], self.ask_add)
        self.reload_workers()

    # ---- 基础 ----
    def wid(self):
        return self.worker.currentData()

    def reload_workers(self, keep=None):
        keep = keep if keep is not None else self.wid()
        self.worker.blockSignals(True)
        self.worker.clear()
        for w in self.db.workers():
            self.worker.addItem(w["name"] + ("" if w["active"] else f"  ({self.tr('status_left')})"), w["id"])
        i = self.worker.findData(keep)
        self.worker.setCurrentIndex(i if i >= 0 else 0)
        self.worker.blockSignals(False)
        self.refresh()

    def manage(self):
        WorkerDialog(self.db, self.tr, self).exec()
        self.reload_workers()

    def on_month(self):
        y, m = self.month.ym()
        d = self.date.date()
        self.date.setDate(QDate(y, m, min(d.day(), QDate(y, m, 1).daysInMonth())))
        self.refresh()

    def refresh(self):
        wid = self.wid()
        y, m = self.month.ym()
        rows = self.db.entries(wid, y, m) if wid is not None else []
        self._loading = True
        self.table.setRowCount(0)
        for e in rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            it = cell(_date.fromisoformat(e["date"]).strftime("%d.%m.%Y"))
            it.setData(Qt.UserRole, e["date"])
            it.setData(Qt.UserRole + 1, e["id"])
            self.table.setItem(i, 0, it)
            for col, key in ((1, "start"), (2, "end")):
                c = cell(P.fmt_hhmm(e[key]), right=True)
                c.setData(Qt.UserRole, e[key])
                self.table.setItem(i, col, c)
            b = cell(str(e["break_min"]), right=True)
            b.setData(Qt.UserRole, e["break_min"])
            self.table.setItem(i, 3, b)
            h = cell(P.fmt_hours(e["minutes"]), right=True, bold=True)
            h.setFlags(h.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 4, h)
        self._loading = False
        self.load_month()

    def load_month(self):
        wid = self.wid()
        y, m = self.month.ym()
        has = wid is not None
        mo = self.db.get_month(wid, y, m) if has else {"mode": "daily", "total_minutes": 0, "ot_minutes": 0,
                                                       "transfer": 0, "cash": 0}
        self.mode.blockSignals(True)
        self.mode.setCurrentIndex(0 if mo["mode"] == "daily" else 1)
        self.mode.blockSignals(False)
        self.total_hours.set_minutes(mo["total_minutes"])
        self.ot_hours.set_minutes(mo["ot_minutes"])
        self.transfer.set_cents(mo["transfer"])
        self.cash.set_cents(mo["cash"])
        self.overtime.set_cents(self.db.get_overtime(wid, y, m) if has else 0)
        for wdg in (self.mode, self.ot_hours, self.overtime, self.transfer, self.cash):
            wdg.setEnabled(has)
        self.apply_mode()
        self.update_summary()

    def apply_mode(self):
        total = self.mode.currentData() == "total"
        has = self.wid() is not None
        self.total_hours.setEnabled(has and total)
        self.entry_box.setEnabled(has and not total)
        self.l_note.setText(self.tr("total_mode_note") if total else "")

    def save_month(self):
        wid = self.wid()
        if wid is None:
            return
        y, m = self.month.ym()
        self.db.set_month(wid, y, m, mode=self.mode.currentData(), total_minutes=self.total_hours.minutes(),
                          ot_minutes=self.ot_hours.minutes(), transfer=self.transfer.cents(), cash=self.cash.cents())
        self.db.set_overtime(wid, y, m, self.overtime.cents())
        self.apply_mode()
        self.update_summary()

    def update_summary(self):
        wid = self.wid()
        labels = (self.l_hours, self.l_rate, self.l_regular, self.l_cap, self.l_otcalc, self.l_ottotal,
                  self.l_payable, self.l_paid, self.l_carry, self.l_cum)
        if wid is None:
            for l in labels:
                l.clear()
            return
        y, m = self.month.ym()
        w = self.db.get_worker(wid)
        r = P.month_result(self.db, w, y, m)
        carry = P.carry_over(self.db, w, y, m)
        self.l_hours.setText(P.fmt_hours(r["minutes"]))
        self.l_rate.setText(fmt_eur(r["rate"]) + " / h")
        self.l_regular.setText(fmt_eur(r["regular"]))
        self.l_cap.setText(self.tr("cap_applied", c=fmt_eur(r["cap"]), g=fmt_eur(r["gross"])) if r["capped"] else "")
        self.l_otcalc.setText(
            f"{P.fmt_hours(r['ot_minutes'])} × {fmt_eur(r['rate'])} × {P.de_num(r['ot_mult'])} = {fmt_eur(r['ot_calc'])}")
        self.l_ottotal.setText(fmt_eur(r["overtime"]))
        self.l_payable.setText(fmt_eur(r["total"]))
        self.l_paid.setText(fmt_eur(r["paid"]))
        self.l_carry.setText(fmt_eur(carry))
        self.l_cum.setText(fmt_eur(carry + r["total"] - r["paid"]))

    # ---- 录入 ----
    def _read_entry(self):
        s, e, b = self.start.minutes(), self.end.minutes(), self.brk.value()
        if s is None or e is None:
            return None
        mins = P.entry_minutes(s, e, b)
        return (s, e, b, mins) if mins > 0 else None

    def ask_add(self):
        if self.wid() is None:
            QMessageBox.information(self, self.tr("add"), self.tr("need_worker"))
            return
        ent = self._read_entry()
        if ent is None:
            self.window().statusBar().showMessage(self.tr("invalid_time"), 5000)
            self.start.setFocus(Qt.TabFocusReason)
            return
        s, e, b, mins = ent
        r = QMessageBox.question(
            self, self.tr("add"),
            self.tr("entry_confirm", w=self.worker.currentText(), d=self.date.date().toString("dd.MM.yyyy"),
                    s=P.fmt_hhmm(s), e=P.fmt_hhmm(e), b=b, h=P.fmt_hours(mins)),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if r == QMessageBox.Yes:
            self.add(True)
            self.start.setFocus(Qt.TabFocusReason)

    def add(self, _confirmed=False):
        wid = self.wid()
        if wid is None:
            QMessageBox.information(self, self.tr("add"), self.tr("need_worker"))
            return
        ent = self._read_entry()
        if ent is None:
            self.window().statusBar().showMessage(self.tr("invalid_time"), 5000)
            return
        s, e, b, mins = ent
        d = self.date.date()
        self.db.add_entry(wid, iso(d), s, e, b, mins)
        self.month.setDate(d)  # 切到该日期所在月份
        self.refresh()
        self.date.setDate(d.addDays(1))  # 日期自动前进一天，方便连续录入；上下班时间保留
        self.window().statusBar().showMessage(self.tr("saved"), 3000)

    def remove(self):
        row = self.table.currentRow()
        if row < 0:
            return
        if QMessageBox.question(self, self.tr("delete"), self.tr("confirm_delete")) == QMessageBox.Yes:
            self.db.delete_entry(self.table.item(row, 0).data(Qt.UserRole + 1))
            self.refresh()

    # ---- 表格内双击编辑 ----
    def on_item_changed(self, item):
        if self._loading or item.column() == 4:
            return
        QTimer.singleShot(0, lambda r=item.row(): self.apply_edit(r))

    def apply_edit(self, row):
        it0 = self.table.item(row, 0)
        if it0 is None:
            return
        eid, d = it0.data(Qt.UserRole + 1), it0.data(Qt.UserRole)
        s = self.table.item(row, 1).data(Qt.UserRole)
        e = self.table.item(row, 2).data(Qt.UserRole)
        b = self.table.item(row, 3).data(Qt.UserRole) or 0
        mins = P.entry_minutes(s, e, b)
        if mins <= 0:
            self.window().statusBar().showMessage(self.tr("invalid_time"), 5000)
            self.refresh()
            return
        self.db.update_entry(eid, d, s, e, b, mins)
        self.month.setDate(QDate.fromString(d, "yyyy-MM-dd"))
        self.refresh()
        self.window().statusBar().showMessage(self.tr("saved"), 3000)

    # ---- PDF ----
    def export(self, only_current):
        if not self.db.workers() or (only_current and self.wid() is None):
            QMessageBox.information(self, self.tr("tab_payroll"), self.tr("need_worker"))
            return
        self.save_month()
        y, m = self.month.ym()
        ids = [self.wid()] if only_current else None
        name = f"_{self.worker.currentText()}" if only_current else ""
        default = os.path.join(os.path.expanduser("~"), "Documents", f"NoodleFun_Lohn_{y}-{m:02d}{name}.pdf")
        path, _ = QFileDialog.getSaveFileName(self, self.tr("export_payroll"), default, self.tr("pdf_filter"))
        if not path:
            return
        try:
            payroll_report.build_payroll(path, self.db, y, m, self.tr, ids)
        except Exception as ex:  # noqa: BLE001
            QMessageBox.critical(self, "PDF", self.tr("pdf_error") + str(ex))
            return
        if QMessageBox.question(self, "PDF", self.tr("pdf_saved") + path + "\n\n" + self.tr("pdf_open")) == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
