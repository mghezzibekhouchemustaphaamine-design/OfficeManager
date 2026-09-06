"""معرض مكوّنات ui2 — كل مكوّن حيّاً في تبويب مستقل، ببيانات وهمية.

هذا ما يُفتَح للحكم على مكتبة المكوّنات (المرحلة 1). لا شاشة عمل هنا.

التشغيل:
    python demos/ui2_gallery.py
بلا شاشة (فحص):
    QT_QPA_PLATFORM=offscreen python demos/ui2_gallery.py --selftest
"""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from ui2 import theme
from ui2.dialog import FormDialog
from ui2.form import Field, Form
from ui2.shortcuts import ShortcutManager
from ui2.table import Column, DataTable
from ui2.tabs import TabHost
from ui2.toolbar import ToolAction, ToolBar
from ui2.window import MainWindow

# ------------------------- بيانات وهمية -------------------------
FAKE_EMPLOYES = [
    {"nom": "AMROUNE", "prenom": "Mohamed", "num_ss": "0187654321",
     "poste": "محاسب", "date_entree": "2019-03-01", "salaire": "48000"},
    {"nom": "BENALI", "prenom": "Yacine", "num_ss": "0192345678",
     "poste": "تقني", "date_entree": "2021-09-15", "salaire": "36000"},
    {"nom": "CHERIF", "prenom": "Amina", "num_ss": "0176543210",
     "poste": "موارد بشرية", "date_entree": "2018-01-10", "salaire": "52000"},
    {"nom": "DJILALI", "prenom": "Karim", "num_ss": "0201122334",
     "poste": "أمين مخزن", "date_entree": "2023-05-02", "salaire": "30000"},
    {"nom": "EL-HADI", "prenom": "Sofiane", "num_ss": "0198877665",
     "poste": "سائق", "date_entree": "2020-11-20", "salaire": "33000"},
]


def _money(v):
    try:
        return f"{float(v):,.2f}".replace(",", " ").replace(".", ",")
    except (TypeError, ValueError):
        return ""


# ------------------------- تبويب الجدول -------------------------
def build_table_tab() -> QWidget:
    page = QWidget()
    page.setObjectName("GalleryPage")
    table = DataTable(
        columns=[
            Column("nom", "اللقب"),
            Column("prenom", "الاسم"),
            Column("num_ss", "رقم الضمان", ltr=True, align=Qt.AlignLeft | Qt.AlignVCenter),
            Column("poste", "المنصب"),
            Column("date_entree", "تاريخ التوظيف", ltr=True, align=Qt.AlignCenter),
            Column("salaire", "الأجر", ltr=True, align=Qt.AlignLeft | Qt.AlignVCenter,
                   formatter=_money),
        ],
        rows=FAKE_EMPLOYES,
    )
    search = QLineEdit()
    search.setPlaceholderText("بحث فوري…  (لقب · اسم · منصب · رقم ضمان)")
    search.setClearButtonEnabled(True)
    info = QLabel()

    def refresh(*_):
        info.setText(f"المعروض: {table.shown_count()}  /  الكلّي: {table.total_count()}")

    search.textChanged.connect(table.filter)
    search.textChanged.connect(refresh)
    table.rowActivated.connect(lambda r: info.setText(f"فُتِح: {r['nom']} {r['prenom']}"))
    refresh()

    lay = QVBoxLayout(page)
    lay.addWidget(search)
    lay.addWidget(table, 1)
    lay.addWidget(info)
    page._table = table          # للـselftest
    page._search = search
    return page


# ------------------------- تبويب النموذج -------------------------
_FORM_FIELDS = [
    Field("nom", "اللقب", required=True),
    Field("prenom", "الاسم"),
    Field("num_ss", "رقم الضمان الاجتماعي", kind="ssn"),
    Field("date_entree", "تاريخ التوظيف", kind="date", default="2024-01-01"),
    Field("nb_enfants", "عدد الأولاد", kind="number", default="0"),
    Field("salaire_base", "الأجر القاعدي", kind="amount", required=True),
    Field("type_contrat", "نوع العقد", kind="choice", choices=["CDI", "CDD"]),
    Field("notes", "ملاحظات", kind="multiline"),
]


def build_form_tab() -> QWidget:
    page = QWidget()
    page.setObjectName("GalleryPage")
    form = Form(_FORM_FIELDS)
    out = QPlainTextEdit()
    out.setReadOnly(True)
    out.setFixedHeight(120)

    btns = QHBoxLayout()
    b_check = QPushButton("تحقّق")
    b_vals = QPushButton("اقرأ القيم")
    b_check.clicked.connect(
        lambda: out.setPlainText("\n".join(form.errors()) or "لا أخطاء — صالح.")
    )
    b_vals.clicked.connect(
        lambda: out.setPlainText("\n".join(f"{k} = {v!r}" for k, v in form.values().items()))
    )
    btns.addWidget(b_check)
    btns.addWidget(b_vals)
    btns.addStretch(1)

    lay = QVBoxLayout(page)
    lay.addWidget(form)
    lay.addLayout(btns)
    lay.addWidget(QLabel("النتيجة:"))
    lay.addWidget(out)
    lay.addStretch(1)
    page._form = form
    return page


