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
from programme.payroll import calc, registry
from programme.payroll.calc import fmt_montant
from programme.payroll.config_loader import PayrollConfigError, load_params
from ui.hr.constants import MOIS_FR
from ui.hr.paie import template_simple as T
from ui.hr.render import TemplateNotReady
from ui2 import theme
from ui2.alerts import confirm
from ui2.form import DateField, GroupedNumberEdit, resolve_month
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

        # ترويسة الجدول + الأعمدة
        hy0, hy1 = Yt(T.TABLE_HEAD_Y), Yt(T.TABLE_HEAD_Y + T.ROW_H + 1)
        p.setPen(ink)
        p.drawRect(int(X(0)), int(hy0), int(X(T.CONTENT_W) - X(0)), int(hy1 - hy0))
        for _key, f0, _f1, _al, title in T.COLS:
            p.setPen(ink)
            p.drawLine(int(col_x(f0)), int(hy0), int(col_x(f0)), int(Yt(T.FORM_TABLE_BOTTOM)))
            p.setFont(font(3.0, True))
            fm = QFontMetricsF(p.font())
            p.drawText(QPoint(int(col_x(f0) + 2.5 * scale),
                              int((hy0 + hy1) / 2 + fm.ascent() / 2 - fm.descent() / 2)),
                       title)
        p.setPen(ink)
        p.drawLine(int(X(T.CONTENT_W)), int(hy0),
                   int(X(T.CONTENT_W)), int(Yt(T.FORM_TABLE_BOTTOM)))

        # خطوط الأسطر الأفقية
        p.setPen(QColor(theme.GRID_LINE))
        for r in range(T.N_BODY_ROWS + 1):
            yy = Yt(T.BODY_TOP + r * T.ROW_H)
            p.drawLine(int(X(0)), int(yy), int(X(T.CONTENT_W)), int(yy))

        def row_mid(r):
            return T.BODY_TOP + r * T.ROW_H + T.ROW_H / 2

        def cell_center(col_key, r, s, color=ink, bold=False):
            f0, f1, _al = T._colf(col_key)
            self._cell(p, (col_x(f0) + col_x(f1)) / 2, Yt(row_mid(r)), s,
                       "center", font(3.2, bold), color)

        def cell_left(col_key, r, s, color=ink, bold=False):
            f0, _f1, _al = T._colf(col_key)
            self._cell(p, col_x(f0) + 2.5 * scale, Yt(row_mid(r)), s,
                       "w", font(3.2, bold), color)

        def cell_right(col_key, r, s, color=ink, bold=False):
            _f0, f1, _al = T._colf(col_key)
            self._cell(p, col_x(f1) - 2.5 * scale, Yt(row_mid(r)), s,
                       "e", font(3.2, bold), color)

        c = T.PAIE_DEFAULT_CODES
        cell_center("code", T.ROW_SALAIRE, c["salaire_base"])
        cell_left("libelle", T.ROW_SALAIRE, "SALAIRE DE BASE")
        cell_center("code", T.ROW_CNAS, c["cnas"])
        cell_left("libelle", T.ROW_CNAS, "RETENUE SÉCU. SOCIALE")
        cell_center("code", T.ROW_IRG, c["irg"])
        cell_left("libelle", T.ROW_IRG, "RETENUE IRG")
        cell_center("code", T.ROW_PANIER, c["panier"])
        cell_left("libelle", T.ROW_PANIER, "PANIER")
        cell_center("code", T.ROW_TRANSPORT, c["transport"])
        cell_left("libelle", T.ROW_TRANSPORT, "(R+) TRANSPORT")

        if res is not None:
            cell_right("nbase", T.ROW_CNAS, fmt_montant(res.base_cnas), cc)
            cell_right("taux", T.ROW_CNAS, "9,00", cc)
            cell_right("retenue", T.ROW_CNAS, fmt_montant(res.retenue_cnas), cc)
            cell_right("nbase", T.ROW_IRG, fmt_montant(res.base_irg), cc)
            cell_right("retenue", T.ROW_IRG, fmt_montant(res.retenue_irg), cc)

            ty0 = Yt(T.FORM_TOTAL_Y)
            p.setPen(ink)
            p.drawLine(int(X(0)), int(ty0), int(X(T.CONTENT_W)), int(ty0))
            p.drawLine(int(X(0)), int(Yt(T.FORM_TOTAL_Y + T.ROW_H)),
                       int(X(T.CONTENT_W)), int(Yt(T.FORM_TOTAL_Y + T.ROW_H)))
            self._cell(p, col_x(T._colf("taux")[1]) - 3 * scale,
                       Yt(T.FORM_TOTAL_Y + T.ROW_H / 2), "TOTAL", "e",
                       font(3.4, True), ink)
            self._cell(p, col_x(T._colf("gain")[1]) - 2.5 * scale,
                       Yt(T.FORM_TOTAL_Y + T.ROW_H / 2), fmt_montant(res.total_gain),
                       "e", font(3.4, True), cc)
            self._cell(p, col_x(T._colf("retenue")[1]) - 2.5 * scale,
                       Yt(T.FORM_TOTAL_Y + T.ROW_H / 2), fmt_montant(res.total_retenue),
                       "e", font(3.4, True), cc)

            ny = T.FORM_NET_Y
            self._cell(p, col_x(0.60), Yt(ny + 5), "NET À PAYER", "e",
                       font(4.2, True), ink)
            p.fillRect(int(col_x(0.62)), int(Yt(ny)),
                       int(X(T.CONTENT_W) - col_x(0.62)), int(Yt(ny + 10) - Yt(ny)),
                       QColor(theme.BAND_BLACK))
            self._cell(p, X(T.CONTENT_W - 3), Yt(ny + 5),
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
    DRAFT_VERSION = 2          # Phase 55: بنية حقول جديدة (تاريخ/مجمَّع/شهر فارغ)

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

        self._slots_by_key = {s.key: s for s in T.FIELD_SLOTS}
        self._nav_order = [s.key for s in T.FIELD_SLOTS]
        self._band_keys = {s.key for s in T.FIELD_SLOTS if s.on_band}
        self._ident_row = {f"id_{k}": row
                           for k, _l, _xl, _xv, _wv, row, _ml, _kd in T.IDENT_FIELDS}
        self._widgets = {}                     # key -> QLineEdit / DateField / GroupedNumberEdit
        self._suspend = set()
        self._prev_text = {}                   # آخر نصّ لكلّ حقل (لتمييز الكتابة عن التحرير)
        self._prime_soumis = [True, True, True]

        self._calc_input = calc.PaieInput()
        self._calc_result = calc.compute(self._calc_input, self._load_cfg())

        self.build_ui()
        self.toolbar.setVisible(False)         # لا شريط أدوات في التصميم القديم
        self._build_fields()
        self.on_activate()
        QTimer.singleShot(0, self._relayout)
        self._recompute()

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

        pf = QFrame()
        pf.setFrameShape(QFrame.StyledPanel)
        pl = QVBoxLayout(pf)
        pl.addWidget(QLabel("منح خاضعة للاشتراك (CNAS)"))
        self._prime_boxes = []
        for k in range(T.N_PRIME_SLOTS):
            cb = QCheckBox(f"منحة {k + 1}")
            cb.setChecked(True)
            cb.toggled.connect(lambda v, i=k: self._set_prime_soumis(i, v))
            pl.addWidget(cb)
            self._prime_boxes.append(cb)
        lay.addWidget(pf)

        bf = QFrame()
        bf.setFrameShape(QFrame.StyledPanel)
        bl = QVBoxLayout(bf)
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

    # المسوّدة
    def draft_state(self):
        out = {}
        for k, w in self._widgets.items():
            if isinstance(w, DateField):
                out[k] = w.iso()                 # ISO
            elif isinstance(w, GroupedNumberEdit):
                out[k] = w.value()               # مضغوط (أرقام + «/» إن وُجد)
            else:
                out[k] = w.text()
        return out

    def apply_draft(self, data):
        self._suspend = set(self._widgets)
        try:
            for k, v in (data or {}).items():
                w = self._widgets.get(k)
                if w is None:
                    continue
                if isinstance(w, DateField):
                    w.set_iso(v)
                elif isinstance(w, GroupedNumberEdit):
                    w.set_value(v)
                else:
                    w.setText(str(v or ""))
            self._prev_text.clear()
        finally:
            self._suspend = set()
        for k in self._widgets:
            self._style_field(k)
        self._recompute()

    def is_empty(self):
        skip = {"mois", "annee", "jours"}
        return not any(w.text().strip()
                       for k, w in self._widgets.items() if k not in skip)

    # ----------------------- بناء الحقول -----------------------
    def _build_fields(self):
        today = date.today()
        # الشهر والسنة يبدآن **فارغين** (لا تعبئة تلقائية بتاريخ اليوم)؛
        # jours وحده افتراضٌ معنوي (30 يوماً).
        defaults = {"jours": "30"}
        for slot in T.FIELD_SLOTS:
            if slot.kind == "date_masked":
                # DateField الموحّد: عرض dd/MM/yyyy، تخزين ISO، مسطّح،
                # خطأ سطري، ولا تاريخ مستقبلي (max = اليوم لكلا الحقلين §8).
                w = DateField(display_format="dd/MM/yyyy", nullable=True,
                              flat=True, max_date=today, inline_error=False,
                              parent=self._canvas)
                w.dateChanged.connect(lambda _d, k=slot.key: self._on_slot_write(k))
                w.errorChanged.connect(self._refresh_date_errors)
                w.completed.connect(lambda k=slot.key: self._focus_rel(k, +1))
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
                w.completed.connect(lambda k=slot.key: self._focus_rel(k, +1))
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
            self._focus_rel(key, +1)

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
        for slot in T.FIELD_SLOTS:
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
        self._canvas.update()

    # ----------------------- المظهر (كريمي/أبيض/شريط) -----------------------
    def _field_value(self, key):
        w = self._widgets[key]
        return w.iso() if isinstance(w, DateField) else w.text().strip()

    def _style_field(self, key):
        w = self._widgets[key]
        if isinstance(w, DateField):
            w.refresh_style()                 # DateField يدير نمطه بنفسه (4 حالات)
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

    def _build_input(self):
        primes = []
        for k in range(T.N_PRIME_SLOTS):
            lib = self._w(f"prime{k}_lib")
            mnt = self._w(f"prime{k}_montant")
            if lib or mnt:
                primes.append(calc.Prime(
                    code=self._w(f"prime{k}_code"), libelle=lib,
                    montant=_num(mnt),
                    soumis_cotisation=bool(self._prime_soumis[k])))
        autres = []
        for k in range(T.N_AUTRE_SLOTS):
            lib = self._w(f"autre{k}_lib")
            mnt = self._w(f"autre{k}_montant")
            if lib or mnt:
                autres.append(calc.Retenue(
                    code=self._w(f"autre{k}_code"), libelle=lib, montant=_num(mnt)))
        return calc.PaieInput(
            mois=self._w("mois"), annee=self._w("annee"),
            jours=_num(self._w("jours")) or 30.0,
            salaire_base=_num(self._w("salaire_base")),
            panier=_num(self._w("panier")), transport=_num(self._w("transport")),
            primes=primes, autres_retenues=autres)

    def _on_slot_write(self, key):
        if key in self._suspend:
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
        (يمنع تعارض إعادة الضبط مع تغيير التركيز)."""
        QTimer.singleShot(0, lambda: self._focus_rel(key, +1))

    def _focus_rel(self, key, direction):
        try:
            i = self._nav_order.index(key)
        except ValueError:
            return
        nkey = self._nav_order[(i + direction) % len(self._nav_order)]
        w = self._widgets[nkey]
        w.setFocus()
        if hasattr(w, "selectAll"):
            w.selectAll()

    def _recompute(self):
        self._calc_input = self._build_input()
        try:
            self._calc_result = calc.compute(self._calc_input, self._load_cfg())
        except Exception:                                    # noqa: BLE001
            logger.warning("إعادة حساب الكشف فشلت", exc_info=True)
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

    def _set_prime_soumis(self, idx, value):
        self._prime_soumis[idx] = bool(value)
        self._recompute()

    # ----------------------- التوليد / السجلّ / المسح -----------------------
    def _resolve_out_path(self, ext):
        who = self._employee_fullname()
        stem = (f"Bulletin_{_safe(who)}_{_safe(self._w('mois'))}"
                f"_{_safe(self._w('annee'))}")
        return os.path.join(paths.get_screen_dir(self.OUTPUT_DIRNAME), stem + ext)

    def _on_generate(self, kind):
        from ui2.alerts import warn
        if not self._employee_fullname():
            warn(self, self.TITLE, ["أدخل اسم الأجير أولاً."])
            return
        self._recompute()
        tpl = T.get_renderer(self._template_key)
        ext = ".docx" if kind == "docx" else ".pdf"
        path = self._resolve_out_path(ext)
        try:
            builder = tpl.build_docx if kind == "docx" else tpl.build_pdf
            builder(path, self._calc_input, self._calc_result,
                    self._employer_data(), self._employee_data())
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

    def _on_history(self):
        from PySide6.QtWidgets import QDialog, QTableWidget, QTableWidgetItem
        rows = database.list_hr_documents(screen_key="hr_bulletin_paie", limit=200)
        dlg = QDialog(self)
        dlg.setWindowTitle(f"سجلّ — {self.DOC_LABEL}")
        dlg.resize(760, 420)
        tw = QTableWidget(len(rows), 4, dlg)
        tw.setHorizontalHeaderLabels(["التاريخ", "الأجير", "المكتب", "الملف"])
        for i, r in enumerate(rows):
            for j, v in enumerate((
                    r.get("doc_date", ""), r.get("employee_name", ""),
                    r.get("employer_name", ""),
                    os.path.basename(r.get("file_path", "")))):
                tw.setItem(i, j, QTableWidgetItem(str(v)))
        QVBoxLayout(dlg).addWidget(tw)
        dlg.exec()

    def _on_clear(self):
        if not confirm(self, "تأكيد", "مسح كل الحقول في هذه الشاشة؟"):
            return
        defaults = {"jours": "30"}          # الشهر/السنة يبقيان فارغين
        self._suspend = set(self._widgets)
        try:
            for k, w in self._widgets.items():
                if isinstance(w, DateField):
                    w.set_iso("")
                elif isinstance(w, GroupedNumberEdit):
                    w.set_value("")
                else:
                    w.setText(defaults.get(k, ""))
            self._prev_text.clear()
        finally:
            self._suspend = set()
        for cb in self._prime_boxes:
            cb.setChecked(True)
        for k in self._widgets:
            self._style_field(k)
        self.mark_clean()
        self._recompute()

    def has_unsaved_changes(self):
        return not self.is_empty()
