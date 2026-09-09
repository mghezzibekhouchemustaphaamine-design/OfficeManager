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

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPalette
from PySide6.QtWidgets import (
    QAbstractSpinBox, QButtonGroup, QCheckBox, QComboBox, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QScrollArea, QSplitter,
    QVBoxLayout, QWidget,
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
from ui2.form import _DateEdit
from ui2.screen import Screen

logger = logging.getLogger(__name__)

_ENTRY_FONT = T.FORM_FONT                       # "Helvetica" — نفس خط النموذج
# معايرة عمودية لمنطقة بيانات العامل في الشاشة الجديدة فقط — الأصل بدا
# أكثر انفراجاً؛ نزيد إيقاع صفوف الهوية بمقدار SPACE["sm"] لكل فجوة،
# وتُزاح كتلة الجدول أسفلها بنفس المجموع (بلا تداخل مع ترويسة الجدول).
_IDENT_ROW_EXTRA_PX = theme.SPACE["sm"]
# فرق كروم QLineEdit العمودي (حدّ + حشو QSS) من أعلى الإطار إلى خط أساس
# نصّه — نظير ``_ENTRY_TOP_CHROME`` في ui/hr/bulletin_paie.py (كان 2 لـ
# tk.Entry). يُضبط بصرياً بمقارنة الصورة.
_ENTRY_TOP_CHROME = 4
_MOIS_UP = [m.upper() for m in MOIS_FR]
_FAMILLE_CODES = {"C", "D", "V", "M"}


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
        box, scale, _cw, _ch = self._screen._page_box()
        x0, y0, x1, y1 = box
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
            self._paint_form(p, box, scale)
        except Exception:                                     # noqa: BLE001
            logger.warning("رسم الاستمارة فشل", exc_info=True)
        p.end()

    def _paint_form(self, p: QPainter, box, scale):
        x0, y0, _x1, _y1 = box
        sc = self._screen
        res = sc._calc_result
        ink = QColor(theme.TEXT)
        cc = QColor(theme.COMPUTED)

        def X(mm):
            return x0 + (T.MARGIN_L + mm) * scale

        def Y(mm):
            return y0 + mm * scale

        def col_x(frac):
            return x0 + (T.MARGIN_L + frac * T.CONTENT_W) * scale

        def font(mm_h, bold=False):
            f = QFont(_ENTRY_FONT)
            f.setPointSize(max(int(mm_h * scale * 0.62), 6))
            f.setBold(bold)
            return f

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
            if kind == "famille":
                base_text(xv + wv + 1.2, sc._ident_row_y(row, scale), "▾",
                          font(3.0), QColor("#5f6368"))
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
    DRAFT_VERSION = 1

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
        self._widgets = {}                     # key -> QLineEdit / _DateEdit
        self._suspend = set()
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
        return {k: (w.iso() if isinstance(w, _DateEdit) else w.text())
                for k, w in self._widgets.items()}

    def apply_draft(self, data):
        self._suspend = set(self._widgets)
        try:
            for k, v in (data or {}).items():
                w = self._widgets.get(k)
                if w is None:
                    continue
                if isinstance(w, _DateEdit):
                    w.set_iso(v)
                else:
                    w.setText(str(v or ""))
        finally:
            self._suspend = set()
        for k in self._widgets:
            self._style_field(k)
        self._recompute()

    def is_empty(self):
        skip = {"mois", "annee", "jours"}
        return not any((w.text().strip() if not isinstance(w, _DateEdit) else w.iso())
                       for k, w in self._widgets.items() if k not in skip)

    # ----------------------- بناء الحقول -----------------------
    def _build_fields(self):
        today = date.today()
        defaults = {"mois": _MOIS_UP[today.month - 1],
                    "annee": str(today.year), "jours": "30"}
        for slot in T.FIELD_SLOTS:
            if slot.kind == "date_masked":
                # نفس مظهر MaskedDateEntry القديمة: dd/MM/yyyy، بلا زرّ
                # تقويم ظاهر، إطار مسطّح فوق الورقة.
                w = _DateEdit("dd/MM/yyyy", nullable=True, parent=self._canvas)
                w.setCalendarPopup(False)
                w.setButtonSymbols(QAbstractSpinBox.NoButtons)
                w.setFrame(False)
                w.dateChanged.connect(lambda _d, k=slot.key: self._on_slot_write(k))
            else:
                w = QLineEdit(defaults.get(slot.key, ""), self._canvas)
                w.setFrame(False)
                al = {"r": Qt.AlignRight, "c": Qt.AlignHCenter,
                      "l": Qt.AlignLeft}[slot.align]
                w.setAlignment(al | Qt.AlignVCenter)
                # القيَم المجمَّعة (N° SS / N° ADHÉRENT) تُدخَل بمسافات وربّما
                # مفتاح «/XX» فتتجاوز maxlen الخام — لا نقصّها بـ setMaxLength.
                if slot.kind not in ("num_ss", "adherent"):
                    w.setMaxLength(slot.maxlen)
                w.textChanged.connect(lambda _t, k=slot.key: self._on_slot_write(k))
                w.returnPressed.connect(lambda k=slot.key: self._focus_rel(k, +1))
            w.setLayoutDirection(Qt.LeftToRight)
            self._widgets[slot.key] = w
            w.show()
        for k in self._widgets:
            self._style_field(k)

    # ----------------------- الزوم والتخطيط -----------------------
    def _page_box(self):
        cw = max(self._scroll.viewport().width(), 1) if hasattr(self, "_scroll") else 1
        ch = max(self._scroll.viewport().height(), 1) if hasattr(self, "_scroll") else 1
        sheet_w = self.TARGET_W * self.zoom / 100.0
        scale = sheet_w / 210.0
        sheet_h = scale * 297.0
        x0 = max((cw - sheet_w) / 2, self.MARGIN)
        y0 = self.MARGIN
        return (x0, y0, x0 + sheet_w, y0 + sheet_h), scale, cw, ch

    def _row1_layout(self, scale):
        """موضعا «à» وحقل المكان في سطر تاريخ الميلاد — نظير
        ``template_simple.row1_layout`` بقياس خط Qt."""
        fs = max(int(3.2 * scale * 0.62), 6)
        f = QFont(_ENTRY_FONT, fs)
        f.setBold(True)
        fm = QFontMetricsF(f)
        date_w_mm = fm.horizontalAdvance("00/00/0000") / scale + 1.8
        sp = fm.horizontalAdvance(" ") / scale
        a_x = T._VAL_L + date_w_mm + 2 * sp
        lieu_x = a_x + fm.horizontalAdvance("à") / scale + 2 * sp
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

    def _relayout(self):
        if not hasattr(self, "_canvas"):
            return
        box, scale, cw, ch = self._page_box()
        x0, y0, x1, y1 = box
        self._canvas.setFixedSize(int(max(x1 + self.MARGIN, cw)),
                                  int(max(y1 + self.MARGIN, ch)))
        for slot in T.FIELD_SLOTS:
            w = self._widgets[slot.key]
            fs = max(6, int(slot.font_mm * scale * 0.62))
            f = QFont(_ENTRY_FONT, fs)
            f.setBold(bool(slot.bold))
            w.setFont(f)
            fm = QFontMetricsF(f)

            slot_x_mm = slot.x_mm
            if slot.key == "id_lieu_naissance":
                slot_x_mm = self._row1_layout(scale)[1]

            px = x0 + (T.MARGIN_L + slot_x_mm) * scale
            if slot.key in self._ident_row:                     # صفّ هوية — إيقاع مُعاير
                base_mm = self._ident_row_y(self._ident_row[slot.key], scale)
                py = y0 + base_mm * scale - fm.ascent() - _ENTRY_TOP_CHROME
                h = int(fm.height() + 2 * _ENTRY_TOP_CHROME)
            elif slot.baseline_mm is not None:                  # رأس المكتب / الشريط
                py = y0 + slot.baseline_mm * scale - fm.ascent() - _ENTRY_TOP_CHROME
                h = int(fm.height() + 2 * _ENTRY_TOP_CHROME)
            else:                                              # خانة جدول — مُزاحة لأسفل
                py = y0 + (slot.y_mm + self._y_shift(scale)) * scale
                h = int((T.ROW_H - 0.8) * scale)

            if getattr(slot, "fit_maxlen", False):
                # قدر أوسع من: maxlen حرفاً عريضاً، أو المحتوى الحالي
                # (قيَم مجمَّعة بمسافات أطول من maxlen الخام — N° SS مثلاً).
                cur = w.iso() if isinstance(w, _DateEdit) else w.text()
                wpx = int(max(fm.horizontalAdvance("0" * slot.maxlen),
                              fm.horizontalAdvance(cur)) + 10)
            else:
                wpx = int(slot.w_mm * scale)
            w.setFixedWidth(max(wpx, 12))
            w.setFixedHeight(max(h, 12))
            w.move(int(px), int(py))
        self._canvas.update()

    # ----------------------- المظهر (كريمي/أبيض/شريط) -----------------------
    def _field_value(self, key):
        w = self._widgets[key]
        return w.iso() if isinstance(w, _DateEdit) else w.text().strip()

    def _style_field(self, key):
        w = self._widgets[key]
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
        cls = "QDateEdit" if isinstance(w, _DateEdit) else "QLineEdit"
        w.setStyleSheet(
            f"{cls} {{ background:{bg}; color:{fg}; border:1px solid {bd}; "
            f"border-radius:0; padding:0 1px; "
            f"selection-background-color:{bg}; selection-color:{fg}; }}")
        # توحيد صريح: لون النصّ من QPalette أيضاً (لا تظليل يُلوّن القيمة)
        pal = w.palette()
        for role in (QPalette.Text, QPalette.WindowText, QPalette.HighlightedText):
            pal.setColor(role, QColor(fg))
        w.setPalette(pal)
        if isinstance(w, QLineEdit):
            w.deselect()

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
            "date_embauche": self._field_value("id_date_embauche"),
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
        # تحويلات نصّ بسيطة (نظير _on_key_release في الشاشة القديمة)
        if slot.kind in ("upper", "upper_alpha") and isinstance(w, QLineEdit):
            up = w.text().upper()
            if up != w.text():
                self._suspend.add(key); pos = w.cursorPosition()
                w.setText(up); w.setCursorPosition(pos); self._suspend.discard(key)
        elif slot.kind == "titlecase" and isinstance(w, QLineEdit):
            tc = _titlecase(w.text())
            if tc != w.text():
                self._suspend.add(key); pos = w.cursorPosition()
                w.setText(tc); w.setCursorPosition(pos); self._suspend.discard(key)
        elif slot.kind == "famille" and isinstance(w, QLineEdit):
            up = w.text().upper()
            if up != w.text():
                self._suspend.add(key); w.setText(up); self._suspend.discard(key)
        self._style_field(key)
        self.mark_dirty()
        self._recompute()

    def _focus_rel(self, key, direction):
        try:
            i = self._nav_order.index(key)
        except ValueError:
            return
        nkey = self._nav_order[(i + direction) % len(self._nav_order)]
        self._widgets[nkey].setFocus()
        w = self._widgets[nkey]
        if isinstance(w, QLineEdit):
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
        today = date.today()
        defaults = {"mois": _MOIS_UP[today.month - 1],
                    "annee": str(today.year), "jours": "30"}
        self._suspend = set(self._widgets)
        try:
            for k, w in self._widgets.items():
                if isinstance(w, _DateEdit):
                    w.set_iso("")
                else:
                    w.setText(defaults.get(k, ""))
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