# ------------------------- تبويب الحوار -------------------------
def build_dialog_tab() -> QWidget:
    page = QWidget()
    page.setObjectName("GalleryPage")
    out = QLabel("— لم يُفتح حوار بعد —")
    out.setWordWrap(True)

    def open_dialog():
        dlg = FormDialog("إضافة عامل", _FORM_FIELDS, page)
        if dlg.exec():
            vals = dlg.values()
            out.setText("قُبِل:\n" + "\n".join(f"{k} = {v}" for k, v in vals.items()))
        else:
            out.setText("أُلغي.")

    btn = QPushButton("افتح حوار «إضافة عامل»")
    btn.clicked.connect(open_dialog)

    lay = QVBoxLayout(page)
    lay.addWidget(btn)
    lay.addWidget(out)
    lay.addStretch(1)
    return page


# ------------------------- تبويب شريط الأدوات -------------------------
def build_toolbar_tab() -> QWidget:
    page = QWidget()
    page.setObjectName("GalleryPage")
    log = QPlainTextEdit()
    log.setReadOnly(True)

    def note(msg):
        log.appendPlainText(msg)

    tb = ToolBar(page)
    tb.add(ToolAction("＋ جديد", lambda: note("جديد"), shortcut="Ctrl+N"))
    tb.add(ToolAction("حفظ", lambda: note("حفظ"), shortcut="Ctrl+S"))
    tb.add(ToolAction("حذف", lambda: note("حذف")))
    tb.addSeparator()
    tb.add(ToolAction("تصفية", lambda: note("تصفية"), checkable=True))
    tb.add_stretch()
    box = QLineEdit()
    box.setPlaceholderText("بحث…")
    box.setFixedWidth(200)
    box.textChanged.connect(lambda t: note(f"بحث: {t!r}"))
    tb.add_widget(box)

    lay = QVBoxLayout(page)
    lay.addWidget(tb)
    lay.addWidget(log, 1)
    page._toolbar = tb
    return page


# ------------------------- تبويب التبويبات -------------------------
def build_tabs_tab() -> QWidget:
    page = QWidget()
    page.setObjectName("GalleryPage")
    host = TabHost(page)
    counter = {"n": 0}
    info = QLabel()

    def refresh(*_):
        info.setText(f"عدد التبويبات: {host.count()}  ·  النشط: {host.current_id()}")

    def new_tab():
        counter["n"] += 1
        w = QLabel(f"محتوى التبويب #{counter['n']}")
        w.setAlignment(Qt.AlignCenter)
        host.add_tab(w, f"عنصر {counter['n']}")

    def rename():
        if host.current_id() != -1:
            host.set_title(host.current_id(), f"مُعاد تسميته {host.current_id()}")

    host.tabAdded.connect(refresh)
    host.tabClosed.connect(refresh)
    host.currentChanged.connect(refresh)

    bar = QHBoxLayout()
    for text, fn in (("تبويب جديد", new_tab), ("أغلق الحالي",
                      lambda: host.close_tab(host.current_id())),
                     ("أغلق الكل", host.close_all), ("أعد تسمية", rename)):
        b = QPushButton(text)
        b.clicked.connect(fn)
        bar.addWidget(b)
    bar.addStretch(1)

    for _ in range(2):
        new_tab()

    lay = QVBoxLayout(page)
    lay.addLayout(bar)
    lay.addWidget(host, 1)
    lay.addWidget(info)
    page._host = host
    return page


# ------------------------- تبويب الاختصارات -------------------------
class ShortcutsTab(QWidget):
    """تبويب يطبّق دورة الحياة: يسجّل اختصاراته عند التنشيط ويلغيها عند
    المغادرة — بلا bind_all، بلا تسرّب."""

    def __init__(self):
        super().__init__()
        self.setObjectName("GalleryPage")
        self._sc = None
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._status = QLabel()
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "هذا التبويب يسجّل Ctrl+S · Ctrl+W · Ctrl+L عند تنشيطه فقط،\n"
            "ويلغيها عند مغادرته (جرّب التنقّل بين التبويبات ولاحظ العدّاد)."
        ))
        lay.addWidget(self._status)
        lay.addWidget(self._log, 1)
        self._refresh()

    def _refresh(self):
        n = len(self._sc) if self._sc else 0
        self._status.setText(f"اختصارات مسجَّلة حالياً: {n}")

    def _note(self, msg):
        self._log.appendPlainText(msg)
        self._refresh()

    def on_activate(self):
        self._sc = ShortcutManager(self)
        self._sc.register_many({
            "Ctrl+S": lambda: self._note("Ctrl+S → حفظ"),
            "Ctrl+W": lambda: self._note("Ctrl+W → إغلاق"),
            "Ctrl+L": lambda: self._note("Ctrl+L → سجلّ"),
        })
        self._note("on_activate → سُجِّلت 3 اختصارات")

    def on_deactivate(self):
        if self._sc:
            self._sc.unregister_all()
        self._note("on_deactivate → أُلغيت كل الاختصارات")


