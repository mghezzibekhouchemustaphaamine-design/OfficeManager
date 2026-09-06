"""نموذج تحقّق (PoC) — PySide6: شاشة «قائمة عمّال شركة».

الغرض: قياس PySide6 مقابل Tkinter على شاشة نموذج/عرض حقيقية، مع RTL
وعربية، وربط **كتابة فعلية** بقاعدة اختبار منفصلة.

  - QTableView + QAbstractTableModel  (نمط model/view — لا QTableWidget).
  - QSortFilterProxyModel: بحث حيّ يفلتر مباشرةً على كل الأعمدة.
  - «إضافة عامل» → QDialog → INSERT فعلي في جدول employe.
  - RTL كامل: اتجاه التخطيط، محاذاة النصوص، ترتيب الأعمدة (يُعكَس آلياً).

قاعدة الاختبار: ``<tempdir>/om_poc_employes.db`` — **ليست** القاعدة
الحقيقية (``office_system.db``). مخطّط جداول الأجور يُنشأ عبر
``programme.payroll.repository.run_migrations(conn)`` — وهو **الوحيد**
المستعمَل من ``repository.py`` (لا توجد فيه دوال CRUD للعمّال — راجع
تعليق ``insert_employe`` / ``load_employes`` أدناه).

التشغيل:
    python demos/pyside6_demo/employes_screen.py
    QT_QPA_PLATFORM=offscreen python demos/pyside6_demo/employes_screen.py --selftest
"""
import os
import sqlite3
import sys
import tempfile

# إتاحة استيراد programme.* عند التشغيل المباشر من داخل demos/
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PySide6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTableView, QVBoxLayout, QWidget,
)

from programme.payroll import repository

DB_PATH = os.path.join(tempfile.gettempdir(), "om_poc_employes.db")

# (مفتاح العمود في صفّ القاعدة, العنوان بالعربية, المحاذاة)
COLUMNS = [
    ("nom",          "اللقب",         Qt.AlignRight | Qt.AlignVCenter),
    ("prenom",       "الاسم",         Qt.AlignRight | Qt.AlignVCenter),
    ("num_ss",       "رقم الضمان",     Qt.AlignRight | Qt.AlignVCenter),
    ("poste",        "المنصب",         Qt.AlignRight | Qt.AlignVCenter),
    ("date_entree",  "تاريخ التوظيف",  Qt.AlignCenter),
    ("salaire_base", "الأجر القاعدي",  Qt.AlignLeft | Qt.AlignVCenter),  # أرقام لاتينية
]


# ----------------------------- قاعدة الاختبار -----------------------------

def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_db():
    """يُنشئ قاعدة الاختبار (مخطّط الأجور عبر repository) ويبذر شركة +
    عمّالاً إن كانت فارغة. لا يمسّ القاعدة الحقيقية إطلاقاً."""
    conn = _connect()
    repository.run_migrations(conn)          # ← الاستعمال الوحيد لـ repository.py
    ent = conn.execute("SELECT id FROM entreprise LIMIT 1").fetchone()
    if ent is None:
        eid = conn.execute(
            "INSERT INTO entreprise (raison_sociale, num_employeur_cnas) VALUES (?, ?)",
            ("SARL EXEMPLE", "16 12345678 90"),
        ).lastrowid
        seed = [
            ("AMROUNE", "Mohamed", "0187654321", "محاسب",     "2019-03-01", "48000"),
            ("BENALI",  "Yacine",  "0192345678", "تقني",       "2021-09-15", "36000"),
            ("CHERIF",  "Amina",   "0176543210", "موارد بشرية", "2018-01-10", "52000"),
            ("DJILALI", "Karim",   "0201122334", "أمين مخزن",   "2023-05-02", "30000"),
        ]
        conn.executemany(
            "INSERT INTO employe (entreprise_id, nom, prenom, num_ss, poste, "
            "date_entree, salaire_base) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(eid, *row) for row in seed],
        )
        conn.commit()
    else:
        eid = ent["id"]
    conn.close()
    return eid


# ملاحظة: repository.py لا يوفّر دوال قراءة/كتابة للعمّال (فيه runner
# الهجرات فقط). هاتان الدالتان SQL خام داخل الـPoC — راجع الجواب 4.

