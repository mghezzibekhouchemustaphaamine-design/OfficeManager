"""الشاشة 1 — الشركات.

جدول الشركات (:class:`ui2.table.DataTable`) + شريط أدوات
(:class:`ui2.toolbar.ToolBar`) + حوار إضافة/تعديل
(:class:`ui2.dialog.FormDialog`). التخزين عبر
``programme.payroll.repository`` فقط.
"""
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

from programme.payroll import repository
from ui2.dialog import FormDialog
from ui2.form import Field
from ui2.alerts import (
    ACTIF_CHOICES, actif_to_text, clean, info_label, text_to_actif, warn,
)
from ui2.table import Column, DataTable
from ui2.toolbar import ToolAction, ToolBar

_FIELDS = [
    Field("raison_sociale", "التسمية / الاسم التجاري", required=True),
    Field("forme_juridique", "الشكل القانوني", kind="choice",
          choices=["", "SARL", "EURL", "SPA", "SNC", "Personne physique",
                   "Autre"]),
    Field("nif", "رقم التعريف الجبائي NIF", kind="ssn", max_len=20),
    Field("nis", "رقم التعريف الإحصائي NIS", kind="ssn", max_len=20),
    Field("rc", "السجل التجاري RC"),
    Field("art_imposition", "المادة الضريبية (article)"),
    Field("num_employeur_cnas", "رقم المُشغّل CNAS", kind="ssn", max_len=15),
    Field("adresse", "العنوان", kind="multiline"),
    Field("gerant_nom", "المسيّر — الاسم الكامل"),
    Field("gerant_qualite", "صفة المسيّر (gérant, PDG…)"),
    Field("tel", "الهاتف", kind="ssn", max_len=15),
    Field("actif", "الحالة", kind="choice", choices=ACTIF_CHOICES,
          default=ACTIF_CHOICES[0]),
]


class CompaniesScreen(QWidget):
    """يبثّ :data:`companySelected` بـ dict الشركة المحدَّدة (أو None)."""

    companySelected = Signal(object)

    def __init__(self, conn=None, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._rows = []

        self.toolbar = ToolBar(self)
        self.toolbar.add(ToolAction("＋ شركة جديدة", self._add, shortcut="Ctrl+N"))
        self._act_edit = self.toolbar.add(ToolAction("تعديل", self._edit))
        self.toolbar.add(ToolAction("تحديث", self.reload, shortcut="F5"))
        self.toolbar.add_stretch()
        self._search = QLineEdit()
        self._search.setPlaceholderText("بحث…  (تسمية · NIF · مسيّر)")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedWidth(260)
        self.toolbar.add_widget(self._search)

        self.table = DataTable(columns=[
            Column("id", "#", ltr=True, align=Qt.AlignCenter, width=52,
                   stretch=False),
            Column("raison_sociale", "التسمية"),
            Column("nif", "NIF", ltr=True, align=Qt.AlignLeft | Qt.AlignVCenter),
            Column("num_employeur_cnas", "رقم CNAS", ltr=True,
                   align=Qt.AlignLeft | Qt.AlignVCenter),
            Column("gerant_nom", "المسيّر"),
            Column("actif", "الحالة", align=Qt.AlignCenter, width=90,
                   stretch=False, formatter=actif_to_text),
        ])
        self._info = info_label("")

        self._search.textChanged.connect(self.table.filter)
        self.table.selectionChanged.connect(self._on_selection)
        self.table.rowActivated.connect(lambda _r: self._edit())

        lay = QVBoxLayout(self)
        lay.addWidget(self.toolbar)
        lay.addWidget(self.table, 1)
        lay.addWidget(self._info)

        self._on_selection(None)
        self.reload()

    # -------------------- بيانات --------------------
    def reload(self):
        self._rows = repository.list_entreprises(actif_only=False,
                                                 conn=self._conn)
        self.table.set_rows(self._rows)
        self._info.setText(f"عدد الشركات: {len(self._rows)}")

    def selected_company(self) -> Optional[dict]:
        return self.table.selected_row()

    # -------------------- أحداث --------------------
    def _on_selection(self, row):
        self._act_edit.setEnabled(row is not None)
        self.companySelected.emit(row)

    def _add(self):
        dlg = FormDialog("شركة جديدة", _FIELDS, self)
        if not dlg.exec():
            return
        data = clean(dlg.values())
        data["actif"] = text_to_actif(dlg.values().get("actif"))
        new_id = repository.create_entreprise(data, conn=self._conn)
        self.reload()
        self._select_by_id(new_id)

    def _edit(self):
        row = self.selected_company()
        if row is None:
            warn(self, "تعديل شركة", ["اختر شركة من الجدول أولاً."])
            return
        values = dict(row)
        values["actif"] = actif_to_text(row.get("actif"))
        dlg = FormDialog(f"تعديل — {row['raison_sociale']}", _FIELDS, self,
                         values=values)
        if not dlg.exec():
            return
        data = clean(dlg.values())
        data["actif"] = text_to_actif(dlg.values().get("actif"))
        repository.update_entreprise(row["id"], data, conn=self._conn)
        self.reload()
        self._select_by_id(row["id"])

    # -------------------- مساعد --------------------
    def _select_by_id(self, ent_id: int):
        view = self.table.view()
        model = view.model()
        for r in range(model.rowCount()):
            if str(model.index(r, 0).data()) == str(ent_id):
                view.selectRow(r)
                return
