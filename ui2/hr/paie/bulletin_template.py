"""كشف الراتب الشهري / Bulletin de paie — إعادة بناء ``ui/hr/bulletin_paie.py``
+ ``ui/hr/paie/template_simple.py`` فوق PySide6 (المرحلة 3-أ من
``docs/MIGRATION_PLAN_PYSIDE6.md``).

**المبدأ الحاكم:** نفس الشكل حرفياً — ورقة A4 مرسومة بالمليمتر فوق لوحة
رمادية، حقولٌ مطلقة الموضع فوقها، شريط جانبي وزوم. الفرق الوحيد: الإطار
PySide6 بدل Tkinter، والحساب من :mod:`programme.payroll.calc` (الدالة
``compute`` — نفس مُهايئ الشاشة القديمة) بدل منطق Tkinter.

- تخطيط الاستمارة (ثوابت المليمتر، ``FIELD_SLOTS``، ``COLS``، ``slot_px``)
  يُعاد استعماله كما هو من ``ui.hr.paie.template_simple`` — لا تكرار.
- مُصيِّر Word/PDF يُستدعى كما هو من ``template_simple.get_renderer`` — لا
  يُعاد كتابته (``build_docx`` / ``build_pdf`` لا تلمسان tkinter).
- **استيراد انتقالي:** هذا الملف يستورد ``ui.hr.paie.template_simple``
  (يجرّ ``tkinter.font`` وحده عند التحميل، بلا إنشاء جذر Tk). يُنقَل
  الجزء المشترك إلى وحدة بلا إطار في المرحلة 4 عند حذف ``ui/``.
"""
import logging
import os
import re
from datetime import date

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPalette
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMenu, QPushButton, QRadioButton, QScrollArea,
    QSplitter, QVBoxLayout, QWidget,
)

from programme import database, paths
from programme.payroll import calc, lignes, registry
from programme.payroll.calc import fmt_montant
from programme.payroll.config_loader import PayrollConfigError, load_params
from ui.hr.constants import MOIS_FR
from ui.hr.paie import template_simple as T
from ui.hr.render import TemplateNotReady
from ui2 import theme
from ui2.alerts import confirm
from ui2.form import DateField, GroupedNumberEdit, resolve_month
from ui2.hr.paie.validation import validate_screen
from ui2.screen import Screen

logger = logging.getLogger(__name__)

_ENTRY_FONT = T.FORM_FONT                       # "Helvetica" — نفس خط النموذج
# معايرة عمودية لمنطقة بيانات العامل في الشاشة الجديدة فقط — الأصل بدا
# أكثر انفراجاً؛ نزيد إيقاع صفوف الهوية بمقدار SPACE["sm"] لكل فجوة،
# وتُزاح كتلة الجدول أسفلها بنفس المجموع (بلا تداخل مع ترويسة الجدول).
_IDENT_ROW_EXTRA_PX = theme.SPACE["sm"]
# ---- إحداثيات الوثيقة → إحداثيات اللوحة: تحويلٌ واحد لكل شيء (Phase 55) ----
_FONT_K = 0.62                # مليمتر ارتفاع الخط × scale × K = نقاط الخط
_ENTRY_CHROME_MM = 1.2       # كروم QLineEdit العمودي (حدّ+حشو) — بالمليمتر فيتبع الزوم
_FIT_PAD_MM = 3.0           # هامش عرض حقل «يتّسع لمحتواه»
_DATE_BTN_MM = 6.0         # عرض زرّ التقويم داخل DateField
_MOIS_UP = [m.upper() for m in MOIS_FR]
_FAMILLE_CODES = {"C", "D", "V", "M"}
_FAMILLE_CHOICES = (("C", "Célibataire"), ("D", "Divorcé(e)"),
                    ("V", "Veuf(ve)"), ("M", "Marié(e)"))


class _DocView:
    """التحويل الوحيد من إحداثيات الوثيقة (مليمتر ورقة A4) إلى إحداثيات
    اللوحة (بكسل). كلّ عنصر — رسمٌ أو ودجت — يمرّ عبره، فلا يحسب أيّ حقل
    موضعه/مقياسه مستقلًّا. ``scale`` = بكسل لكلّ مليمتر."""

    __slots__ = ("x0", "y0", "scale", "sheet_w", "sheet_h", "cw", "ch")

    def __init__(self, x0, y0, scale, sheet_w, sheet_h, cw, ch):
        self.x0, self.y0, self.scale = x0, y0, scale
        self.sheet_w, self.sheet_h, self.cw, self.ch = sheet_w, sheet_h, cw, ch

    def x(self, mm):
        return self.x0 + (T.MARGIN_L + mm) * self.scale

    def y(self, mm):
        return self.y0 + mm * self.scale

    def px(self, mm):
        return mm * self.scale

    def font(self, mm_h, bold=False):
        f = QFont(_ENTRY_FONT)
        f.setPointSizeF(max(mm_h * self.scale * _FONT_K, 0.5))   # لا أرضية 6pt
        f.setBold(bool(bold))
        return f


# ======================= نموذج صفوف جدول الكشف (Phase A2) =======================
#  abstraction صغير خاصّ بجدول هذا الكشف: يفصل «ما الصفوف؟» عن «كيف تُرسم؟».
#  كل صف يعرف نوعه الدلاليّ، دوره (أساسي/اختياري/نظام)، خلاياه القابلة
#  للتحرير، وكيف يتحوّل إلى entry لـ ``lignes.compute_bulletin``. الحساب
#  كلّه في المحرّك — الصفوف لا تحسب.

_YES, _NO = "نعم", "لا"
_C = T.PAIE_DEFAULT_CODES

#  الترتيب الدلاليّ الثابت (§13). صفوف نفس النوع تحافظ على ترتيب الإضافة
#  داخل حزمتها.
_SEMANTIC_ORDER = {"salaire": 0, "iep": 10, "prime": 20, "hs": 30,
                   "absence": 40, "retard": 50, "panier": 60, "transport": 70,
                   "cnas": 80, "irg": 90, "avance": 100, "autre": 110}

#  تصنيف مالِيّ مُعلَن (بلا مصطلحات Zones): 3 خيارات تُترجَم إلى
#  (cotisable, imposable) — لا تخمين صامت (§0/§6).
_SOUMIS_CHOICES = ("CNAS + IRG", "IRG seul", "Net (ni CNAS ni IRG)")


def _soumis_class(label):
    if label.startswith("CNAS"):
        return _YES, _YES                      # Z1
    if label.startswith("IRG"):
        return _NO, _YES                       # Z2
    return _NO, _NO                            # Z3 (net)


# --------- تحويل الصفوف إلى entries لـ lignes.compute_bulletin ---------

def _prime_entry(r):
    cot, imp = _soumis_class(r.val("soumis") or "CNAS + IRG")
    return {"type": "libre", "values": {
        "libelle": r.val("libelle") or "PRIME / INDEMNITÉ",
        "montant": r.val("gain"), "est_retenue": _NO,
        "cotisable": cot, "imposable": imp}}


def _avance_entry(r):
    return {"type": "libre", "values": {
        "libelle": r.val("libelle") or "AVANCE / RETENUE",
        "montant": r.val("montant"), "est_retenue": _YES,
        "cotisable": _NO, "imposable": _NO}}


def _autre_entry(r):
    #  fallback: gain أو retenue بخيار صريح داخل السطر. gain مصنَّف
    #  بخيار مُعلَن (Net افتراضاً — الأكثر تحفّظاً). لا تخمين صامت (§0).
    lbl = r.val("libelle") or "AUTRE"
    if r.val("sens") == "Gain":
        cot, imp = _soumis_class(r.val("classe") or _SOUMIS_CHOICES[2])
        return {"type": "libre", "values": {
            "libelle": lbl, "montant": r.val("montant"), "est_retenue": _NO,
            "cotisable": cot, "imposable": imp}}
    return {"type": "libre", "values": {
        "libelle": lbl, "montant": r.val("montant"), "est_retenue": _YES,
        "cotisable": _NO, "imposable": _NO}}


def _abs_type(r):
    return "abs_jours" if "jours" in r.val("mode").lower() else "abs_heures"


def _abs_entry(r):
    t = _abs_type(r)
    return {"type": t, "values": {
        ("jours" if t == "abs_jours" else "heures"): r.val("qty")}}


def _hs_type(r):
    return "hs_50" if r.val("coef").startswith("50") else "hs_100"


#  spec خلية: (name, col, kind, opts, default). col نصّ عمود أو callable.
def _cs(name, col, kind, opts=(), default=""):
    return {"name": name, "col": col, "kind": kind,
            "opts": tuple(opts), "default": default}


_AUTRE_MONTANT_COL = lambda r: "gain" if r.val("sens") == "Gain" else "retenue"  # noqa: E731

_ROW_SPECS = {
    "salaire": dict(
        role="basic", code=_C["salaire_base"], lib="SALAIRE DE BASE",
        primary="gain",
        cells=(_cs("nbase", "nbase", "amount"), _cs("gain", "gain", "amount")),
        to_entry=lambda r: {"type": "salaire_base",
                            "values": {"montant": r.val("gain")}}),
    "iep": dict(
        role="optional", code="IEP", lib="IND. EXPÉRIENCE PROF.",
        primary="taux", computed="gain", lignes_key="iep",
        cells=(_cs("taux", "taux", "amount"),),
        to_entry=lambda r: {"type": "iep", "values": {"taux": r.val("taux")}}),
    "prime": dict(
        role="optional", code="", lib="", primary="gain",
        cells=(_cs("code", "code", "text"), _cs("libelle", "libelle", "text"),
               _cs("soumis", "taux", "choice", _SOUMIS_CHOICES, _SOUMIS_CHOICES[0]),
               _cs("gain", "gain", "amount")),
        to_entry=_prime_entry),
    "hs": dict(
        role="optional", code="HS", lib="HEURES SUPPLÉMENTAIRES",
        primary="qty", computed="gain", lignes_key=_hs_type,
        cells=(_cs("qty", "nbase", "amount"),
               _cs("coef", "taux", "choice", ("50%", "100%"), "50%")),
        to_entry=lambda r: {"type": _hs_type(r),
                            "values": {"heures": r.val("qty")}}),
    #  Absence/Retard = Z1: تُنقِص وعاء [A] وTOTAL_GAINS [6]، لا تدخل
    #  TOTAL_RETENUES [11]. تُرسَم **مبلغاً سالباً في عمود GAIN** — فيتّزن
    #  العمودان مع الصافي (نفس تمثيل المُصيِّر، Phase C2 §19).
    "absence": dict(
        role="optional", code="ABS", lib="", primary="qty",
        computed="gain", computed_neg=True, lignes_key=_abs_type,
        cells=(_cs("mode", "libelle", "choice",
                   ("Absence (jours)", "Absence (heures)"), "Absence (jours)"),
               _cs("qty", "nbase", "amount")),
        to_entry=_abs_entry),
    "retard": dict(
        role="optional", code="RET", lib="RETARD", primary="qty",
        computed="gain", computed_neg=True, lignes_key="retard",
        cells=(_cs("qty", "nbase", "amount"),),
        to_entry=lambda r: {"type": "retard", "values": {"heures": r.val("qty")}}),
    "panier": dict(
        role="basic", code=_C["panier"], lib="PANIER", primary="",
        cells=(_cs("gain", "gain", "amount"),),
        to_entry=lambda r: {"type": "panier",
                            "values": {"montant_mensuel": r.val("gain")}}),
    "transport": dict(
        role="basic", code=_C["transport"], lib="(R+) TRANSPORT", primary="",
        cells=(_cs("gain", "gain", "amount"),),
        to_entry=lambda r: {"type": "transport",
                            "values": {"montant_mensuel": r.val("gain")}}),
    "avance": dict(
        role="optional", code="", lib="", primary="montant",
        cells=(_cs("code", "code", "text"), _cs("libelle", "libelle", "text"),
               _cs("montant", "retenue", "amount")),
        to_entry=_avance_entry),
    "autre": dict(
        role="optional", code="", lib="", primary="montant",
        cells=(_cs("code", "code", "text"), _cs("libelle", "libelle", "text"),
               _cs("sens", "taux", "choice", ("Retenue", "Gain"), "Retenue"),
               _cs("classe", "nbase", "choice", _SOUMIS_CHOICES, _SOUMIS_CHOICES[2]),
               _cs("montant", _AUTRE_MONTANT_COL, "amount")),
        to_entry=_autre_entry),
    "cnas": dict(role="system", code=_C["cnas"],
                 lib="RETENUE SÉCU. SOCIALE", cells=(), primary=""),
    "irg": dict(role="system", code=_C["irg"], lib="RETENUE IRG",
                cells=(), primary=""),
}

