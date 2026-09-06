"""جدول موحّد: ``QTableView`` + ``QAbstractTableModel`` + ``QSortFilterProxyModel``.

يستقبل وصف أعمدة (:class:`Column`) وقائمة صفوف (``list[dict]``)، ويعطي
فرزاً وبحثاً حيّاً على كل الأعمدة وتحديد صفوف وتلوين متناوب — جاهزة.
كل عمود يقبل محاذاة واتجاهاً خاصّين به (الاتجاه عبر ``QStyledItemDelegate``
لا عبر ``setLayoutDirection``).

لا SQL ولا منطق حساب.
"""
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, Signal,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QStyledItemDelegate, QTableView,
    QVBoxLayout, QWidget,
)

_ALIGN_DEFAULT = Qt.AlignRight | Qt.AlignVCenter


@dataclass
class Column:
    key: str
    title: str
    align: Qt.Alignment = _ALIGN_DEFAULT
    ltr: bool = False                          # عمود لاتيني (أرقام/تواريخ) → رسم LTR
    width: Optional[int] = None                # px ثابت؛ None → تمدّد
    stretch: bool = True
    formatter: Optional[Callable[[Any], str]] = None


class _TableModel(QAbstractTableModel):
    def __init__(self, columns: List[Column], rows=None):
        super().__init__()
        self._cols = list(columns)
        self._rows: List[dict] = list(rows or [])

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = list(rows or [])
        self.endResetModel()

    def row_dict(self, source_row: int) -> Optional[dict]:
        if 0 <= source_row < len(self._rows):
            return self._rows[source_row]
        return None

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._cols)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        col = self._cols[index.column()]
        if role in (Qt.DisplayRole, Qt.EditRole):
            val = self._rows[index.row()].get(col.key, "")
            if col.formatter is not None:
                return col.formatter(val)
            return "" if val is None else str(val)
        if role == Qt.TextAlignmentRole:
            return int(col.align)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self._cols[section].title
        return section + 1


class _DirectionDelegate(QStyledItemDelegate):
    """يضبط اتجاه *رسم الخلية* حسب العمود (LTR للأعمدة اللاتينية) دون
    لمس اتجاه الجدول ككل."""

    def __init__(self, columns: List[Column], parent=None):
        super().__init__(parent)
        self._cols = columns

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.isValid() and self._cols[index.column()].ltr:
            option.direction = Qt.LeftToRight


class DataTable(QWidget):
    rowActivated = Signal(dict)          # نقر مزدوج على صفّ
    selectionChanged = Signal(object)   # dict الصفّ المحدَّد أو None

    def __init__(self, columns: List[Column], rows=None, parent=None):
        super().__init__(parent)
        self._columns = list(columns)
        self._model = _TableModel(self._columns, rows)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)      # كل الأعمدة
        self._proxy.setSortRole(Qt.DisplayRole)
        self._proxy.setDynamicSortFilter(True)

        self._view = QTableView(self)
        self._view.setModel(self._proxy)
        self._view.setSortingEnabled(True)
        self._view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._view.setSelectionMode(QAbstractItemView.SingleSelection)
        self._view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._view.setAlternatingRowColors(True)
        self._view.verticalHeader().setVisible(False)
        self._view.setItemDelegate(_DirectionDelegate(self._columns, self._view))

        header = self._view.horizontalHeader()
        header.setHighlightSections(False)
        for i, col in enumerate(self._columns):
            if col.width is not None:
                header.setSectionResizeMode(i, QHeaderView.Interactive)
                header.resizeSection(i, col.width)
            else:
                header.setSectionResizeMode(
                    i, QHeaderView.Stretch if col.stretch else QHeaderView.ResizeToContents
                )

        self._view.doubleClicked.connect(self._on_double_clicked)
        self._view.selectionModel().selectionChanged.connect(self._on_selection)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._view)

    # -------------------- الواجهة العمومية --------------------
    def set_rows(self, rows):
        self._model.set_rows(rows)

    def filter(self, text: str):
        """بحث حيّ: يفلتر مباشرةً على كل الأعمدة (غير حسّاس لحالة الأحرف)."""
        self._proxy.setFilterFixedString(text or "")

    def shown_count(self) -> int:
        return self._proxy.rowCount()

    def total_count(self) -> int:
        return self._model.rowCount()

    def selected_row(self) -> Optional[dict]:
        idx = self._view.selectionModel().currentIndex()
        if not idx.isValid():
            return None
        return self._model.row_dict(self._proxy.mapToSource(idx).row())

    def view(self) -> QTableView:
        return self._view

    # -------------------- داخلي --------------------
    def _row_from_proxy(self, proxy_index) -> Optional[dict]:
        return self._model.row_dict(self._proxy.mapToSource(proxy_index).row())

    def _on_double_clicked(self, proxy_index):
        row = self._row_from_proxy(proxy_index)
        if row is not None:
            self.rowActivated.emit(row)

    def _on_selection(self, *_):
        self.selectionChanged.emit(self.selected_row())