# ------------------------- تبويب المظهر / RTL -------------------------
def build_theme_tab() -> QWidget:
    page = QWidget()
    page.setObjectName("GalleryPage")
    app = QApplication.instance()
    rtl = app.layoutDirection() == Qt.RightToLeft
    lay = QVBoxLayout(page)
    lay.addWidget(QLabel(f"اتجاه التخطيط: {'RightToLeft ✓' if rtl else 'LeftToRight'}"))
    lay.addWidget(QLabel(f"عائلة الخط المُختارة: {theme.resolved_font_family()}"))
    lay.addWidget(QLabel(f"عائلات fallback: {' → '.join(theme.FONT_FAMILIES)}"))
    lay.addWidget(QLabel(f"حجم الخط: {theme.FONT_POINT_SIZE}pt"))
    sw = QHBoxLayout()
    for name, color in (("primary", theme.PRIMARY), ("surface", theme.SURFACE),
                        ("border", theme.BORDER), ("warning", theme.WARNING),
                        ("danger", theme.DANGER), ("field-empty", theme.FIELD_EMPTY)):
        chip = QLabel(f"  {name}  ")
        chip.setStyleSheet(f"background:{color}; border:1px solid {theme.BORDER}; padding:6px;")
        sw.addWidget(chip)
    sw.addStretch(1)
    lay.addLayout(sw)
    lay.addWidget(QLabel("عيّنة حقول (لاحظ RTL والحقول اللاتينية LTR):"))
    lay.addWidget(Form([
        Field("txt", "نصّ عربي", placeholder="اكتب هنا"),
        Field("num", "رقم", kind="number", default="123"),
        Field("amt", "مبلغ", kind="amount", default="45000.00"),
    ]))
    lay.addStretch(1)
    return page


# ------------------------- التجميع -------------------------
def build_gallery() -> MainWindow:
    win = MainWindow("معرض مكوّنات ui2 — المرحلة 1")
    win.toolbar.add(ToolAction("عن المعرض",
                    lambda: win.status("مكتبة مكوّنات PySide6 — بلا شاشات عمل")))
    win.add_tab(build_table_tab(), "الجدول")
    win.add_tab(build_form_tab(), "النموذج")
    win.add_tab(build_dialog_tab(), "الحوار")
    win.add_tab(build_toolbar_tab(), "شريط الأدوات")
    win.add_tab(build_tabs_tab(), "التبويبات")
    win.add_tab(ShortcutsTab(), "الاختصارات")
    win.add_tab(build_theme_tab(), "المظهر / RTL")
    win.tabs.tab_widget().setCurrentIndex(0)
    return win


def _selftest() -> int:
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    assert app.layoutDirection() == Qt.RightToLeft
    win = build_gallery()

    tbl_page = win.tabs.widget(1)
    assert tbl_page._table.total_count() == len(FAKE_EMPLOYES)
    tbl_page._search.setText("ben")
    assert tbl_page._table.shown_count() == 1, tbl_page._table.shown_count()
    tbl_page._search.setText("")
    print(f"[selftest] الجدول: {tbl_page._table.total_count()} صفّ · فلترة 'ben' → 1")

    form_page = win.tabs.widget(2)
    assert form_page._form.errors(), "المفروض أخطاء (حقول إجبارية فارغة)"
    form_page._form.set_values({"nom": "X", "salaire_base": "40000"})
    assert not form_page._form.errors(), form_page._form.errors()
    print("[selftest] النموذج: errors() قبل التعبئة ثم فارغة بعدها")

    dlg = FormDialog("t", _FORM_FIELDS)
    assert set(dlg.values()) == {f.key for f in _FORM_FIELDS}
    assert dlg.form.widget("num_ss").layoutDirection() == Qt.LeftToRight
    assert dlg.form.widget("nom").layoutDirection() == Qt.RightToLeft
    print("[selftest] الحوار/النموذج: num_ss=LTR · nom=RTL (سلوك المكتبة)")

    tabs_page = win.tabs.widget(5)
    n0 = tabs_page._host.count()
    tabs_page._host.close_all()
    assert tabs_page._host.count() == 0
    print(f"[selftest] التبويبات: {n0} → close_all → 0")

    sc_tab = win.tabs.widget(6)
    sc_tab.on_activate()
    assert len(sc_tab._sc) == 3, len(sc_tab._sc)
    sc_tab.on_deactivate()
    assert len(sc_tab._sc) == 0
    print("[selftest] الاختصارات: on_activate→3 · on_deactivate→0 (لا تسرّب)")

    tb_page = win.tabs.widget(4)
    assert len(tb_page._toolbar.actions()) >= 4
    print(f"[selftest] شريط الأدوات: {len(tb_page._toolbar.actions())} إجراء")

    print("[selftest] ALLOK")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()
    app = QApplication(sys.argv)
    theme.apply_theme(app)
    win = build_gallery()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