#  قائمة «+ Ajouter» — منتَج مبسَّط فوق الـ domain (لا تعرض أنواع
#  ``lignes.LINE_TYPES`` التقنية؛ jours/heures و50/100 خيارات **داخل** السطر).
_AJOUTER_MENU = (("IEP / Ancienneté", "iep"),
                 ("Prime / Indemnité", "prime"),
                 ("Heures supplémentaires", "hs"),
                 ("Absence", "absence"),
                 ("Retard", "retard"),
                 ("Avance / Retenue", "avance"),
                 ("Autre", "autre"))

_MAX_BODY_ROWS = 18          # حدّ عمليّ (لا pagination في A2) — §14

_COL_ALIGN = {"code": Qt.AlignHCenter, "libelle": Qt.AlignLeft,
              "nbase": Qt.AlignRight, "taux": Qt.AlignRight,
              "gain": Qt.AlignRight, "retenue": Qt.AlignRight}


class _Row:
    """صفّ واحد في جدول الكشف. يملك widgetات خلاياه القابلة للتحرير
    (‏``QLineEdit`` / ``QComboBox``، مسجَّلة في ``screen._widgets`` بمفتاح
    ``r{rid}_{cell}``). المبلغ المحسوب (IEP/Absence/Retard/HS) **ليس**
    widgetاً — يُرسَم من ``BulletinView``."""

    def __init__(self, screen: "BulletinTemplateScreen", kind: str, rid: int):
        self.screen = screen
        self.kind = kind
        self.rid = rid
        self.seq = screen._row_seq
        screen._row_seq += 1
        spec = _ROW_SPECS[kind]
        self.role = spec["role"]
        self.code = spec["code"]
        self.libelle = spec["lib"]
        self._cellspec = {c["name"]: c for c in spec["cells"]}
        self.widgets = {}
        self._amount = None                       # المبلغ المحسوب (إن وُجد)
        self._iep_manual = False
        for c in spec["cells"]:
            name, k = c["name"], self.cell_key(c["name"])
            if c["kind"] == "choice":
                w = QComboBox(screen._canvas)
                w.addItems(c["opts"])
                if c["default"]:
                    w.setCurrentText(c["default"])
                w.currentTextChanged.connect(
                    lambda _t, kk=k: screen._on_row_edit(kk))
            else:
                w = QLineEdit(screen._canvas)
                w.setFrame(False)
                col = self.column(name)
                w.setAlignment(_COL_ALIGN.get(col, Qt.AlignLeft) | Qt.AlignVCenter)
                w.textChanged.connect(lambda _t, kk=k: screen._on_row_edit(kk))
                w.returnPressed.connect(lambda kk=k: screen._focus_rel(kk, +1))
                if c["default"]:
                    w.setText(c["default"])
            w.setLayoutDirection(Qt.LeftToRight)
            w.installEventFilter(screen)
            self.widgets[name] = w
            screen._widgets[k] = w
            w.show()

    def cell_key(self, cell: str) -> str:
        return f"r{self.rid}_{cell}"

    def column(self, cell: str) -> str:
        col = self._cellspec[cell]["col"]
        return col(self) if callable(col) else col

    def has_widget_in(self, col: str) -> bool:
        return any(self.column(n) == col for n in self.widgets)

    def choice_cells(self):
        return {n for n, c in self._cellspec.items() if c["kind"] == "choice"}

    def val(self, cell: str) -> str:
        w = self.widgets.get(cell)
        if w is None:
            return ""
        if isinstance(w, QComboBox):
            return w.currentText().strip()
        return w.text().strip()

    def set_val(self, cell: str, value):
        w = self.widgets.get(cell)
        if w is None:
            return
        if isinstance(w, QComboBox):
            w.setCurrentText(str(value or ""))
        else:
            w.setText(str(value or ""))

    def is_empty(self) -> bool:
        pk = _ROW_SPECS[self.kind].get("primary")
        if pk:
            return not self.val(pk)
        edit = [n for n, c in self._cellspec.items() if c["kind"] != "choice"]
        return not any(self.val(c) for c in edit)

    def can_delete(self) -> bool:
        return self.role == "optional"

    def sort_key(self):
        return (_SEMANTIC_ORDER.get(self.kind, 999), self.seq)

    def entry(self):
        return _ROW_SPECS[self.kind].get("to_entry", lambda _r: None)(self)

    def dispose(self):
        for cell, w in list(self.widgets.items()):
            self.screen._widgets.pop(self.cell_key(cell), None)
            w.setParent(None)
            w.deleteLater()
        self.widgets.clear()


def _titlecase(s: str) -> str:
    return re.sub(r"(^|[ \-])([^\W\d_])",
                  lambda m: m.group(1) + m.group(2).upper(), s.lower())


def _num(value) -> float:
    s = str(value or "").strip().replace(" ", "").replace(" ", "").replace(",", ".")
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _safe(text) -> str:
    out = re.sub(r"[^\w\- ]+", "", str(text or ""), flags=re.UNICODE).strip()
    return re.sub(r"\s+", "_", out) or "SN"


def _month_matches(prefix: str):
    p = prefix.upper()
    return [m for m in _MOIS_UP if m.startswith(p)]


def _resolve_month(text: str):
    t = text.strip()
    if not t:
        return None
    if t.isdigit():
        if len(t) == 1:
            return _MOIS_UP[int(t) - 1] if t in "23456789" else None
        if t in ("10", "11", "12"):
            return _MOIS_UP[int(t) - 1]
        return None
    m = _month_matches(t)
    return m[0] if len(m) == 1 else None


# ============================ لوحة الورقة ============================

