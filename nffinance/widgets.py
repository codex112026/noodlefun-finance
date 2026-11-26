"""共用输入控件、表格委托与小工具（营业额 / 支出 / 工资结算页共用）。"""
from datetime import date as _date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from PySide6.QtCore import QDate, QEvent, QRegularExpression, Qt, Signal
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDateEdit, QHeaderView, QLineEdit, QStyledItemDelegate, QTableWidget,
    QTableWidgetItem,
)

from .i18n import fmt_eur


def parse_cents(text: str) -> int:
    t = text.strip().replace(" ", "").replace(",", ".")
    if not t:
        return 0
    try:
        return int((Decimal(t) * 100).quantize(Decimal(1), ROUND_HALF_UP))
    except InvalidOperation:
        return 0


def input_text(cents: int) -> str:
    return "" if not cents else f"{cents // 100},{cents % 100:02d}"


class MoneyEdit(QLineEdit):
    """金额输入：默认留空（不预设 0,00），可输入 12,5 或 12.50。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignRight)
        self.setValidator(QRegularExpressionValidator(QRegularExpression(r"^\d{0,9}([.,]\d{0,2})?$"), self))
        self.setMinimumWidth(140)
        self.editingFinished.connect(self._tidy)

    def _tidy(self):
        if self.text().strip():
            self.setText(input_text(self.cents()) or "0,00")

    def cents(self) -> int:
        return parse_cents(self.text())

    def set_cents(self, c: int):
        self.setText(input_text(c))


class NavDateEdit(QDateEdit):
    """日期输入：↑↓ 增减日(tt)，←→ 增减月(mm)，Enter 发出 enterPressed。"""

    enterPressed = Signal()

    def __init__(self, date=None, parent=None):
        super().__init__(date or QDate.currentDate(), parent)
        self.setDisplayFormat("dd.MM.yyyy")
        self.setCalendarPopup(True)
        self.lineEdit().installEventFilter(self)

    def eventFilter(self, obj, ev):
        if obj is self.lineEdit() and ev.type() == QEvent.KeyPress and not (
            ev.modifiers() & (Qt.ControlModifier | Qt.AltModifier)
        ):
            k, d = ev.key(), self.date()
            if k == Qt.Key_Up:
                self.setDate(d.addDays(1))
                return True
            if k == Qt.Key_Down:
                self.setDate(d.addDays(-1))
                return True
            if k == Qt.Key_Right:
                self.setDate(d.addMonths(1))
                return True
            if k == Qt.Key_Left:
                self.setDate(d.addMonths(-1))
                return True
        return super().eventFilter(obj, ev)

    def keyPressEvent(self, ev):
        super().keyPressEvent(ev)
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.enterPressed.emit()


class NavCombo(QComboBox):
    enterPressed = Signal()

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.enterPressed.emit()
            return
        super().keyPressEvent(ev)


def link_enter(widgets, on_last):
    """Enter 跳到下一个可用项（跳过被禁用的）；在最后一项按 Enter 调用 on_last。"""
    def sig(w):
        return w.returnPressed if isinstance(w, QLineEdit) else w.enterPressed

    def go(i):
        for n in widgets[i + 1:]:
            if n.isEnabled():
                n.setFocus(Qt.TabFocusReason)
                return
        on_last()

    for i, wd in enumerate(widgets):
        sig(wd).connect(lambda i=i: go(i))


# ---- 表格内双击编辑用的委托 ----
def _commit(model, index, display, user):
    model.blockSignals(True)
    model.setData(index, user, Qt.UserRole)
    model.setData(index, display, Qt.DisplayRole)
    model.blockSignals(False)
    model.dataChanged.emit(index, index)  # 只触发一次 itemChanged


class MoneyDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        return MoneyEdit(parent)

    def setEditorData(self, editor, index):
        editor.set_cents(index.data(Qt.UserRole) or 0)
        editor.selectAll()

    def setModelData(self, editor, model, index):
        c = editor.cents()
        _commit(model, index, fmt_eur(c), c)


class DateDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        e = NavDateEdit(parent=parent)
        e.setCalendarPopup(False)
        return e

    def setEditorData(self, editor, index):
        editor.setDate(QDate.fromString(index.data(Qt.UserRole), "yyyy-MM-dd"))

    def setModelData(self, editor, model, index):
        d = editor.date()
        _commit(model, index, d.toString("dd.MM.yyyy"), d.toString("yyyy-MM-dd"))


class CategoryDelegate(QStyledItemDelegate):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db

    def createEditor(self, parent, option, index):
        c = NavCombo(parent)
        c.addItems(self.db.categories())
        return c

    def setEditorData(self, editor, index):
        cur = index.data(Qt.DisplayRole)
        if editor.findText(cur) < 0:
            editor.addItem(cur)
        editor.setCurrentText(cur)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.DisplayRole)


class MonthPicker(QDateEdit):
    def __init__(self):
        super().__init__(QDate.currentDate())
        self.setDisplayFormat("MM / yyyy")
        self.setCalendarPopup(True)

    def ym(self):
        d = self.date()
        return d.year(), d.month()


def make_table(headers, editable=False):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.DoubleClicked if editable else QAbstractItemView.NoEditTriggers)
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