def load_employes(entreprise_id):
    conn = _connect()
    rows = conn.execute(
        "SELECT nom, prenom, num_ss, poste, date_entree, salaire_base "
        "FROM employe WHERE entreprise_id = ? AND actif = 1 ORDER BY nom, prenom",
        (entreprise_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def insert_employe(entreprise_id, data):
    conn = _connect()
    conn.execute(
        "INSERT INTO employe (entreprise_id, nom, prenom, num_ss, poste, "
        "date_entree, salaire_base) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (entreprise_id, data["nom"], data["prenom"], data["num_ss"],
         data["poste"], data["date_entree"] or None, data["salaire_base"] or "0"),
    )
    conn.commit()
    conn.close()


# ----------------------------- النموذج (Model) -----------------------------

class EmployeModel(QAbstractTableModel):
    def __init__(self, rows=None):
        super().__init__()
        self._rows = rows or []

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(COLUMNS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        key, _title, align = COLUMNS[index.column()]
        if role in (Qt.DisplayRole, Qt.EditRole):
            return str(self._rows[index.row()].get(key, "") or "")
        if role == Qt.TextAlignmentRole:
            return int(align)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return COLUMNS[section][1]
        return section + 1


# ----------------------------- حوار الإضافة -----------------------------

class AddEmployeDialog(QDialog):
    _FIELDS = [
        ("nom",          "اللقب *",                    "rtl"),
        ("prenom",       "الاسم",                       "rtl"),
        ("num_ss",       "رقم الضمان الاجتماعي",         "ltr"),
        ("poste",        "المنصب",                      "rtl"),
        ("date_entree",  "تاريخ التوظيف (YYYY-MM-DD)",  "ltr"),
        ("salaire_base", "الأجر القاعدي",               "ltr"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إضافة عامل")
        self.setLayoutDirection(Qt.RightToLeft)
        self._edits = {}
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        for key, label, direction in self._FIELDS:
            e = QLineEdit()
            # الحقول اللاتينية (أرقام/تواريخ) تُجبَر على LTR حتى تُقرأ طبيعياً
            e.setLayoutDirection(Qt.LeftToRight if direction == "ltr" else Qt.RightToLeft)
            self._edits[key] = e
            form.addRow(label, e)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def _try_accept(self):
        if not self._edits["nom"].text().strip():
            QMessageBox.warning(self, "ناقص", "اللقب إجباري.")
            return
        self.accept()

    def values(self):
        return {k: e.text().strip() for k, e in self._edits.items()}


# ----------------------------- الشاشة -----------------------------

class EmployesScreen(QWidget):
    def __init__(self, entreprise_id):
        super().__init__()
        self.entreprise_id = entreprise_id
        self.setWindowTitle("قائمة عمّال شركة — نموذج PySide6")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(780, 460)

        self.model = EmployeModel(load_employes(entreprise_id))
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)          # كل الأعمدة

        self.search = QLineEdit()
        self.search.setPlaceholderText("بحث فوري…  (لقب · اسم · منصب · رقم ضمان)")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.proxy.setFilterFixedString)

        add_btn = QPushButton("＋  إضافة عامل")
        add_btn.clicked.connect(self.on_add)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.count_lbl = QLabel()
        for sig in (self.proxy.rowsInserted, self.proxy.rowsRemoved,
                    self.proxy.modelReset, self.proxy.layoutChanged):
            sig.connect(self._refresh_count)
        self._refresh_count()

        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(add_btn)
        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.table, 1)
        root.addWidget(self.count_lbl)

    def _refresh_count(self, *args):
        self.count_lbl.setText(
            f"المعروض: {self.proxy.rowCount()}   /   الكلّي: {self.model.rowCount()}"
        )

    def on_add(self):
        dlg = AddEmployeDialog(self)
        if dlg.exec() == QDialog.Accepted:
            insert_employe(self.entreprise_id, dlg.values())
            self.model.set_rows(load_employes(self.entreprise_id))


# ----------------------------- التشغيل / الاختبار الذاتي -----------------------------

def _selftest():
    """يتحقّق بلا شاشة (QT_QPA_PLATFORM=offscreen): بذر → عرض → فلترة →
    كتابة فعلية → إعادة تحميل. يرجّع 0 عند النجاح."""
    eid = ensure_db()
    app = QApplication.instance() or QApplication([])
    app.setLayoutDirection(Qt.RightToLeft)
    scr = EmployesScreen(eid)

    assert scr.layoutDirection() == Qt.RightToLeft
    n0 = scr.model.rowCount()
    assert n0 >= 4, n0
    print(f"[selftest] عرض أوّلي: {n0} عامل · RTL={scr.layoutDirection() == Qt.RightToLeft}")

    scr.search.setText("ben")                       # فلترة حيّة
    shown = scr.proxy.rowCount()
    assert shown == 1, (shown, "expected BENALI only")
    print(f"[selftest] فلترة 'ben' → {shown} صفّ (BENALI)")
    scr.search.setText("")

    before = scr.model.rowCount()
    insert_employe(eid, {"nom": "ZEROUAL", "prenom": "Sara", "num_ss": "0209988776",
                         "poste": "سكرتيرة", "date_entree": "2025-02-01",
                         "salaire_base": "34000"})
    scr.model.set_rows(load_employes(eid))
    after = scr.model.rowCount()
    assert after == before + 1, (before, after)
    # تأكيد الكتابة على القرص
    conn = _connect()
    row = conn.execute("SELECT nom, poste FROM employe WHERE nom='ZEROUAL'").fetchone()
    conn.close()
    assert row and row["nom"] == "ZEROUAL" and row["poste"] == "سكرتيرة"
    print(f"[selftest] كتابة فعلية: {before} → {after} · القرص يؤكّد ZEROUAL")

    hdr = [scr.model.headerData(c, Qt.Horizontal) for c in range(scr.model.columnCount())]
    print(f"[selftest] رؤوس الأعمدة (منطقياً؛ تُعرَض معكوسة بصرياً في RTL): {hdr}")
    print(f"[selftest] قاعدة الاختبار: {DB_PATH}")
    print("[selftest] ALLOK")
    return 0


def main():
    if "--selftest" in sys.argv:
        return _selftest()
    eid = ensure_db()
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    scr = EmployesScreen(eid)
    scr.show()
    print(f"[PoC] قاعدة الاختبار: {DB_PATH}")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