class _SheetCanvas(QWidget):
    """اللوحة التي تُرسَم عليها الاستمارة (نظير ``tk.Canvas`` في الشاشة
    القديمة): ظلّ الورقة + الورقة البيضاء + الجزء الثابت المرسوم بالمليمتر
    + القيَم المحسوبة (زرقاء). حقول الإدخال ودجات أبناء لها، تُوضَع مطلقةً
    في :meth:`BulletinTemplateScreen._relayout`."""

    def __init__(self, screen: "BulletinTemplateScreen"):
        super().__init__(screen)
        self._screen = screen
        # الاستمارة فرنسية بالكامل (نصّ + أرقام) — الرسم LTR دائماً مهما
        # كان اتجاه التطبيق، وإلا انعكست التسميات والمبالغ (bidi).
        self.setLayoutDirection(Qt.LeftToRight)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QColor(theme.CANVAS_BG_HR))
        self.setPalette(pal)

    # -- أدوات رسم بوحدة المليمتر (نفس دوال template_simple.paint_form) --
    def paintEvent(self, _e):                                  # noqa: N802
        v = self._screen._view()
        x0, y0 = v.x0, v.y0
        x1, y1 = v.x0 + v.sheet_w, v.y0 + v.sheet_h
        p = QPainter(self)
        p.setLayoutDirection(Qt.LeftToRight)          # نصّ فرنسي — لا bidi
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        # ظلّ + ورقة بيضاء (نظير ui/hr/bulletin_paie.py:_paint_all)
        p.fillRect(int(x0 + 3), int(y0 + 3), int(x1 - x0), int(y1 - y0),
                   QColor(theme.PAGE_SHADOW))
        p.fillRect(int(x0), int(y0), int(x1 - x0), int(y1 - y0), QColor("white"))
        p.setPen(QColor(theme.PAGE_BORDER))
        p.drawRect(int(x0), int(y0), int(x1 - x0), int(y1 - y0))

        try:
            self._paint_form(p, v)
        except Exception:                                     # noqa: BLE001
            logger.warning("رسم الاستمارة فشل", exc_info=True)
        p.end()

    def _paint_form(self, p: QPainter, v: "_DocView"):
        scale = v.scale
        sc = self._screen
        res = sc._calc_result
        ink = QColor(theme.TEXT)
        cc = QColor(theme.COMPUTED)

        def X(mm):
            return v.x(mm)

        def Y(mm):
            return v.y(mm)

        def col_x(frac):
            return v.x(frac * T.CONTENT_W)

        def font(mm_h, bold=False):
            return v.font(mm_h, bold)

        def base_text(mm_x, baseline_mm, s, f, color=ink):
            p.setFont(f)
            p.setPen(color)
            p.drawText(QPoint(int(X(mm_x)), int(Y(baseline_mm))), s)

        # رأس المكتب — تسمية N° ADHÉRENT ثابتة (الرقم حقلٌ حيّ)
        base_text(0, T.ADHERENT_BASELINE, "N° ADHÉRENT", font(3.4, True))

        # شريط العنوان الأسود
        p.fillRect(int(X(0)), int(Y(T.BAND_TITLE_Y)),
                   int(X(T.CONTENT_W) - X(0)), int(Y(T.BAND_TITLE_H) - Y(0)),
                   QColor(theme.BAND_BLACK))
        base_text(3, T.BAND_BASELINE, "BULLETIN DE PAIE", font(5.0, True),
                  QColor("white"))

        # صندوق الهوية + تسمياته (القيَم حقول حيّة) — إيقاع عمودي مُعاير
        p.setPen(ink)
        p.drawRect(int(X(0)), int(Y(T.IDENT_Y)),
                   int(X(T.CONTENT_W) - X(0)), int(sc._ident_h(scale) * scale))
        for _k, lbl, xl, xv, wv, row, _ml, kind in T.IDENT_FIELDS:
            if lbl:
                base_text(xl, sc._ident_row_y(row, scale), f"{lbl} :",
                          font(3.2, True))
        a_x, _lieu_x = sc._row1_layout(scale)
        base_text(a_x, sc._ident_row_y(1, scale), "à", font(3.2, True))

        # كتلة الجدول مُزاحة لأسفل بمقدار توسيع منطقة الهوية
        ys = sc._y_shift(scale)

        def Yt(mm):
            return Y(mm + ys)

        # ---- جسم الجدول: صفوف ديناميكية (Phase A2) ----
        rows = sc._visible_body_rows()
        nb = len(rows)
        bottom_mm = T.BODY_TOP + nb * T.ROW_H
        total_mm = bottom_mm + 1.0
        net_mm = total_mm + T.ROW_H + 4.0

        # ترويسة الجدول + الأعمدة (تمتدّ لآخر صفّ فعليّ)
        hy0, hy1 = Yt(T.TABLE_HEAD_Y), Yt(T.TABLE_HEAD_Y + T.ROW_H + 1)
        p.setPen(ink)
        p.drawRect(int(X(0)), int(hy0), int(X(T.CONTENT_W) - X(0)), int(hy1 - hy0))
        for _key, f0, _f1, _al, title in T.COLS:
            p.setPen(ink)
            p.drawLine(int(col_x(f0)), int(hy0), int(col_x(f0)), int(Yt(bottom_mm)))
            p.setFont(font(3.0, True))
            fm = QFontMetricsF(p.font())
            p.drawText(QPoint(int(col_x(f0) + 2.5 * scale),
                              int((hy0 + hy1) / 2 + fm.ascent() / 2 - fm.descent() / 2)),
                       title)
        p.setPen(ink)
        p.drawLine(int(X(T.CONTENT_W)), int(hy0), int(X(T.CONTENT_W)), int(Yt(bottom_mm)))

        p.setPen(QColor(theme.GRID_LINE))
        for r in range(nb + 1):
            yy = Yt(T.BODY_TOP + r * T.ROW_H)
            p.drawLine(int(X(0)), int(yy), int(X(T.CONTENT_W)), int(yy))

        def row_mid(i):
            return T.BODY_TOP + i * T.ROW_H + T.ROW_H / 2

        def cell(col_key, i, s, anchor, color=ink, bold=False):
            f0, f1, _al = T._colf(col_key)
            if anchor == "c":
                px = (col_x(f0) + col_x(f1)) / 2
            elif anchor == "e":
                px = col_x(f1) - 2.5 * scale
            else:
                px = col_x(f0) + 2.5 * scale
            self._cell(p, px, Yt(row_mid(i)),
                       s, {"c": "center", "e": "e", "w": "w"}[anchor],
                       font(3.2, bold), color)

        computed = res is not None and getattr(sc, "_computed", False)
        for i, row in enumerate(rows):
            # code / libellé ثابتان يُرسمان فقط حين لا widget يشغل العمود
            if row.code and not row.has_widget_in("code"):
                cell("code", i, row.code, "c")
            if row.libelle and not row.has_widget_in("libelle"):
                cell("libelle", i, row.libelle, "w")
            if row.kind == "cnas" and computed:
                cell("nbase", i, fmt_montant(res.base_cnas), "e", cc)
                cell("taux", i, "9,00", "e", cc)
                cell("retenue", i, fmt_montant(res.retenue_cnas), "e", cc)
            elif row.kind == "irg" and computed:
                cell("nbase", i, fmt_montant(res.base_irg), "e", cc)
                cell("retenue", i, fmt_montant(res.retenue_irg), "e", cc)
            else:
                # المبلغ المحسوب (IEP/Absence/Retard/HS) — خلية للقراءة، تُرسَم
                # من BulletinView. لا تُرسَم «0,00» إن لم يكن الحساب ممكناً.
                spec = _ROW_SPECS[row.kind]
                col = spec.get("computed")
                if col and computed and row._amount is not None:
                    amt = -row._amount if spec.get("computed_neg") else row._amount
                    cell(col, i, fmt_montant(amt), "e", cc)

        # لا تُرسَم TOTAL/NET كـ«0,00» إذا كان الحساب غير ممكن — «غير محسوبة»
        # ≠ «صفر حقيقي».
        if computed:
            ty0 = Yt(total_mm)
            p.setPen(ink)
            p.drawLine(int(X(0)), int(ty0), int(X(T.CONTENT_W)), int(ty0))
            p.drawLine(int(X(0)), int(Yt(total_mm + T.ROW_H)),
                       int(X(T.CONTENT_W)), int(Yt(total_mm + T.ROW_H)))
            mid = Yt(total_mm + T.ROW_H / 2)
            self._cell(p, col_x(T._colf("taux")[1]) - 3 * scale, mid, "TOTAL",
                       "e", font(3.4, True), ink)
            self._cell(p, col_x(T._colf("gain")[1]) - 2.5 * scale, mid,
                       fmt_montant(res.total_gain), "e", font(3.4, True), cc)
            self._cell(p, col_x(T._colf("retenue")[1]) - 2.5 * scale, mid,
                       fmt_montant(res.total_retenue), "e", font(3.4, True), cc)

            self._cell(p, col_x(0.60), Yt(net_mm + 5), "NET À PAYER", "e",
                       font(4.2, True), ink)
            p.fillRect(int(col_x(0.62)), int(Yt(net_mm)),
                       int(X(T.CONTENT_W) - col_x(0.62)),
                       int(Yt(net_mm + 10) - Yt(net_mm)), QColor(theme.BAND_BLACK))
            self._cell(p, X(T.CONTENT_W - 3), Yt(net_mm + 5),
                       fmt_montant(res.net_a_payer), "e", font(4.8, True),
                       QColor("white"))

    @staticmethod
    def _cell(p: QPainter, px, py, s, anchor, f: QFont, color: QColor):
        p.setFont(f)
        p.setPen(color)
        fm = QFontMetricsF(f)
        vy = py + fm.ascent() / 2 - fm.descent() / 2
        w = fm.horizontalAdvance(s)
        if anchor == "e":
            p.drawText(QPoint(int(px - w), int(vy)), s)
        elif anchor == "center":
            p.drawText(QPoint(int(px - w / 2), int(vy)), s)
        else:
            p.drawText(QPoint(int(px), int(vy)), s)


# ============================ الشاشة ============================

class BulletinTemplateScreen(Screen):
    """كشف الراتب الشهري — نفس شاشة ``ui/hr/bulletin_paie.py`` بإطار
    PySide6. تُبنى فوق :class:`ui2.screen.Screen` لكنها تخفي شريط أدواته
    (لا شريط في التصميم القديم — كل شيء في الشريط الجانبي)."""

    TITLE = "كشف راتب شهري"
    DOC_LABEL = "Bulletin de paie"
    OUTPUT_DIRNAME = "Bulletins de paie"
    DRAFT_NAME = "paie_template"
    DRAFT_VERSION = 4          # Phase A2.3: خلايا choice + iep_manual

    TARGET_W = 720
    ZOOM_MIN, ZOOM_MAX, ZOOM_STEP, ZOOM_DEFAULT = 30, 260, 20, 100
    MARGIN = 18

    def __init__(self, conn=None, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._template_key = registry.DEFAULT_TEMPLATE_KEY
        self.zoom = self.ZOOM_DEFAULT
        self._cfg = None
        self._mode = "walkin"

        self._ident_row = {f"id_{k}": row
                           for k, _l, _xl, _xv, _wv, row, _ml, _kd in T.IDENT_FIELDS}
        # خانات جسم الجدول القديمة (ثابتة) لم تعد تُبنى من FIELD_SLOTS —
        # جسم الجدول الآن نموذج صفوف ديناميكي (_rows). نُبقي خانات
        # الترويسة/الهوية/الشريط فقط.
        self._body_slot_keys = (
            {"jours", "salaire_base", "panier", "transport"}
            | {f"prime{k}_{c}" for k in range(T.N_PRIME_SLOTS)
               for c in ("code", "lib", "montant")}
            | {f"autre{k}_{c}" for k in range(T.N_AUTRE_SLOTS)
               for c in ("code", "lib", "montant")})
        self._header_slots = [s for s in T.FIELD_SLOTS
                              if s.key not in self._body_slot_keys]
        self._slots_by_key = {s.key: s for s in self._header_slots}
        self._band_keys = {s.key for s in self._header_slots if s.on_band}
        self._nav_order = []                   # يُعاد بناؤه في _rebuild_nav
        self._widgets = {}                     # key -> QLineEdit / DateField / GroupedNumberEdit / row cell
        self._suspend = set()
        self._prev_text = {}                   # آخر نصّ لكلّ حقل (لتمييز الكتابة عن التحرير)
        self._rows = []                        # List[_Row] — جسم الجدول الديناميكي
        self._row_seq = 0
        self._next_rid = 1

        # ---- تحقّق مرن (Phase B) ----
        self._validation = None                # validation.ValidationResult
        self._warnings_active = False          # عرض تحذيرات الإلزاميّ (§6)
        self._restored_incomplete = False      # مسوّدة محفوظة كـ«غير مكتملة» (Phase C)

        # ---- دورة حياة العمل (Phase C) ----
        self._work_id = None                   # معرّف hr_documents المستقرّ (None = لم يُحفَظ)
        self._work_state = None                # None | "incomplete" | "final"
        self._locked = False                   # 🔒 — المدخلات للقراءة فقط
        self._has_final_artifacts = False      # وُلِّدت DOCX/PDF نهائيّان مرّةً
        self._final_docx = None
        self._final_pdf = None

        self._calc_input = calc.PaieInput()
        self._calc_result = calc.compute(self._calc_input, self._load_cfg())
        self._bulletin_view = None                      # lignes.BulletinView (المحرّك)
        self._computed = False                 # نتيجة حقيقية مقابل «غير محسوبة»

        self.build_ui()
        self.toolbar.setVisible(False)         # لا شريط أدوات في التصميم القديم
        self._build_fields()
        self._init_default_rows()
        self._rebuild_nav()
        self.on_activate()
        QTimer.singleShot(0, self._relayout)
        self._recompute()
        self._dirty = False        # بناء الشاشة الافتراضية ليس «تعديل مستخدم»

    # ======================= نموذج الصفوف (Phase A2) =======================
    def _init_default_rows(self):
        for kind in ("salaire", "prime", "panier", "transport", "cnas", "irg"):
            self._rows.append(_Row(self, kind, self._next_rid))
            self._next_rid += 1
        self._widgets["r%d_nbase" % self._rows[0].rid].setText("30")  # jours

    def _ordered_rows(self):
        return sorted(self._rows, key=lambda r: r.sort_key())

    def _visible_body_rows(self):
        """الصفوف بترتيبها الدلاليّ — CNAS/IRG دائماً بعد panier/transport."""
        return self._ordered_rows()

    def _row_index(self, row) -> int:
        return self._visible_body_rows().index(row)

    def _add_row(self, kind: str):
        if self._locked:                          # 🔒 — لا تعديل بنية
            return
        if len([r for r in self._rows if r.role != "system"]) + 2 >= _MAX_BODY_ROWS:
            from ui2.alerts import warn
            warn(self, self.TITLE,
                 ["بلغ الجدول الحدّ الأقصى للصفوف — احذف صفاً قبل الإضافة."])
            return
        r = _Row(self, kind, self._next_rid)
        self._next_rid += 1
        self._rows.append(r)
        self._rebuild_nav()
        self._sync_row_styles()
        self.mark_dirty()
        self._recompute()
        self._relayout()
        # ركّز أوّل خلية قابلة للتحرير في الصف الجديد
        cells = _ROW_SPECS[kind]["cells"]
        if cells:
            self._widgets[r.cell_key(cells[0]["name"])].setFocus()

    def _remove_row(self, row: "_Row"):
        if self._locked or not row.can_delete() or row not in self._rows:
            return
        if not row.is_empty() and not confirm(
                self, "حذف السطر", "هذا السطر يحتوي بيانات — حذفه؟"):
            return
        row.dispose()
        self._rows.remove(row)
        self._rebuild_nav()
        self.mark_dirty()
        self._recompute()
        self._relayout()

    def _rebuild_nav(self):
        """ترتيب Tab/Enter من النموذج الفعليّ: خانات الترويسة، ثم خلايا
        صفوف الجسم القابلة للتحرير بترتيبها الدلاليّ. لا يمرّ على خلايا
        النظام/المحسوبة."""
        nav = [s.key for s in self._header_slots]
        for r in self._visible_body_rows():
            for cell in _ROW_SPECS[r.kind]["cells"]:
                nav.append(r.cell_key(cell["name"]))
        self._nav_order = nav
        # سلسلة Tab أصلية مطابقة (بلا references ميتة)
        prev = None
        for k in nav:
            w = self._widgets.get(k)
            if w is None:
                continue
            if prev is not None:
                self.setTabOrder(prev, w)
            prev = w

    # ----------------------- خطاطيف Screen -----------------------
    def build_body(self):
        split = QSplitter(Qt.Horizontal, self)
        split.setLayoutDirection(Qt.LeftToRight)   # اللوحة يساراً، الشريط يميناً (كالقديم)

        self._canvas = _SheetCanvas(self)
        self._scroll = QScrollArea(split)
        self._scroll.setWidget(self._canvas)
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignCenter)
        self._scroll.viewport().setStyleSheet(
            f"background:{theme.CANVAS_BG_HR};")
        split.addWidget(self._scroll)

        split.addWidget(self._build_sidebar())
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setSizes([self.TARGET_W + 80, 240])
        return split

    def _build_sidebar(self):
        sb = QWidget()
        lay = QVBoxLayout(sb)
        lay.setContentsMargins(theme.SPACE["md"], theme.SPACE["md"],
                               theme.SPACE["md"], theme.SPACE["md"])
        lay.setSpacing(theme.SPACE["sm"])

        ttl = QLabel(self.TITLE)
        ttl.setStyleSheet(f"font-size:{theme.FONT_SIZES['card']}pt; font-weight:700;")
        lay.addWidget(ttl)
        sub = QLabel(self.DOC_LABEL)
        sub.setStyleSheet(f"color:{theme.TEXT_DIM};")
        lay.addWidget(sub)

        zb = QHBoxLayout()
        b_out = QPushButton("−")
        b_out.setFixedWidth(32)
        b_out.clicked.connect(self.zoom_out)
        self._zoom_lbl = QLabel("100%")
        self._zoom_lbl.setAlignment(Qt.AlignCenter)
        self._zoom_lbl.setFixedWidth(52)
        b_in = QPushButton("+")
        b_in.setFixedWidth(32)
        b_in.clicked.connect(self.zoom_in)
        b_fit = QPushButton("ملاءمة")
        b_fit.clicked.connect(self.fit_to_window)
        for w in (b_out, self._zoom_lbl, b_in, b_fit):
            zb.addWidget(w)
        lay.addLayout(zb)

        mf = QLabel("الموديل: " + registry.get_template(self._template_key).label)
        mf.setWordWrap(True)
        lay.addWidget(mf)

        cf = QFrame()
        cf.setFrameShape(QFrame.StyledPanel)
        cl = QVBoxLayout(cf)
        cl.addWidget(QLabel("الزبون"))
        self._rb_reg = QRadioButton("زبون مسجّل")
        self._rb_walk = QRadioButton("زبون عابر")
        self._rb_walk.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self._rb_reg)
        grp.addButton(self._rb_walk)
        self._rb_reg.toggled.connect(self._on_mode_change)
        cl.addWidget(self._rb_reg)
        cl.addWidget(self._rb_walk)
        self._client_combo = QComboBox()
        self._client_combo.setVisible(False)
        cl.addWidget(self._client_combo)
        lay.addWidget(cf)

        # ---- + Ajouter (قائمة منتَج مبسَّطة فوق lignes) ----
        add_btn = QPushButton("＋ Ajouter")
        self._add_menu = QMenu(self)
        for label, kind in _AJOUTER_MENU:
            self._add_menu.addAction(label,
                                     lambda k=kind: self._add_row(k))
        add_btn.setMenu(self._add_menu)
        self._add_btn = add_btn
        lay.addWidget(add_btn)

        hint = QLabel("تصنيف كلّ Prime (CNAS/IRG) داخل سطرها.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{theme.TEXT_DIM};")
        lay.addWidget(hint)

        # مؤشّر «⚠️ غير مكتمل» (§13) — يظهر فقط بعد محاولة الإصدار النهائي
        # أو استعادة عمل محفوظ كـ«غير مكتمل». هادئ، بلا صندوق حوار.
        self._incomplete_lbl = QLabel("")
        self._incomplete_lbl.setWordWrap(True)
        self._incomplete_lbl.setStyleSheet(
            f"color:{theme.WARNING}; font-weight:700;")
        self._incomplete_lbl.setVisible(False)
        lay.addWidget(self._incomplete_lbl)

        bf = QFrame()
        bf.setFrameShape(QFrame.StyledPanel)
        bl = QVBoxLayout(bf)
        self._save_btn = QPushButton("💾 حفظ")
        self._save_btn.clicked.connect(self._on_save)
        bl.addWidget(self._save_btn)
        for txt, fn in (("توليد Word", lambda: self._on_generate("docx")),
                        ("توليد PDF", lambda: self._on_generate("pdf")),
                        ("السجلّ", self._on_history),
                        ("مسح", self._on_clear)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            bl.addWidget(b)
        lay.addWidget(bf)

        leg = QLabel("أبيض = يُملأ يدوياً · أزرق = يُحسب تلقائياً · "
                     "أسود = جزء ثابت من الاستمارة.")
        leg.setWordWrap(True)
        leg.setStyleSheet(f"color:{theme.TEXT_DIM};")
        lay.addWidget(leg)
        lay.addStretch(1)
        return sb

    def shortcuts(self):
        return {}

    # المسوّدة (DRAFT_VERSION = 3: نموذج صفوف ديناميكيّ)
    def _hdr_val(self, w):
        if isinstance(w, DateField):
            return w.iso()
        if isinstance(w, GroupedNumberEdit):
            return w.value()
        return w.text()

    def draft_state(self):
        #  ``incomplete``: علمٌ استرشاديّ (Phase B) — التمييز بين مسوّدة
        #  تلقائية وعملٍ محفوظ رسمياً كـ«غير مكتمل» يحتاج دورة حياة الحفظ
        #  (Phase C)؛ نُخزّنه فقط، ولا نُفعّل به تحذيرات عند الاستعادة.
        v = self._validation
        return {
            "header": {s.key: self._hdr_val(self._widgets[s.key])
                       for s in self._header_slots},
            "rows": [{"kind": r.kind,
                      "cells": {c: r.val(c) for c in r.widgets},
                      "iep_manual": r._iep_manual}
                     for r in self._rows],
            "incomplete": bool(v is not None and v.is_incomplete),
        }

    def apply_draft(self, data):
        data = data or {}
        # Phase B: نُسجّل العلم فقط. الاستعادة التلقائية للمسوّدة أثناء
        # الكتابة لا تُظهر تحذيرات الإلزاميّ (§14)؛ تفعيلها عند فتح عملٍ
        # محفوظ رسمياً كـ«غير مكتمل» = Phase C عبر ``show_required_warnings``.
        self._restored_incomplete = bool(data.get("incomplete"))
        self._suspend = set(self._widgets)
        try:
            for k, v in data.get("header", {}).items():
                w = self._widgets.get(k)
                if w is None:
                    continue
                if isinstance(w, DateField):
                    w.set_iso(v)
                elif isinstance(w, GroupedNumberEdit):
                    w.set_value(v)
                else:
                    w.setText(str(v or ""))
            # إعادة بناء الصفوف من المسوّدة
            for r in list(self._rows):
                r.dispose()
            self._rows.clear()
            for spec in data.get("rows", []):
                kind = spec.get("kind")
                if kind not in _ROW_SPECS:
                    continue
                r = _Row(self, kind, self._next_rid)
                self._next_rid += 1
                self._rows.append(r)
                for c, val in (spec.get("cells") or {}).items():
                    r.set_val(c, val)
                r._iep_manual = bool(spec.get("iep_manual"))
            for kind in ("salaire", "panier", "transport", "cnas", "irg"):
                if not any(r.kind == kind for r in self._rows):
                    self._rows.append(_Row(self, kind, self._next_rid))
                    self._next_rid += 1
            self._prev_text.clear()
        finally:
            self._suspend = set()
        self._rebuild_nav()
        for k in list(self._widgets):
            self._style_field(k)
        self._recompute()
        self._relayout()

    def is_empty(self):
        hdr = any(str(self._hdr_val(self._widgets[s.key])).strip()
                  for s in self._header_slots if s.key not in ("mois", "annee"))
        rows = any(not r.is_empty() for r in self._rows if r.role != "system")
        return not (hdr or rows)

    # ----------------------- بناء الحقول -----------------------
    def _build_fields(self):
        today = date.today()
        # الشهر والسنة يبدآن **فارغين**. جسم الجدول لم يعد من FIELD_SLOTS
        # (نموذج صفوف ديناميكي) — نبني خانات الترويسة/الهوية/الشريط فقط.
        defaults = {}
        for slot in self._header_slots:
            if slot.kind == "date_masked":
                # DateField الموحّد: عرض dd/MM/yyyy، تخزين ISO، مسطّح،
                # خطأ سطري، ولا تاريخ مستقبلي (max = اليوم لكلا الحقلين §8).
                w = DateField(display_format="dd/MM/yyyy", nullable=True,
                              flat=True, max_date=today, inline_error=False,
                              parent=self._canvas)
                w.dateChanged.connect(lambda _d, k=slot.key: self._on_slot_write(k))
                w.errorChanged.connect(self._refresh_date_errors)
                w.completed.connect(lambda k=slot.key: self._focus_rel(k, +1, select=False))
            elif slot.kind in ("adherent", "num_ss"):
                # حقول رقمية مجمَّعة (reusable): N° ADHÉRENT «xx xxx xxx xx»
                # · N° SS «xx xxxx xxxx xx» أو «xx xxxx xxxx /xx».
                if slot.kind == "adherent":
                    w = GroupedNumberEdit([2, 3, 3, 2], parent=self._canvas)
                else:
                    w = GroupedNumberEdit([2, 4, 4, 2], key_sep="/",
                                          parent=self._canvas)
                w.setFrame(False)
                al = {"r": Qt.AlignRight, "c": Qt.AlignHCenter,
                      "l": Qt.AlignLeft}[slot.align]
                w.setAlignment(al | Qt.AlignVCenter)
                w.textEdited.connect(lambda _t, k=slot.key: self._on_slot_write(k))
                w.completed.connect(lambda k=slot.key: self._focus_rel(k, +1, select=False))
            else:
                w = QLineEdit(defaults.get(slot.key, ""), self._canvas)
                w.setFrame(False)
                al = {"r": Qt.AlignRight, "c": Qt.AlignHCenter,
                      "l": Qt.AlignLeft}[slot.align]
                w.setAlignment(al | Qt.AlignVCenter)
                w.setMaxLength(slot.maxlen)
                w.textChanged.connect(lambda _t, k=slot.key: self._on_slot_write(k))
                w.returnPressed.connect(lambda k=slot.key: self._focus_rel(k, +1))
            w.setLayoutDirection(Qt.LeftToRight)
            self._widgets[slot.key] = w
            w.show()
        for k in self._widgets:
            self._style_field(k)
        # §8: تاريخ بداية العمل > تاريخ الميلاد (وكلاهما ≤ اليوم — مضبوط
        # عبر max_date). القاعدة على حقل الدخول؛ تغيّر الميلاد يُعيد فحصه.
        self._widgets["id_date_embauche"].set_extra_check(self._check_entree)
        # Ctrl+عجلة يعمل حتى فوق أيّ حقل (لا يبتلعه الحقل) + حدّ تركيز واضح.
        self._canvas.installEventFilter(self)
        self._scroll.viewport().installEventFilter(self)
        for w in self._canvas.findChildren(QWidget):
            w.installEventFilter(self)

    def _refresh_date_errors(self, *_a):
        msgs = []
        for k, lbl in (("id_date_naissance", "تاريخ الميلاد"),
                       ("id_date_embauche", "تاريخ بداية العمل")):
            w = self._widgets.get(k)
            txt = w.error_text() if isinstance(w, DateField) else ""
            if txt:
                msgs.append(f"{lbl}: {txt}")
        if msgs:
            self.warnbar.setText(" • ".join(msgs))
            self.warnbar.show()
        else:
            self.warnbar.setText("")
            self.warnbar.hide()
        self._relayout()

    # ----------------------- الحالة العائلية (Hybrid) -----------------------
    def _popup_famille(self, key, widget):
        menu = QMenu(self)
        for code, label in _FAMILLE_CHOICES:
            menu.addAction(f"{code} — {label}",
                           lambda c=code, k=key: self._pick_famille(k, c))
        menu.addSeparator()
        menu.addAction("—  (تفريغ)", lambda k=key: self._pick_famille(k, ""))
        menu.exec(widget.mapToGlobal(widget.rect().bottomLeft()))

    def _pick_famille(self, key, code):
        w = self._widgets[key]
        self._suspend.add(key)
        w.setText(code)
        self._suspend.discard(key)
        self._style_field(key)
        self.mark_dirty()
        self._recompute()
        if code:
            self._focus_rel(key, +1, select=False)     # انتقال تلقائي — بلا تحديد

    def _birth_pydate(self):
        iso = self._widgets["id_date_naissance"].iso()
        try:
            return date.fromisoformat(iso) if iso else None
        except ValueError:
            return None

    def _check_entree(self, d):
        nb = self._birth_pydate()
        if nb is not None and d <= nb:
            return "تاريخ بداية العمل يجب أن يكون بعد تاريخ الميلاد."
        return None

    # ----------------------- الزوم والتخطيط -----------------------
    def _view(self) -> _DocView:
        """التحويل الحالي وثيقة→لوحة (يُعاد حسابه عند كلّ رسم/تخطيط)."""
        vp = self._scroll.viewport() if hasattr(self, "_scroll") else None
        cw = max(vp.width(), 1) if vp is not None else 1
        ch = max(vp.height(), 1) if vp is not None else 1
        sheet_w = self.TARGET_W * self.zoom / 100.0
        scale = sheet_w / 210.0
        sheet_h = scale * 297.0
        x0 = max((cw - sheet_w) / 2, self.MARGIN)
        y0 = self.MARGIN
        return _DocView(x0, y0, scale, sheet_w, sheet_h, cw, ch)

    def _page_box(self):
        v = self._view()
        return ((v.x0, v.y0, v.x0 + v.sheet_w, v.y0 + v.sheet_h),
                v.scale, v.cw, v.ch)

    def _row1_layout(self, scale):
        """موضعا «à» وحقل المكان في سطر تاريخ الميلاد — **بالمليمتر خالصاً**
        (لا قياس خطّ بكسل يتسرّب إلى تخطيط الوثيقة). حقل التاريخ = عرض نصّه
        + زرّ التقويم، ثمّ «à»، ثمّ حقل المكان."""
        date_w_mm = 20.0 + _DATE_BTN_MM          # عرض DateField لسطر الميلاد
        a_x = T._VAL_L + date_w_mm + 3.0
        lieu_x = a_x + 3.0 + 3.0
        return a_x, lieu_x

    # --- معايرة الإيقاع العمودي لمنطقة الهوية (الشاشة الجديدة فقط) ---
    def _ident_extra_mm(self, scale):
        return _IDENT_ROW_EXTRA_PX / scale

    def _ident_row_y(self, r, scale):
        """نظير ``template_simple._ident_row_y`` بفجوة أوسع قليلاً لتقارب
        إيقاع الأصل بصرياً (لا يُلمَس الثابت المشترك)."""
        return T.IDENT_Y + 9.0 + r * (9.0 + self._ident_extra_mm(scale))

    def _y_shift(self, scale):
        """مجموع الزيادة عبر فجوات صفوف الهوية الأربع — تُزاح به كتلة
        الجدول (ترويسة/أسطر/TOTAL/NET) لأسفل."""
        return 4 * self._ident_extra_mm(scale)

    def _ident_h(self, scale):
        return T.IDENT_H + self._y_shift(scale)

    # --- هندسة جسم الجدول الديناميكي (تُحسب من عدد الصفوف الفعليّ) ---
    def _n_body(self):
        return len(self._visible_body_rows())

    def _body_bottom_mm(self):
        return T.BODY_TOP + self._n_body() * T.ROW_H

    def _total_y_mm(self):
        return self._body_bottom_mm() + 1.0

    def _net_y_mm(self):
        return self._total_y_mm() + T.ROW_H + 4.0

    def _sheet_content_mm(self):
        """أدنى امتداد رأسيّ يلزم لاحتواء الوثيقة (لضبط طول اللوحة)."""
        return self._net_y_mm() + 14.0

    def _set_zoom(self, pct):
        self.zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, int(round(pct))))
        self._zoom_lbl.setText(f"{self.zoom}%")
        self._relayout()

    def zoom_in(self):
        self._set_zoom(((self.zoom // self.ZOOM_STEP) + 1) * self.ZOOM_STEP)

    def zoom_out(self):
        self._set_zoom((-(-self.zoom // self.ZOOM_STEP) - 1) * self.ZOOM_STEP)

    def fit_to_window(self):
        cw = max(self._scroll.viewport().width() - 2 * self.MARGIN, 100)
        ch = max(self._scroll.viewport().height() - 2 * self.MARGIN, 100)
        by_w = cw / self.TARGET_W
        by_h = ch / (self.TARGET_W * 297.0 / 210.0)
        self._set_zoom(min(by_w, by_h) * 100)

    def resizeEvent(self, e):                                 # noqa: N802
        super().resizeEvent(e)
        self._relayout()

    # ---- زوم بعجلة الفأرة + Ctrl (يشارك نفس zoom state ومؤشّره) ----
    def _zoom_wheel(self, ev):
        step = self.ZOOM_STEP if ev.angleDelta().y() > 0 else -self.ZOOM_STEP
        new_zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self.zoom + step))
        if new_zoom == self.zoom:
            return
        gp = ev.globalPosition().toPoint()
        v0 = self._view()
        # نقطة الوثيقة (مليمتر) تحت المؤشّر قبل الزوم
        cpt = self._canvas.mapFromGlobal(gp)
        mm_x = (cpt.x() - v0.x0) / v0.scale - T.MARGIN_L
        mm_y = (cpt.y() - v0.y0) / v0.scale
        cur_vp = self._scroll.viewport().mapFromGlobal(gp)
        self._set_zoom(new_zoom)                          # يعيد التخطيط
        v1 = self._view()
        # اجعل نفس نقطة الوثيقة تبقى تحت المؤشّر (Cursor-anchored)
        new_cx = v1.x0 + (T.MARGIN_L + mm_x) * v1.scale
        new_cy = v1.y0 + mm_y * v1.scale
        self._scroll.horizontalScrollBar().setValue(int(new_cx - cur_vp.x()))
        self._scroll.verticalScrollBar().setValue(int(new_cy - cur_vp.y()))

    def _key_of_edit(self, obj):
        for k, w in self._widgets.items():
            if w is obj or getattr(w, "_edit", None) is obj:
                return k
        return None

    def eventFilter(self, obj, ev):                       # noqa: N802 (Qt)
        t = ev.type()
        if t == QEvent.Wheel:
            if ev.modifiers() & Qt.ControlModifier:
                self._zoom_wheel(ev)                      # Ctrl+عجلة → زوم الوثيقة
                return True
            return False                                  # عجلة عادية → تمرير طبيعي
        if t in (QEvent.FocusIn, QEvent.FocusOut) and isinstance(obj, QLineEdit):
            k = self._key_of_edit(obj)
            if k:
                self._style_field(k)                      # حدّ التركيز واضح (B)
            if t == QEvent.FocusOut:
                obj.deselect()                            # لا تظليل بعد المغادرة
        if t == QEvent.MouseButtonPress:
            k = self._key_of_edit(obj)
            if k and self._slots_by_key.get(k) and \
                    self._slots_by_key[k].kind == "famille":
                self._popup_famille(k, obj)
        return super().eventFilter(obj, ev)

    def _relayout(self):
        if not hasattr(self, "_canvas"):
            return
        v = self._view()
        self._canvas.setFixedSize(
            int(max(v.x0 + v.sheet_w + self.MARGIN, v.cw)),
            int(max(v.y0 + v.sheet_h + self.MARGIN, v.ch)))
        chrome = v.px(_ENTRY_CHROME_MM)
        for slot in self._header_slots:
            w = self._widgets[slot.key]
            f = v.font(slot.font_mm, slot.bold)
            w.setFont(f)
            fm = QFontMetricsF(f)

            x_mm = slot.x_mm
            if slot.key == "id_lieu_naissance":
                x_mm = self._row1_layout(v.scale)[1]

            # ---- عمودياً ----
            if slot.key in self._ident_row:
                ref_mm = self._ident_row_y(self._ident_row[slot.key], v.scale)
                top_px = v.y(ref_mm) - fm.ascent() - chrome
                h_px = int(fm.height() + 2 * chrome)
            elif slot.baseline_mm is not None:
                top_px = v.y(slot.baseline_mm) - fm.ascent() - chrome
                h_px = int(fm.height() + 2 * chrome)
            else:                                          # خانة جدول — مُزاحة لأسفل
                top_px = v.y(slot.y_mm + self._y_shift(v.scale))
                h_px = int(v.px(T.ROW_H - 0.8))

            # ---- عرضاً (كلّه بالمليمتر ثمّ يُحوَّل — لا ثابت بكسل) ----
            if isinstance(w, DateField):
                btn_px = v.px(_DATE_BTN_MM)
                w_px = int(v.px(slot.w_mm) + btn_px)
                w.set_row_geom(h_px, btn_px)              # ارتفاع الحقل = بقيّة الصفّ
                w.setFixedWidth(max(w_px, 12))
                w.move(int(v.x(x_mm)), int(top_px))
                continue
            if getattr(slot, "fit_maxlen", False) or isinstance(
                    w, GroupedNumberEdit):
                cur = w.text()
                w_px = int(max(fm.horizontalAdvance("0" * max(slot.maxlen, 10)),
                               fm.horizontalAdvance(cur)) + v.px(_FIT_PAD_MM))
            else:
                w_px = int(v.px(slot.w_mm))

            w.setFixedWidth(max(w_px, 12))
            w.setFixedHeight(max(h_px, 12))
            w.move(int(v.x(x_mm)), int(top_px))

        # ---- خلايا صفوف الجسم الديناميكية ----
        ys = self._y_shift(v.scale)
        f_row = v.font(3.2, True)
        h_row = int(v.px(T.ROW_H - 0.8))
        for i, row in enumerate(self._visible_body_rows()):
            top_mm = T.BODY_TOP + i * T.ROW_H + 0.7 + ys
            for cell, w in row.widgets.items():
                # خلية «classe» في «Autre» تظهر فقط حين sens = Gain
                if row.kind == "autre" and cell == "classe":
                    w.setVisible(row.val("sens") == "Gain")
                x_mm, _y0, w_mm = T._cell_mm(row.column(cell), 0)
                w.setFont(f_row)
                w.setFixedWidth(max(int(v.px(w_mm)), 12))
                w.setFixedHeight(max(h_row, 12))
                w.move(int(v.x(x_mm)), int(v.y(top_mm)))
        self._canvas.update()

    # ----------------------- المظهر (كريمي/أبيض/شريط) -----------------------
    def _field_value(self, key):
        w = self._widgets[key]
        if isinstance(w, DateField):
            return w.iso()
        if isinstance(w, QComboBox):
            return w.currentText().strip()
        return w.text().strip()

    def _warns(self, key) -> bool:
        """هل على هذا الحقل تحذير إلزاميّ نشِط الآن؟ (§7: حدّ خفيف، بلا
        صندوق حوار؛ يزول فور تصحيح الحقل لأنّ ``_validation`` تُحدَّث)."""
        return (self._warnings_active and self._validation is not None
                and key in self._validation.keys())

    def _style_field(self, key):
        w = self._widgets[key]
        warn = self._warns(key)
        if isinstance(w, (DateField, QComboBox)):
            if isinstance(w, DateField):
                w.refresh_style()             # DateField/Combo يديران نمطهما
                if warn and not w.error_text():
                    # حدّ تحذير خفيف فوق نمط DateField — آخر قاعدة QLineEdit
                    # تفوز في Qt، ويُعيده refresh_style في الاستدعاء التالي.
                    w._edit.setStyleSheet(
                        w._edit.styleSheet()
                        + f"\nQLineEdit{{border:1px solid {theme.WARNING};}}")
            return
        filled = bool(self._field_value(key))
        if key in self._band_keys:
            focused = w.hasFocus()
            if focused:
                bg, fg, bd = theme.SURFACE, "#000000", theme.HOVER
            elif filled:
                bg, fg, bd = theme.BAND_BLACK, "#ffffff", theme.BAND_BLACK
            else:
                bg, fg, bd = theme.FIELD_EMPTY, "#000000", "#ffffff"
        else:
            bg = theme.SURFACE if filled else theme.FIELD_EMPTY
            fg = theme.TEXT
            bd = theme.HOVER if w.hasFocus() else "#ffffff"
        if warn:
            bd = theme.WARNING                # التحذير يعلو لون الحدّ العاديّ
        w.setStyleSheet(
            f"QLineEdit {{ background:{bg}; color:{fg}; border:1px solid {bd}; "
            f"border-radius:0; padding:0 1px; "
            f"selection-background-color:{theme.PRIMARY}; "
            f"selection-color:#ffffff; }}")            # تظليل ويندوز المعتاد
        # لون النصّ صريح من QPalette، والتحديد يُعتّمه Qt عند فقد التركيز.
        pal = w.palette()
        pal.setColor(QPalette.Text, QColor(fg))
        pal.setColor(QPalette.WindowText, QColor(fg))
        pal.setColor(QPalette.Highlight, QColor(theme.PRIMARY))
        pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        w.setPalette(pal)

    # ===================== تحقّق مرن (Phase B) =====================
    #  «العمل يمكن حفظه ناقصًا. الوثيقة النهائية لا تُصدر ناقصة.»
    #  الحفظ لا يُمنَع أبداً بنقص المعلومات (§4)؛ التحقّق يُغذّي فقط
    #  حالة «⚠️ غير مكتمل» وبوّابة الإصدار النهائي.

    def _field_present(self, key) -> bool:
        w = self._widgets.get(key)
        if w is None:
            return False
        if isinstance(w, DateField):
            return bool(w.iso())
        if isinstance(w, GroupedNumberEdit):
            return bool(re.sub(r"\D", "", w.value()))
        if isinstance(w, QComboBox):
            return bool(w.currentText().strip())
        return bool(w.text().strip())

    def _field_error(self, key) -> str:
        """رسالة عدم الصلاحية الشكليّة (DateField فقط) — وإلا ``""``."""
        w = self._widgets.get(key)
        if isinstance(w, DateField):
            return w.error_text() or ""
        return ""

    _REQUIRE_PRESENT = {"iep"}          # موجودة → مطلوبة (§10)

    def _row_status(self, r):
        """‏``(started, complete, label)`` لسطرٍ — فحص المدخلات اللازمة
        للحساب فقط، بلا تكرار منطق المحرّك (§10). ``started`` يعني أنّ
        المستخدم بدأ تعبئة السطر فيصير نقصُه مانعاً للإصدار النهائي."""
        k = r.kind
        #  «بدأ» = أيّ خلية قابلة للتحرير (غير خيار — للخيارات قيَم افتراضية)
        #  فيها قيمة؛ أو نوعٌ يُطلَب بمجرّد وجوده (IEP).
        edit_cells = [n for n, c in r._cellspec.items() if c["kind"] != "choice"]
        started = ((k in self._REQUIRE_PRESENT)
                   or any(r.val(c) for c in edit_cells))
        if k == "salaire":
            return True, _num(r.val("gain")) > 0, "الأجر القاعديّ"
        if k in ("panier", "transport", "cnas", "irg"):
            return False, True, ""                     # 0 صالح · صفوف نظام
        if k == "prime":
            return started, _num(r.val("gain")) > 0, "Prime / تعويض"
        if k == "iep":
            return started, _num(r.val("taux")) > 0, "نسبة الأقدمية (IEP)"
        if k == "hs":
            ok = _num(r.val("qty")) > 0 and r.val("coef") in ("50%", "100%")
            return started, ok, "ساعات العمل الإضافيّ"
        if k == "absence":
            ok = (_num(r.val("qty")) > 0
                  and r.val("mode") in ("Absence (jours)", "Absence (heures)"))
            return started, ok, "كمّية الغياب"
        if k == "retard":
            return started, _num(r.val("qty")) > 0, "ساعات التأخّر"
        if k == "avance":
            ok = _num(r.val("montant")) > 0 and bool(r.val("libelle"))
            return started, ok, "السلفة / الاقتطاع"
        if k == "autre":
            need_class = r.val("sens") == "Gain"
            ok = (_num(r.val("montant")) > 0 and bool(r.val("libelle"))
                  and bool(r.val("sens"))
                  and (not need_class or bool(r.val("classe"))))
            return started, ok, "سطر «Autre»"
        return started, True, ""

    def _row_problem_key(self, r) -> str:
        if r is None:
            return ""
        pk = _ROW_SPECS[r.kind].get("primary")
        if pk and pk in r.widgets:
            return r.cell_key(pk)
        for c in r.widgets:
            return r.cell_key(c)
        return ""

    def validate(self):
        """‏``ValidationResult`` محدَّثة للحالة الراهنة (تُخزَّن في
        ``self._validation``)."""
        self._validation = validate_screen(self)
        return self._validation

    def show_required_warnings(self):
        """يُفعّل عرض تحذيرات الحقول الإلزامية (§6): يُستدعى فقط عند محاولة
        الإصدار النهائي أو استعادة عمل محفوظ كـ«غير مكتمل». يُبرز كلّ
        المشاكل دفعةً واحدة، ويركّز أوّلها بترتيب التنقّل، بلا صندوق حوار.
        يُعيد ``True`` إذا كان الكشف جاهزاً للإصدار النهائي."""
        self._recompute()
        self._warnings_active = True
        self._refresh_warning_styles()
        self._update_incomplete_indicator()
        v = self._validation
        if v is not None and v.problems:
            k = v.first_key(self._nav_order)
            w = self._widgets.get(k) if k else None
            if w is not None:
                w.setFocus()
            return False
        return True

    def clear_required_warnings(self):
        self._warnings_active = False
        self._refresh_warning_styles()
        self._update_incomplete_indicator()

    def _refresh_warning_styles(self):
        """يعيد تنميط كلّ الحقول من ``_validation`` الحالية. إذا صُحّحت كلّ
        النواقص، تنطفئ التحذيرات كلّها فوراً (§7)."""
        if (self._warnings_active and self._validation is not None
                and not self._validation.problems):
            self._warnings_active = False
        for k in list(self._widgets):
            self._style_field(k)
        if hasattr(self, "_canvas"):
            self._canvas.update()

    def _update_incomplete_indicator(self):
        lbl = getattr(self, "_incomplete_lbl", None)
        if lbl is None:
            return
        v = self._validation
        show = bool(self._warnings_active and v is not None and v.is_incomplete)
        if show:
            lbl.setText("⚠️ كشف غير مكتمل — %d نقطة تحتاج إكمالاً قبل "
                        "الإصدار النهائي." % len(v.problems))
        lbl.setVisible(show)

    def incomplete_badge(self) -> str:
        """للاستهلاك الخارجيّ لاحقاً (Phase C / مستكشف الملفّات): «⚠️» أو «»."""
        v = self._validation
        return "⚠️" if (v is not None and v.is_incomplete) else ""

    # ===================== دورة حياة العمل (Phase C) =====================
    #  SAVE يحمي عمل المستخدم · FINALIZE يصدر الوثيقة · LOCK يحمي النهائيّ.
    #  حالتان مرئيّتان فقط: ⚠️ Incomplete · 🔒 Final. Auto-draft آليّة
    #  استرداد داخلية لا حالة مستند.

    WORK_VERSION = 1

    def work_data(self) -> dict:
        """Work Data كاملة — مصدر إعادة بناء الشاشة (لا DOCX/PDF). تلفّ
        ``draft_state()`` (header + الصفوف الديناميكية + تصنيفاتها +
        ``iep_manual``) بـ metadata و``work_version``. مفصولة عن auto-draft
        من حيث دورة الحياة، لكنها تعيد استعمال نفس التسلسل."""
        d = self.draft_state()
        d["work_version"] = self.WORK_VERSION
        d["screen_key"] = "hr_bulletin_paie"
        d["employer"] = self._employer_data()
        d["employee"] = self._employee_data()
        d["period"] = {"mois": self._w("mois"), "annee": self._w("annee")}
        d["has_final_artifacts"] = bool(self._has_final_artifacts)
        d["final_docx"] = self._final_docx
        d["final_pdf"] = self._final_pdf
        return d

    def _work_record(self, state, docx="", pdf=None) -> dict:
        return {
            "screen_key": "hr_bulletin_paie", "doc_label": self.DOC_LABEL,
            "employer_name": self._w("emp_raison_sociale"),
            "employee_name": self._employee_fullname(),
            "doc_date": f"{self._w('mois')} {self._w('annee')}".strip(),
            "client_id": None, "file_path": docx or "", "pdf_path": pdf,
            "state": state,
        }

    def load_work(self, row: dict):
        """يفتح عملاً محفوظاً (صفّ ``hr_documents``) للتحرير: يعيد بناء
        الشاشة من ``full_data_json``، يثبّت المعرّف، ويستعيد حالة
        ⚠️/🔒. عمل ⚠️ مُعاد فتحه ⇒ تُفعَّل تحذيرات الإلزاميّ (§5)."""
        import json as _json
        raw = row.get("full_data_json") or ""
        try:
            data = _json.loads(raw) if raw else {}
        except ValueError:
            data = {}
        self.apply_draft(data)
        self._work_id = row.get("id")
        self._work_state = row.get("state") or None
        self._has_final_artifacts = bool(data.get("has_final_artifacts"))
        self._final_docx = data.get("final_docx") or row.get("file_path") or None
        self._final_pdf = data.get("final_pdf") or row.get("pdf_path") or None
        if self._work_state == "final":
            self._set_locked(True)
        elif self._work_state == "incomplete":
            self.show_required_warnings()
        # نظّف بعد كلّ إعادة البناء: عملٌ مُحمَّل حديثاً = «غير ملموس»
        # (‏auto-draft لا يطغى عليه) — §26/§14.
        self._dirty = False
        self.clear_draft()
        self._update_incomplete_indicator()
        self.status.setText("فُتح العمل: %s" % (self.work_badge() or "—"))

    def work_badge(self) -> str:
        """«⚠️» | «🔒» | «» — للاستهلاك الخارجيّ (مستكشف الملفّات لاحقاً)."""
        if self._work_state == "final":
            return "🔒"
        if self._work_state == "incomplete":
            return "⚠️"
        return self.incomplete_badge()

    def _on_save(self):
        """يحفظ التقدّم — **لا يُمنَع أبداً** بنقص المعلومات (§4). ينتج/يحدّث
        عملاً بحالة ⚠️ (لا DOCX/PDF نهائيَّين، لا قفل). عمل كان 🔒 ثمّ
        عُدِّل بعد فتح القفل ⇒ يعود ⚠️ ولا تُلمَس ملفّاته النهائية القديمة
        (§16)."""
        self._recompute()
        state = "incomplete"                      # SAVE لا يُنتج نهائياً أبداً
        rec = self._work_record(state)
        wd = self.work_data()
        try:
            if self._work_id is None:
                self._work_id = database.save_hr_work(rec, wd)
            else:
                database.update_hr_work(self._work_id, rec, wd)
        except Exception as exc:                              # noqa: BLE001
            logger.warning("حفظ العمل فشل", exc_info=True)
            from ui2.alerts import warn
            warn(self, self.TITLE, [f"تعذّر حفظ العمل: {exc}"])
            return
        self._work_state = state
        self._dirty = False
        self.clear_draft()
        self._update_incomplete_indicator()
        v = self._validation
        tail = ("⚠️ غير مكتمل" if (v is not None and v.is_incomplete)
                else "قابل للإصدار النهائيّ")
        self.status.setText(f"💾 حُفظ العمل — {tail}")

    def _set_locked(self, locked: bool):
        """🔒: كلّ مدخلات الوثيقة للقراءة فقط (حقول الترويسة + خلايا كلّ
        صفّ ديناميكيّ + ``+ Ajouter``). لا يمسّ Zoom/Ctrl+Wheel/التمرير
        (على ``_canvas``) ولا أزرار المعاينة/الحفظ باسم."""
        self._locked = bool(locked)
        for w in self._widgets.values():
            if isinstance(w, QComboBox):
                w.setEnabled(not locked)
            elif hasattr(w, "setReadOnly"):
                w.setReadOnly(locked)
        if hasattr(self, "_add_btn"):
            self._add_btn.setEnabled(not locked)
        if hasattr(self, "_canvas"):
            self._canvas.update()

    # ----------------------- البيانات والحساب -----------------------
    def _w(self, key):
        return self._widgets[key].text().strip()

    def _employer_data(self):
        return {"raison_sociale": self._w("emp_raison_sociale"),
                "adresse": self._w("emp_adresse"),
                "cnas_employeur": self._w("emp_cnas")}

    def _employee_data(self):
        return {
            "nom": self._w("id_nom"), "prenom": self._w("id_prenom"),
            "date_naissance": self._w("id_date_naissance"),
            "lieu_naissance": self._w("id_lieu_naissance"),
            "matricule": self._w("id_matricule"),
            "fonction": self._w("id_fonction"),
            "situation_familiale": self._w("id_situation_familiale"),
            "num_ss": self._w("id_num_ss"),
            # المستند يعرض dd/MM/yyyy (نصّ الحقل)؛ التخزين البرمجي/المسوّدة
            # يبقيان ISO عبر DateField.iso().
            "date_embauche": self._w("id_date_embauche"),
        }

    def _employee_fullname(self):
        return " ".join(x for x in (self._w("id_nom"), self._w("id_prenom")) if x)

    def _bulletin_date(self):
        try:
            month = _MOIS_UP.index(self._w("mois").upper()) + 1
            return date(int(self._w("annee")), month, 1)
        except (ValueError, KeyError):
            return date.today()

    def _load_cfg(self):
        if self._cfg is not None:
            return self._cfg
        for d in (self._bulletin_date(), date.today()):
            try:
                self._cfg = load_params(d)
                return self._cfg
            except PayrollConfigError:
                continue
        raise PayrollConfigError("لا يوجد ملف معاملات أجور متاح لأي تاريخ.")

    def _salaire_row(self):
        return next((r for r in self._rows if r.kind == "salaire"), None)

    def _build_entries(self):
        """أسطر الكشف بصيغة :func:`programme.payroll.lignes.compute_bulletin`
        من نموذج الصفوف الديناميكيّ. لا Convention ولا Catalogue — المحرّك
        هو مصدر الحساب الوحيد."""
        out = []
        for r in self._visible_body_rows():
            if r.role == "system":
                continue
            ent = r.entry()
            if ent is not None:
                out.append(ent)
        return out

    def _build_input(self):
        """‏``PaieInput`` للمُصيِّر (Word/PDF) — يُشتقّ من نتيجة المحرّك
        (‏``_bulletin_view``) فتظهر في المستند نفس المبالغ المحسوبة. القيَم
        الأساسية (أجر/سلة/نقل) من صفوفها؛ بقيّة الأسطر من ``view.lignes``."""
        sr = self._salaire_row()
        pin = calc.PaieInput(
            mois=self._w("mois"), annee=self._w("annee"),
            jours=_num(sr.val("nbase") if sr else "") or 30.0,
            salaire_base=_num(sr.val("gain") if sr else ""),
            panier=_num(next((r.val("gain") for r in self._rows
                              if r.kind == "panier"), "")),
            transport=_num(next((r.val("gain") for r in self._rows
                                 if r.kind == "transport"), "")))
        view = getattr(self, "_bulletin_view", None)
        if view is not None:
            for lv in view.lignes:
                if lv.key in ("salaire_base", "panier", "transport"):
                    continue
                if lv.sens == "GAIN":
                    pin.primes.append(calc.Prime(
                        code=lv.code, libelle=lv.libelle, montant=lv.montant,
                        soumis_cotisation=bool(lv.cotisable),
                        imposable=bool(lv.imposable)))
                else:
                    pin.autres_retenues.append(calc.Retenue(
                        code=lv.code, libelle=lv.libelle, montant=lv.montant))
        return pin

    def _is_computable(self):
        """هل الحساب ممكن أصلاً؟ (أجر قاعديّ موجب — وإلا فالنتائج «غير
        محسوبة» لا «صفراً حقيقياً»)."""
        sr = self._salaire_row()
        return sr is not None and _num(sr.val("gain")) > 0

    def _on_row_edit(self, key):
        if key in self._suspend or self._locked:
            return
        relayout = False
        for r in self._rows:
            if r.kind == "iep" and key == r.cell_key("taux"):
                # تعديل يدويّ للنسبة → Manual Override؛ تفريغها → العودة
                # للاقتراح (لفتة خفيفة، بلا زرّ إضافيّ).
                r._iep_manual = bool(r.val("taux"))
            if key in {r.cell_key(c) for c in r.choice_cells()}:
                relayout = True                  # قد يتغيّر عمود/ظهور خلية
        self._style_field(key)
        self.mark_dirty()
        self._recompute()
        if relayout:
            self._relayout()

    def _apply_iep_suggestion(self, row):
        """يضع النسبة المقترَحة من ``lignes.suggest_iep_taux`` (بلا Employé
        registry — ``employe_taux_iep=None``). لا يُستدعى لصفٍّ عُدِّلت
        نسبته يدوياً (``_iep_manual``)."""
        try:
            cfg = self._load_cfg()
        except Exception:                                    # noqa: BLE001
            return
        entree = self._widgets["id_date_embauche"].iso()
        try:
            m = _MOIS_UP.index(self._w("mois").upper()) + 1
            periode = f"{int(self._w('annee')):04d}-{m:02d}"
        except (ValueError, KeyError):
            periode = ""
        sug = lignes.suggest_iep_taux(date_entree=entree, periode=periode,
                                      cfg=cfg, employe_taux_iep=None)
        if sug.taux is None:
            return
        k = row.cell_key("taux")
        self._suspend.add(k)
        row.widgets["taux"].setText(format(sug.taux, "f"))
        self._suspend.discard(k)
        row._iep_manual = False

    def _assign_computed_amounts(self, view):
        by_key = {}
        for lv in view.lignes:
            by_key.setdefault(lv.key, []).append(lv)
        used = {}
        for r in self._visible_body_rows():
            r._amount = None
            lk = _ROW_SPECS[r.kind].get("lignes_key")
            if not lk:
                continue
            key = lk(r) if callable(lk) else lk
            lst = by_key.get(key, [])
            n = used.get(key, 0)
            if n < len(lst):
                r._amount = lst[n].montant
                used[key] = n + 1

    def _sync_row_styles(self):
        for r in self._rows:
            for cell in r.widgets:
                self._style_field(r.cell_key(cell))

    def _on_slot_write(self, key):
        if key in self._suspend or self._locked:
            return
        if key in ("mois", "annee"):
            self._cfg = None
        w = self._widgets[key]
        slot = self._slots_by_key[key]
        prev = self._prev_text.get(key, "")
        cur = w.text()
        self._prev_text[key] = cur
        growing = len(cur.replace(" ", "")) > len(prev.replace(" ", ""))

        def _set(txt, cursor_end=True):
            self._suspend.add(key)
            pos = w.cursorPosition()
            w.setText(txt)
            w.setCursorPosition(len(txt) if cursor_end else min(pos, len(txt)))
            self._suspend.discard(key)
            self._prev_text[key] = txt

        # ---- تحويلات نصّ بسيطة ----
        if slot.kind in ("upper", "upper_alpha") and isinstance(w, QLineEdit):
            if cur.upper() != cur:
                _set(cur.upper(), cursor_end=False)
        elif slot.kind == "titlecase" and isinstance(w, QLineEdit):
            tc = _titlecase(cur)
            if tc != cur:
                _set(tc, cursor_end=False)
        # ---- إدخال ذكي completion-driven (لا يقفز أثناء تحرير قيمة قائمة) ----
        elif slot.kind == "famille":
            if cur.upper() != cur:
                _set(cur.upper())
                cur = cur.upper()
            if growing and len(cur) == 1 and cur in _FAMILLE_CODES:
                self._advance_after(key)
        elif slot.kind == "month":
            idx, unamb = resolve_month(cur, MOIS_FR)
            if growing and unamb:
                canon = _MOIS_UP[idx]
                if cur.upper() != canon:
                    _set(canon)
                self._advance_after(key)
        elif slot.kind == "year":
            digs = re.sub(r"\D", "", cur)
            if digs != cur:
                _set(digs, cursor_end=False)
                digs = re.sub(r"\D", "", w.text())
            if growing and len(digs) == 4:
                self._advance_after(key)

        # §8: تغيّر تاريخ الميلاد قد يُبطِل صلاحية تاريخ بداية العمل.
        if key == "id_date_naissance":
            self._widgets["id_date_embauche"].revalidate()
        self._style_field(key)
        self.mark_dirty()
        self._recompute()

    def _advance_after(self, key):
        """انتقال مؤجَّل للحقل التالي — بعد أن ينتهي حدث الكتابة الحالي
        (يمنع تعارض إعادة الضبط مع تغيير التركيز). **بلا تحديد** للمحتوى:
        الانتقال التلقائي لا يجوز أن يُعرّض قيمةً قائمة للحذف بأوّل ضغطة."""
        QTimer.singleShot(0, lambda: self._focus_rel(key, +1, select=False))

    def _focus_rel(self, key, direction, *, select=True):
        try:
            i = self._nav_order.index(key)
        except ValueError:
            return
        nkey = self._nav_order[(i + direction) % len(self._nav_order)]
        w = self._widgets[nkey]
        w.setFocus()
        if select and hasattr(w, "selectAll"):
            w.selectAll()                    # Tab/Enter يدويّ: تحديد للكتابة فوقه
        elif hasattr(w, "deselect"):
            w.deselect()                     # انتقال تلقائي: المؤشّر فقط، لا تحديد

    @staticmethod
    def _view_to_paieresult(view):
        """‏``BulletinView`` (المحرّك) → ``PaieResult`` للمُصيِّر — فتظهر
        في Word/PDF نفس مبالغ المحرّك ([A]…[E] والمجاميع)."""
        r = view.result
        return calc.PaieResult(
            salaire_poste=view.a, base_cnas=view.a, retenue_cnas=view.b,
            base_irg=view.c, retenue_irg=view.d,
            panier=getattr(r, "panier", 0), transport=getattr(r, "transport", 0),
            total_gain=r.total_gains, total_retenue=r.total_retenues,
            net_a_payer=view.e, avertissements=list(view.avertissements))

    def _recompute(self):
        self._computed = False
        # اقتراح نسبة IEP للصفوف غير المعدَّلة يدوياً (يقرأ تاريخ الدخول
        # والفترة الحاليَّين). لا يسحق Manual Override.
        for r in self._rows:
            if r.kind == "iep" and not r._iep_manual:
                self._apply_iep_suggestion(r)
        try:
            cfg = self._load_cfg()
            #  مصدر الحساب الوحيد: lignes.compute_bulletin (بلا Convention/
            #  Catalogue). _calc_input / _calc_result للمُصيِّر يُشتقّان منه.
            self._bulletin_view = lignes.compute_bulletin(
                self._build_entries(), cfg)
            self._calc_input = self._build_input()
            self._calc_result = self._view_to_paieresult(self._bulletin_view)
            self._computed = self._is_computable()
            #  المبلغ المحسوب للصفوف المتكيّفة — None حين لا يمكن الحساب
            #  (‏«صفر حقيقي» ≠ «غير محسوب»، §5).
            if self._computed:
                self._assign_computed_amounts(self._bulletin_view)
            else:
                for r in self._rows:
                    r._amount = None
        except Exception:                                    # noqa: BLE001
            logger.warning("إعادة حساب الكشف فشلت", exc_info=True)
            self._bulletin_view = None
            for r in self._rows:
                r._amount = None
            self._calc_input = self._build_input()
        # تحقّق مرن (Phase B): يُعاد تقييمه بعد كلّ حساب — فتنطفئ تحذيرات
        # الحقول المصحَّحة فوراً دون انتظار حفظ (§7).
        try:
            self._validation = validate_screen(self)
        except Exception:                                    # noqa: BLE001
            logger.warning("تحقّق الكشف فشل", exc_info=True)
            self._validation = None
        if self._warnings_active:
            self._refresh_warning_styles()
        self._update_incomplete_indicator()
        if hasattr(self, "_canvas"):
            self._canvas.update()

    # ----------------------- الزبون -----------------------
    def _on_mode_change(self, _checked=False):
        reg = self._rb_reg.isChecked()
        self._mode = "registered" if reg else "walkin"
        self._client_combo.setVisible(reg)
        if reg and self._client_combo.count() == 0:
            try:
                from programme.payroll import repository
                rows = repository.list_entreprises(registered_only=True,
                                                   conn=self._conn)
                self._client_rows = rows
                self._client_combo.addItems([r["raison_sociale"] for r in rows])
            except Exception:                                # noqa: BLE001
                logger.warning("تعذّر جلب الزبائن المسجَّلين", exc_info=True)

    # ----------------------- التوليد / السجلّ / المسح -----------------------
    def _resolve_out_path(self, ext):
        who = self._employee_fullname()
        stem = (f"Bulletin_{_safe(who)}_{_safe(self._w('mois'))}"
                f"_{_safe(self._w('annee'))}")
        return os.path.join(paths.get_screen_dir(self.OUTPUT_DIRNAME), stem + ext)

    def _on_generate(self, kind):
        from ui2.alerts import warn
        self._recompute()
        # بوّابة الإصدار النهائي (Phase B §8): تحقّق واحد لكامل الشاشة —
        # يُبرز كلّ المشاكل، ويركّز أوّلها، وينبّه تنبيهاً عامّاً واحداً.
        # (دورة حياة Finalize/Lock الكاملة = Phase C.)
        if not self.show_required_warnings():
            warn(self, self.TITLE,
                 ["توجد معلومات ناقصة قبل إصدار الكشف النهائي."])
            return
        tpl = T.get_renderer(self._template_key)
        ext = ".docx" if kind == "docx" else ".pdf"
        path = self._resolve_out_path(ext)
        try:
            builder = tpl.build_docx if kind == "docx" else tpl.build_pdf
            #  المُصيِّر من BulletinView (مصدر حقيقة الشاشة نفسه، Phase C2)
            builder(path, self._calc_input, self._calc_result,
                    self._employer_data(), self._employee_data(),
                    view=self._bulletin_view)
        except TemplateNotReady as exc:
            warn(self, self.TITLE, [str(exc)])
            return
        except Exception as exc:                             # noqa: BLE001
            logger.warning("توليد %s فشل", kind, exc_info=True)
            warn(self, self.TITLE, [f"تعذّر التوليد: {exc}"])
            return
        try:
            database.log_hr_document({
                "screen_key": "hr_bulletin_paie", "doc_label": self.DOC_LABEL,
                "employer_name": self._employer_data().get("raison_sociale", ""),
                "employee_name": self._employee_fullname(),
                "doc_date": f"{self._w('mois')} {self._w('annee')}".strip(),
                "client_id": None, "file_path": path,
                "pdf_path": path if kind == "pdf" else None,
            }, full_data=self._collect_data())
        except Exception:                                    # noqa: BLE001
            logger.warning("تسجيل الوثيقة فشل", exc_info=True)
        if confirm(self, self.TITLE, f"تمّ إنشاء الملف:\n{path}\n\nفتحه الآن؟"):
            try:
                os.startfile(path)                           # noqa: SIM115
            except OSError:
                pass

    def _collect_data(self):
        pin = self._calc_input
        import dataclasses
        return {
            "screen_key": "hr_bulletin_paie", "doc_label": self.DOC_LABEL,
            "template": self._template_key, "mode": self._mode, "client_id": None,
            "employer": self._employer_data(), "employee": self._employee_data(),
            "paie": {
                "mois": pin.mois, "annee": pin.annee, "jours": pin.jours,
                "salaire_base": pin.salaire_base, "panier": pin.panier,
                "transport": pin.transport,
                "primes": [dataclasses.asdict(p) for p in pin.primes],
                "autres_retenues": [dataclasses.asdict(r) for r in pin.autres_retenues],
            },
            "result": {k: str(v) for k, v in
                       dataclasses.asdict(self._calc_result).items()},
        }

    _WORK_BADGE = {"final": "🔒", "incomplete": "⚠️"}

    def _on_history(self):
        from PySide6.QtWidgets import (QDialog, QTableWidget, QTableWidgetItem,
                                       QAbstractItemView)
        rows = database.list_hr_documents(screen_key="hr_bulletin_paie", limit=200)
        dlg = QDialog(self)
        dlg.setWindowTitle(f"سجلّ — {self.DOC_LABEL}")
        dlg.resize(780, 440)
        tw = QTableWidget(len(rows), 5, dlg)
        tw.setHorizontalHeaderLabels(["", "التاريخ", "الأجير", "المكتب", "الملف"])
        tw.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tw.setSelectionBehavior(QAbstractItemView.SelectRows)
        for i, r in enumerate(rows):
            badge = self._WORK_BADGE.get(r.get("state"), "")
            for j, v in enumerate((
                    badge, r.get("doc_date", ""), r.get("employee_name", ""),
                    r.get("employer_name", ""),
                    os.path.basename(r.get("file_path", "")))):
                tw.setItem(i, j, QTableWidgetItem(str(v)))
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("نقرة مزدوجة على سطر لفتح العمل للتحرير."))
        lay.addWidget(tw)

        def _open(row_idx):
            r = rows[row_idx]
            rid = r.get("id")
            if rid is None:
                return
            full = database.get_hr_document(rid)
            if not full:
                return
            dlg.accept()
            self.load_work(full)

        tw.cellDoubleClicked.connect(lambda rr, _c: _open(rr))
        dlg.exec()

    def _on_clear(self):
        if not confirm(self, "تأكيد", "مسح كل الحقول في هذه الشاشة؟"):
            return
        if self._locked:
            self._set_locked(False)
        self._work_id = None                   # مسح ⇒ عمل جديد بلا هويّة
        self._work_state = None
        self._has_final_artifacts = False
        self._final_docx = self._final_pdf = None
        self._suspend = set(self._widgets)
        try:
            for s in self._header_slots:
                w = self._widgets[s.key]
                if isinstance(w, DateField):
                    w.set_iso("")
                elif isinstance(w, GroupedNumberEdit):
                    w.set_value("")
                else:
                    w.setText("")
            # صفوف الجسم → العودة إلى النواة الافتراضية
            for r in list(self._rows):
                r.dispose()
            self._rows.clear()
            self._init_default_rows()
            self._prev_text.clear()
        finally:
            self._suspend = set()
        self._warnings_active = False          # مسح ⇒ لا تحذيرات إلزاميّ
        self._restored_incomplete = False
        self._rebuild_nav()
        for k in list(self._widgets):
            self._style_field(k)
        self.mark_clean()
        self._recompute()
        self._relayout()

    def has_unsaved_changes(self):
        #  Phase C §26: تغييرات فعلية منذ آخر حفظ/تحميل — لا «فيه محتوى».
        #  عملٌ مُحمَّل وغير ملموس ⇒ False؛ أوّل تعديل ⇒ True؛ Save ⇒ False.
        return self._dirty
