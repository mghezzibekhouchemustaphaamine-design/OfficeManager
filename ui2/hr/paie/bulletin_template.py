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

from PySide6.QtCore import QEvent, QPoint, QStringListModel, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPalette
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QCompleter, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMenu, QPushButton, QRadioButton, QScrollArea,
    QSplitter, QToolButton, QVBoxLayout, QWidget,
)

from programme import database, paths
from programme.payroll import calc, lignes, registry
from programme.payroll.calc import fmt_montant
from programme.payroll.config_loader import PayrollConfigError, load_params
from ui.hr.constants import MOIS_FR
from ui.hr.paie import layout_spec as L        # هندسة الوثيقة (مليمتر، بلا زوم)
from ui.hr.paie import presentation as PZ      # طبقة العرض المشتركة (§11)
from ui.hr.paie import template_simple as T
from ui.hr.render import TemplateNotReady
from ui2 import theme
from ui2.alerts import confirm
from ui2.form import DateField, GroupedNumberEdit, resolve_month
from ui2.hr.paie.validation import validate_screen
from ui2.screen import Screen

logger = logging.getLogger(__name__)

_ENTRY_FONT = T.FORM_FONT                       # "Helvetica" — نفس خط النموذج
#  Phase E.1 §3: أُزيلت المعايرة العمودية المعتمِدة على البكسل
#  (‏``theme.SPACE["sm"] / scale``). إيقاع صفوف الهوية وموضع الجدول
#  ثابتان بالمليمتر في :mod:`ui.hr.paie.layout_spec` (‏``IDENT_ROW_STEP_MM``
#  · ``TABLE_HEAD_Y_MM``) — لا يتغيّران مع الزوم.
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

    def tfont(self, token):
        """خطّ من نظام الخطوط الموحَّد المشترك (:data:`layout_spec.TEXT`) —
        نفس الرموز يحوّلها المُصيِّر إلى Helvetica + نقطة (§9)."""
        mm_h, bold = L.TEXT[token]
        return self.font(mm_h, bold)


#  نظام الخطوط: مصدرٌ واحد مشترك في :mod:`ui.hr.paie.layout_spec` — Qt
#  يحوّله إلى ``QFont`` عبر ``_DocView.tfont``، وReportLab إلى نقطة عبر
#  ``layout_spec.pdf_font`` (§9). لا قيَم خطّ متناثرة في أيٍّ من المُصيِّرَين.
_TXT = L.TEXT                       # اسمٌ بديل تاريخيّ

#  مفتاح خليّة جدول ديناميكيّ: ``r{rid}_{cell}``.
_ROW_CELL_KEY = re.compile(r"^r\d+_[a-z]+$")


# ======================= نموذج صفوف جدول الكشف (Phase A2) =======================
#  abstraction صغير خاصّ بجدول هذا الكشف: يفصل «ما الصفوف؟» عن «كيف تُرسم؟».
#  كل صف يعرف نوعه الدلاليّ، دوره (أساسي/اختياري/نظام)، خلاياه القابلة
#  للتحرير، وكيف يتحوّل إلى entry لـ ``lignes.compute_bulletin``. الحساب
#  كلّه في المحرّك — الصفوف لا تحسب.

_YES, _NO = "نعم", "لا"
_C = T.PAIE_DEFAULT_CODES

#  ======================= نموذج المناطق (UX Redesign — R1) =======================
#  المبدأ: **مكان السطر = تصنيفه** (§1/§2). الجدول ثلاث مناطق حسابيّة:
#    • Zone A — فوق CNAS: يدخل CNAS و IRG.
#    • Zone B — بين CNAS/السلة/النقل و IRG: لا CNAS، يدخل IRG.
#    • Zone C — تحت IRG: لا CNAS ولا IRG.
#  أسماء Z1/Z2/Z3 لا تُعرَض للمستخدم — تخطيط داخليّ فقط. المنطقة قرار
#  المستخدم (موضع السطر) ولا تتحرّك تلقائياً بتغيّر LIBELLÉ (§19).
_ZONE_A, _ZONE_B, _ZONE_C = "A", "B", "C"
_ZONES = (_ZONE_A, _ZONE_B, _ZONE_C)

#  المنطقة الافتراضية لكلّ نوع اختياريّ عند إضافته (يبقى المستخدم حرّاً
#  ينقله لاحقاً عبر إعادة الإضافة/الحذف — R2). Absence/Retard/HS/IEP تؤثّر
#  قبل CNAS/IRG ⇒ Zone A (§21-§24). Prime الافتراضي «CNAS + IRG» ⇒ Zone A
#  (§25). Avance/Autre تحفّظاً ⇒ Zone C.
_DEFAULT_ZONE = {"iep": _ZONE_A, "hs": _ZONE_A, "absence": _ZONE_A,
                 "retard": _ZONE_A, "prime": _ZONE_A, "free": _ZONE_A,
                 "avance": _ZONE_C, "autre": _ZONE_C}

#  ================= نموذج الموضع البصريّ (Phase E.3 §2) =================
#  المنطقة = التصنيف الحسابيّ. **الشريحة (segment) + الترتيب (order)** =
#  الموضع البصريّ الذي اختاره المستخدم، **مستقلٌّ عن المنطقة**. خمس شرائح
#  بين الصفوف الثابتة:
#    A  : بعد الأجر القاعديّ، قبل CNAS   → Zone A
#    B1 : بعد CNAS، قبل PANIER           → Zone B
#    B2 : بعد PANIER، قبل TRANSPORT      → Zone B
#    B3 : بعد TRANSPORT، قبل IRG         → Zone B
#    C  : بعد IRG                        → Zone C
#  داخل كلّ شريحة يُحفَظ ترتيب الإدراج بالضبط (§1/§3/§5).
_SEGMENTS = ("A", "B1", "B2", "B3", "C")
_SEGMENT_ZONE = {"A": _ZONE_A, "B1": _ZONE_B, "B2": _ZONE_B, "B3": _ZONE_B,
                 "C": _ZONE_C}
_SEGMENT_RANK = {"A": 10, "B1": 30, "B2": 50, "B3": 70, "C": 90}
#  الشريحة التي تلي كلّ صفٍّ ثابت مباشرةً (الحدّ أسفله).
_SEGMENT_BELOW_ANCHOR = {"salaire": "A", "cnas": "B1", "panier": "B2",
                         "transport": "B3", "irg": "C"}
_ANCHOR_RANK = {"salaire": 0, "cnas": 20, "panier": 40, "transport": 60,
                "irg": 80}
#  الشريحة الافتراضية عند ``_add_row(kind)`` بلا موضع صريح.
_DEFAULT_SEGMENT = {"iep": "A", "hs": "A", "absence": "A", "retard": "A",
                    "prime": "A", "free": "A", "avance": "C", "autre": "C"}


def _legacy_zone(kind, cells):
    """منطقة سطرٍ من Work/Draft قديم لا يحمل ``segment``/``zone`` صريحاً
    (§5/§39): تُشتقّ من نوعه وتصنيفه القديم مرّة واحدة عند الاستعادة."""
    cells = cells or {}
    if kind in ("iep", "hs", "absence", "retard"):
        return _ZONE_A
    if kind == "prime":
        cot, imp = _soumis_class(cells.get("soumis") or _SOUMIS_CHOICES[0])
        return _ZONE_A if cot == _YES else (_ZONE_B if imp == _YES else _ZONE_C)
    if kind == "autre" and (cells.get("sens") or "Retenue") == "Gain":
        cot, imp = _soumis_class(cells.get("classe") or _SOUMIS_CHOICES[2])
        return _ZONE_A if cot == _YES else (_ZONE_B if imp == _YES else _ZONE_C)
    return _ZONE_C                                    # avance / autre-retenue


def _legacy_segment(kind, cells):
    """‏``segment`` لسطرٍ قديم بلا حقل ``segment`` (§5): Zone A → A ·
    Zone B → **B3** (قبل IRG) · Zone C → C."""
    return {_ZONE_A: "A", _ZONE_B: "B3", _ZONE_C: "C"}[_legacy_zone(kind, cells)]

#  Smart Next (Phase D): ما يُنقَل إلى الشهر التالي. الباقي (absence /
#  retard / hs / avance / autre) يُحذَف بالكامل — عرضيّ/شهريّ لا يتكرّر.
_SMART_NEXT_CARRY = {"salaire", "iep", "prime", "panier", "transport",
                     "cnas", "irg"}

#  تصنيف مالِيّ مُعلَن (بلا مصطلحات Zones): 3 خيارات تُترجَم إلى
#  (cotisable, imposable) — لا تخمين صامت (§0/§6).
_SOUMIS_CHOICES = ("CNAS + IRG", "IRG seul", "Net (ni CNAS ni IRG)")


def _soumis_class(label):
    if label.startswith("CNAS"):
        return _YES, _YES                      # Z1
    if label.startswith("IRG"):
        return _NO, _YES                       # Z2
    return _NO, _NO                            # Z3 (net)


#  المنطقة → (cotisable, imposable) للسطر الحرّ (§11): الموضع وحده يحسم
#  التصنيف الجبائيّ — لا ComboBox. Zone A = CNAS+IRG · Zone B = IRG فقط ·
#  Zone C = خارج الاثنين.
_ZONE_CLASS = {_ZONE_A: (_YES, _YES), _ZONE_B: (_NO, _YES), _ZONE_C: (_NO, _NO)}


# --------- تحويل الصفوف إلى entries لـ lignes.compute_bulletin ---------

def _free_entry(r):
    """السطر الحرّ (§8-§14). التصنيف الجبائيّ من المنطقة (الموضع):
      • GAIN — مسموحٌ في كلّ المناطق: Zone A ⇒ CNAS+IRG · Zone B ⇒ IRG
        فقط · Zone C ⇒ خارج الاثنين.
      • RETENUE حرّة — مسموحةٌ في **Zone C فقط** (اقتطاع صافٍ / Z4، وهو ما
        يطبّقه المحرّك فعلاً). في Zone A/B لا يملك المحرّك مساراً عامّاً
        باقتطاعٍ قبل الضريبة ⇒ **لا تُحتسَب** (§12/§13/§16) — تُبرَز
        للمراجعة، ويحوّلها المستخدم إلى Absence/Retard أو ينقلها لأسفل IRG.
    N/BASE و TAUX عرضٌ فقط — لا حساب تلقائيّ (§9)."""
    cot, imp = _ZONE_CLASS[r.zone]
    gain, ret = r.val("gain"), r.val("retenue")
    lbl = r.val("libelle") or "LIGNE LIBRE"
    if ret and not gain:
        if r.zone != _ZONE_C:
            return None                            # §13: غير مدعوم — لا يُحتسَب
        return {"type": "libre", "values": {
            "libelle": lbl, "montant": ret, "est_retenue": _YES,
            "cotisable": _NO, "imposable": _NO}}
    if not gain:
        return None
    return {"type": "libre", "values": {
        "libelle": lbl, "montant": gain, "est_retenue": _NO,
        "cotisable": cot, "imposable": imp}}


# ======================= التحويل الذكيّ (UX Redesign R3) =======================
#  LIBELLÉ المطابق لاسم نوع محرّك معروف يحوّل السطر الحرّ إليه (§14)،
#  وبالعكس. المطابقة **محافِظة** (§16): تطابق كامل بعد التطبيع أو اسمٌ
#  بديل موثوق — لا تخمين. لكلّ نوع منطقته المسموحة (§13/§19) و``code``
#  افتراضيّ (§20). Prime ليست نوعاً ذكياً — سطرٌ حرّ في منطقته (§25).
_SMART_TYPES = {
    "iep": {"zone": _ZONE_A, "code": "IEP", "label": "IEP / Ancienneté",
            "names": ("iep", "ancienneté", "anciennete", "ind. expérience prof.",
                      "indemnité d'expérience", "منحة الأقدمية", "الأقدمية")},
    "hs": {"zone": _ZONE_A, "code": "HS", "label": "Heures supplémentaires",
           "names": ("hs", "heures supplémentaires", "heures supp", "heures sup",
                     "h.s.", "ساعات إضافية", "ساعات اضافية")},
    "absence": {"zone": _ZONE_A, "code": "ABS", "label": "Absence",
                "names": ("absence", "absences", "abs", "غياب")},
    "retard": {"zone": _ZONE_A, "code": "RET", "label": "Retard",
               "names": ("retard", "retards", "تأخّر", "تاخر")},
    "avance": {"zone": _ZONE_C, "code": "AV", "label": "Avance / Retenue",
               "names": ("avance", "avance sur salaire", "acompte",
                         "retenue sur salaire", "تسبيق", "سلفة")},
}
#  أنواع فريدة (§24/§38): لا تُضاف مرّتين، وتُخفى من اقتراحات الأسطر الأخرى.
_SMART_UNIQUE = {"iep"}


def _norm_libelle(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _smart_match(text: str, zone: str):
    """نوع محرّك يطابق النصّ ضمن منطقته (§13/§16)، أو ``None`` (يبقى حرّاً)."""
    n = _norm_libelle(text)
    if not n:
        return None
    for k, spec in _SMART_TYPES.items():
        if spec["zone"] == zone and n in spec["names"]:
            return k
    return None


def _zone_smart_labels(zone: str, exclude=()):
    """تسميات الأنواع الذكيّة الصالحة لهذه المنطقة — للاقتراحات (§13)."""
    return [spec["label"] for k, spec in _SMART_TYPES.items()
            if spec["zone"] == zone and k not in exclude]


class _SmartLibelle(QLineEdit):
    """حقل LIBELLÉ ذكيّ (§12/§15): يبدو كخليّة صفراء نصّيّة عاديّة، لكن
    فيه إكمالٌ تلقائيّ (قائمة منسدلة عبر السهم ▾) واقتراحات مُرشَّحة
    بالمنطقة. لا يفرض الإكمال — الكتابة حرّة. يبثّ ``committed`` عند
    Enter/Tab/مغادرة التركيز/اختيار اقتراح (نقطة التحويل، §14)."""

    committed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrame(False)
        self._completer = QCompleter([], self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.PopupCompletion)
        self._completer.setFilterMode(Qt.MatchContains)
        self.setCompleter(self._completer)
        self._completer.activated[str].connect(self._on_activated)
        #  §19: القائمة تلتقط Enter/→ عندما تكون ظاهرةً — نُرشِّح حدثَها كي:
        #  Enter يُثبّت النصّ **كما كُتب** (لا يستبدله بالمظلَّل)، → يُكمِل
        #  الاقتراح الحاليّ إن كان المؤشّر في الآخر، Esc يُغلقها بلا مساس.
        self._completer.popup().installEventFilter(self)
        self.returnPressed.connect(lambda: self.committed.emit(self.text()))
        self.editingFinished.connect(lambda: self.committed.emit(self.text()))
        #  اقتراحاتٌ بعد حرفين على الأقلّ (سلوك Chrome — §19).
        self.textEdited.connect(self._on_text_edited)
        #  سهم ▾ داخل الحقل لفتح القائمة كاملةً (§12)
        self._arrow = QToolButton(self)
        self._arrow.setText("▾")
        self._arrow.setCursor(Qt.ArrowCursor)
        self._arrow.setFocusPolicy(Qt.NoFocus)
        self._arrow.setStyleSheet(
            "QToolButton{border:0;background:transparent;padding:0;"
            f"color:{theme.TEXT_DIM};}}")
        self._arrow.clicked.connect(self._open_popup)

    def set_suggestions(self, items):
        self._completer.setModel(QStringListModel(list(items), self._completer))

    def _open_popup(self):
        self.setFocus()
        self._completer.setCompletionPrefix("")
        self._completer.complete()

    def _on_activated(self, text):
        #  اختيارٌ صريح (نقرة فأرة على القائمة) — يُقبَل ويُثبَّت (§19).
        self.setText(text)
        self.committed.emit(text)

    def _on_text_edited(self, text):
        if len(text.strip()) < 2:
            self._completer.popup().hide()

    def _accept_current_completion(self) -> bool:
        """يُكمِل النصّ إلى الاقتراح الحاليّ إن كان امتداداً صالحاً له
        والمؤشّرُ في النهاية (§19: → عند وجود اقتراح). ``True`` إن قَبِل."""
        if self.cursorPosition() != len(self.text()) or self.hasSelectedText():
            return False
        cur = self._completer.currentCompletion()
        ct = self.text()
        if cur and cur != ct and cur.lower().startswith(ct.lower()):
            self.setText(cur)
            self._completer.popup().hide()
            return True
        return False

    def keyPressEvent(self, e):                                # noqa: N802
        key = e.key()
        pv = self._completer.popup().isVisible()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            #  §19: يُثبِّت النصّ الحاليّ كما هو — لا يستبدله بالمظلَّل.
            self._completer.popup().hide()
            self.committed.emit(self.text())
            return
        if key == Qt.Key_Escape and pv:
            self._completer.popup().hide()             # يُغلق، لا يمسّ النصّ
            return
        if key == Qt.Key_Right and self._accept_current_completion():
            return
        super().keyPressEvent(e)

    def eventFilter(self, obj, e):                             # noqa: N802
        if obj is self._completer.popup() and e.type() == QEvent.KeyPress:
            k = e.key()
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self._completer.popup().hide()
                self.committed.emit(self.text())      # النصّ كما كُتب (§19)
                return True
            if k == Qt.Key_Right and self._accept_current_completion():
                return True
            if k == Qt.Key_Escape:
                self._completer.popup().hide()
                return True
        return super().eventFilter(obj, e)

    def resizeEvent(self, e):                                  # noqa: N802
        super().resizeEvent(e)
        #  السهم يتبع ارتفاع الخليّة (يتناسب مع الزوم) — عرضه ~70% من
        #  الارتفاع، محدودٌ حتى لا يبتلع نصف الخليّة الضيّقة.
        s = max(9, min(int(self.height() * 0.72), int(self.width() * 0.5)))
        self._arrow.setFixedSize(s, self.height())
        self._arrow.move(self.width() - s, 0)
        self.setTextMargins(0, 0, s, 0)          # النصّ لا يمرّ تحت السهم


class _InlineChoice(QLineEdit):
    """خليّة اختيارٍ خفيفة (§21): مظهرُ خليّةٍ صفراء نصّيّة عاديّة (نفس
    الخطّ والارتفاع والحشو) مع سهمٍ صغير؛ نقرةٌ تفتح قائمةً منبثقة. بديلٌ
    لـ ``QComboBox`` الأصفر الثقيل — jours/heures و50%/100%. في القفل تبدو
    كنصّ وثيقة (السهم يُعطَّل، لا قائمة). واجهةُ ``currentText`` /
    ``setCurrentText`` متوافقةٌ مع ما تنتظره الشاشة."""

    changed = Signal(str)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self._options = [str(o) for o in options]
        self.setReadOnly(True)
        self.setFrame(False)
        self.setCursor(Qt.PointingHandCursor)
        if self._options:
            super().setText(self._options[0])
        self._arrow = QToolButton(self)
        self._arrow.setText("▾")
        self._arrow.setFocusPolicy(Qt.NoFocus)
        self._arrow.setCursor(Qt.ArrowCursor)
        self._arrow.setStyleSheet(
            "QToolButton{border:0;background:transparent;padding:0;"
            f"color:{theme.TEXT_DIM};}}")
        self._arrow.clicked.connect(self._popup)

    #  ---- توافق واجهة QComboBox المستعمَلة في الشاشة ----
    def currentText(self):
        return self.text()

    def setCurrentText(self, value):
        v = str(value or "")
        if self._options and v not in self._options:
            v = self._options[0]
        if v != self.text():
            super().setText(v)

    def _enabled_for_edit(self):
        return self._arrow.isEnabled()          # القفل يعطّل السهم

    def _popup(self):
        if not self._enabled_for_edit():
            return
        m = QMenu(self)
        for opt in self._options:
            m.addAction(opt, lambda o=opt: self._pick(o))
        m.exec(self.mapToGlobal(self.rect().bottomLeft()))

    def _pick(self, opt):
        if opt != self.text():
            super().setText(opt)
            self.changed.emit(opt)

    def mousePressEvent(self, e):                              # noqa: N802
        if self._enabled_for_edit():
            self._popup()
        # لا super() — لا وضعَ مؤشّرٍ نصّيّ

    def keyPressEvent(self, e):                                # noqa: N802
        if not self._enabled_for_edit():
            return
        if e.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter,
                       Qt.Key_Down):
            self._popup()
            return
        super().keyPressEvent(e)

    def resizeEvent(self, e):                                  # noqa: N802
        super().resizeEvent(e)
        s = max(9, min(int(self.height() * 0.72), int(self.width() * 0.5)))
        self._arrow.setFixedSize(s, self.height())
        self._arrow.move(self.width() - s, 0)
        self.setTextMargins(0, 0, s, 0)


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
    #  ---- الأنواع الذكيّة (R3): LIBELLÉ ذكيّ + CODE قابل للتحرير (§12/§20).
    #  jours/heures و50/100 خياراتٌ **داخل** السطر في عمود TAUX (§21/§23).
    "iep": dict(
        role="optional", code="IEP", lib="IND. EXPÉRIENCE PROF.",
        primary="taux", computed="gain", lignes_key="iep",
        cells=(_cs("code", "code", "text", default="IEP"),
               _cs("libelle", "libelle", "smart", default="IEP / Ancienneté"),
               _cs("taux", "taux", "amount")),
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
        cells=(_cs("code", "code", "text", default="HS"),
               _cs("libelle", "libelle", "smart",
                   default="Heures supplémentaires"),
               _cs("qty", "nbase", "amount"),
               _cs("coef", "taux", "choice", ("50%", "100%"), "50%")),
        to_entry=lambda r: {"type": _hs_type(r),
                            "values": {"heures": r.val("qty")}}),
    #  Absence/Retard = Z1: تُنقِص وعاء [A] و``total_gains`` في المحرّك (لا
    #  يُغيَّر — §30). العرضُ (E.3 §9) **اقتطاعٌ موجب في عمود RETENUE**؛
    #  المجاميع تُصالَح في :mod:`ui.hr.paie.presentation`.
    "absence": dict(
        role="optional", code="ABS", lib="", primary="qty",
        computed="retenue", lignes_key=_abs_type,
        cells=(_cs("code", "code", "text", default="ABS"),
               _cs("libelle", "libelle", "smart", default="Absence"),
               _cs("qty", "nbase", "amount"),
               _cs("mode", "taux", "choice",
                   ("Absence (jours)", "Absence (heures)"), "Absence (jours)")),
        to_entry=_abs_entry),
    "retard": dict(
        role="optional", code="RET", lib="RETARD", primary="qty",
        computed="retenue", lignes_key="retard",
        cells=(_cs("code", "code", "text", default="RET"),
               _cs("libelle", "libelle", "smart", default="Retard"),
               _cs("qty", "nbase", "amount")),
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
        role="optional", code="AV", lib="", primary="montant",
        cells=(_cs("code", "code", "text", default="AV"),
               _cs("libelle", "libelle", "smart", default="Avance / Retenue"),
               _cs("montant", "retenue", "amount")),
        to_entry=_avance_entry),
    "autre": dict(
        role="optional", code="", lib="", primary="montant",
        cells=(_cs("code", "code", "text"), _cs("libelle", "libelle", "text"),
               _cs("sens", "taux", "choice", ("Retenue", "Gain"), "Retenue"),
               _cs("classe", "nbase", "choice", _SOUMIS_CHOICES, _SOUMIS_CHOICES[2]),
               _cs("montant", _AUTRE_MONTANT_COL, "amount")),
        to_entry=_autre_entry),
    #  ------- السطر الحرّ (UX Redesign R2) — نوع الإضافة الافتراضيّ -------
    #  ستّ خلايا نصّيّة/رقميّة، بلا أيّ ComboBox رماديّ (§8/§29). N/BASE و
    #  TAUX عرضٌ فقط (§9)؛ القيمة الحقيقيّة في GAIN أو RETENUE (§10).
    #  التصنيف الجبائيّ من المنطقة لا من حقل (§11).
    "free": dict(
        role="optional", code="", lib="", primary="",
        cells=(_cs("code", "code", "text"),
               _cs("libelle", "libelle", "smart"),
               _cs("nbase", "nbase", "amount"),
               _cs("taux", "taux", "amount"),
               _cs("gain", "gain", "amount"),
               _cs("retenue", "retenue", "amount")),
        to_entry=_free_entry),
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

_MAX_BODY_ROWS = 18          # حدّ عمليّ (لا pagination) — §31

#  خلايا الاختيار التي تستعمل :class:`_InlineChoice` الخفيفة (§21) بدل
#  ``QComboBox`` — Absence(jours/heures) و HS(50%/100%). prime/autre تبقى
#  ComboBox (أنواعٌ قديمة غير مُتاحة للإضافة).
_INLINE_CHOICE_CELLS = {"coef", "mode"}

_COL_ALIGN = {"code": Qt.AlignHCenter, "libelle": Qt.AlignLeft,
              "nbase": Qt.AlignRight, "taux": Qt.AlignRight,
              "gain": Qt.AlignRight, "retenue": Qt.AlignRight}


class _Row:
    """صفّ واحد في جدول الكشف. يملك widgetات خلاياه القابلة للتحرير
    (‏``QLineEdit`` / ``QComboBox``، مسجَّلة في ``screen._widgets`` بمفتاح
    ``r{rid}_{cell}``). المبلغ المحسوب (IEP/Absence/Retard/HS) **ليس**
    widgetاً — يُرسَم من ``BulletinView``."""

    def __init__(self, screen: "BulletinTemplateScreen", kind: str, rid: int,
                 segment: str = None, order: float = None):
        self.screen = screen
        self.kind = kind
        self.rid = rid
        spec = _ROW_SPECS[kind]
        self.role = spec["role"]
        #  الموضع البصريّ (§2) — للصفوف الاختيارية فقط؛ الثابتة تُرتَّب
        #  بمرتكزاتها. ``segment`` تُمرَّر عند الإدراج/الاستعادة، و``order``
        #  رقمٌ متزايدٌ داخل الشريحة يُعاد تسويته بـ ``_reindex_segments``.
        if self.role == "optional":
            self.segment = (segment if segment in _SEGMENTS
                            else _DEFAULT_SEGMENT.get(kind, "C"))
            self.order = (float(order) if order is not None
                          else float(screen._alloc_order(self.segment)))
        else:
            self.segment = None
            self.order = 0.0
        #  حالة مراجعة (§8/§15): "" | "duplicate_unique" | "free_retenue_ab".
        self._review = ""
        self.code = spec["code"]
        self.libelle = spec["lib"]
        self._cellspec = {c["name"]: c for c in spec["cells"]}
        self.widgets = {}
        self._amount = None                       # المبلغ المحسوب (إن وُجد)
        self._iep_manual = False
        self._code_manual = False                 # §20: CODE عُدِّل يدوياً؟
        for c in spec["cells"]:
            name, k = c["name"], self.cell_key(c["name"])
            if c["kind"] == "choice" and name in _INLINE_CHOICE_CELLS:
                #  §21: jours/heures و50%/100% — خليّةٌ خفيفة لا ComboBox ثقيل.
                w = _InlineChoice(c["opts"], screen._canvas)
                w.changed.connect(lambda _t, kk=k: screen._on_row_edit(kk))
            elif c["kind"] == "choice":
                w = QComboBox(screen._canvas)
                w.addItems(c["opts"])
                w.currentTextChanged.connect(
                    lambda _t, kk=k: screen._on_row_edit(kk))
            elif c["kind"] == "smart":
                w = _SmartLibelle(screen._canvas)
                w.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                w.textChanged.connect(lambda _t, kk=k: screen._on_row_edit(kk))
                w.committed.connect(
                    lambda _t=None, rr=self: screen._on_libelle_committed(rr))
            else:
                w = QLineEdit(screen._canvas)
                w.setFrame(False)
                col = self.column(name)
                w.setAlignment(_COL_ALIGN.get(col, Qt.AlignLeft) | Qt.AlignVCenter)
                w.textChanged.connect(lambda _t, kk=k: screen._on_row_edit(kk))
                w.returnPressed.connect(lambda kk=k: screen._focus_rel(kk, +1))
                if name == "code":
                    w.textEdited.connect(
                        lambda _t=None, rr=self: setattr(rr, "_code_manual", True))
            w.setLayoutDirection(Qt.LeftToRight)
            w.installEventFilter(screen)
            self.widgets[name] = w
            screen._widgets[k] = w
            #  القيمة الافتراضية **بعد** التسجيل (وإلا يصطدم ``textChanged``
            #  بـ ``_style_field`` قبل وجود المفتاح)، ومكتومةٌ حتى لا تُطلِق
            #  إعادة حساب/تعليم «غير محفوظ» أثناء البناء.
            if c["default"]:
                screen._suspend.add(k)
                try:
                    if isinstance(w, QComboBox):
                        w.setCurrentText(c["default"])
                    else:
                        w.setText(c["default"])
                finally:
                    screen._suspend.discard(k)
            w.show()
        #  Phase E §3: كلّ خلايا الجدول تبدأ بنمطها الصفراء النظيف — لا
        #  حالة رماديّة ثمّ صفراء عند التركيز.
        for name in self.widgets:
            screen._style_field(self.cell_key(name))

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
        if hasattr(w, "setCurrentText"):          # QComboBox / _InlineChoice
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

    @property
    def zone(self):
        """المنطقة الحسابيّة — **مشتقّة** من الشريحة (§2): لا تُخزَّن ولا
        تُضبَط مباشرةً. الشريحة هي القرار."""
        return _SEGMENT_ZONE.get(self.segment, _ZONE_C)

    def sort_key(self):
        #  الصفوف الثابتة تُرسي حدود الشرائح؛ الاختيارية داخل شريحتها
        #  بترتيب الإدراج الدقيق (§1/§3). الموضع قرار المستخدم — لا ترتيب
        #  دلاليّ حسب النوع.
        if self.role != "optional":
            return (_ANCHOR_RANK.get(self.kind, 999), -1.0)
        return (_SEGMENT_RANK[self.segment], self.order)

    def entry(self):
        return _ROW_SPECS[self.kind].get("to_entry", lambda _r: None)(self)

    def dispose(self):
        #  Phase E.2: كتم إشارات كلّ خليّة **قبل** فكّ الأبوّة. ``setParent
        #  (None)`` على حقلٍ له تركيز يُطلق ``editingFinished`` ⇒
        #  ``_SmartLibelle.committed`` ⇒ ``_on_libelle_committed`` من جديد
        #  أثناء الهدم = تحويلٌ متداخل يخلّف widgetات يتيمة على اللوحة.
        for cell, w in list(self.widgets.items()):
            w.blockSignals(True)
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


def _silent_unlink(*paths_):
    for p in paths_:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


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
        base_text(0, T.ADHERENT_BASELINE, "N° ADHÉRENT", v.tfont("block_labels"))

        # شريط العنوان الأسود
        p.fillRect(int(X(0)), int(Y(T.BAND_TITLE_Y)),
                   int(X(T.CONTENT_W) - X(0)), int(Y(T.BAND_TITLE_H) - Y(0)),
                   QColor(theme.BAND_BLACK))
        base_text(3, T.BAND_BASELINE, "BULLETIN DE PAIE",
                  v.tfont("header_title"), QColor("white"))

        # صندوق الهوية + تسمياته — إيقاع عموديّ ثابتٌ بالمليمتر (§3)
        p.setPen(ink)
        p.drawRect(int(X(0)), int(Y(T.IDENT_Y)),
                   int(X(T.CONTENT_W) - X(0)), int(v.px(sc._ident_h())))
        for _k, lbl, xl, xv, wv, row, _ml, kind in T.IDENT_FIELDS:
            if lbl:
                base_text(xl, sc._ident_row_y(row), f"{lbl} :",
                          v.tfont("block_labels"))
        a_x, _lieu_x = sc._row1_layout()
        base_text(a_x, sc._ident_row_y(1), "à", v.tfont("block_labels"))

        # كتلة الجدول: مواضعها مليمترٌ مطلق من المواصفة (لا إزاحة معتمِدة زوم)
        def Yt(mm):
            return Y(mm)

        # ---- جسم الجدول: نموذج المناطق (R1) ----
        #  ``nb`` = الصفوف الفعليّة (محتوى)؛ ``nb_drawn`` = أسطر الشبكة
        #  المرسومة (فعليّة + حشو فارغ تحت IRG حتى MIN_BODY_SLOTS، §4).
        rows = sc._visible_body_rows()
        nb = len(rows)
        nb_drawn = sc._n_body_drawn()
        bottom_mm = T.BODY_TOP + nb_drawn * T.ROW_H
        total_mm = bottom_mm                          # متّصل — لا فجوة (§31)
        net_mm = total_mm + T.ROW_H
        table_bot = net_mm + T.ROW_H                  # أسفل TOTAL/NET

        # ترويسة الجدول + الأعمدة — الإطار الخارجيّ امتدادٌ واحد من
        # الترويسة حتى أسفل NET (§31: لا خطّ عائم).
        hy0, hy1 = Yt(T.TABLE_HEAD_Y), Yt(T.TABLE_HEAD_Y + T.ROW_H + 1)
        p.setPen(ink)
        p.drawRect(int(X(0)), int(hy0), int(X(T.CONTENT_W) - X(0)), int(hy1 - hy0))
        for _key, f0, _f1, _al, title in T.COLS:
            p.setPen(ink)
            p.drawLine(int(col_x(f0)), int(hy0), int(col_x(f0)), int(Yt(bottom_mm)))
            p.setFont(v.tfont("table_header"))
            fm = QFontMetricsF(p.font())
            p.drawText(QPoint(int(col_x(f0) + 2.5 * scale),
                              int((hy0 + hy1) / 2 + fm.ascent() / 2 - fm.descent() / 2)),
                       title)
        # الحوافّ العموديّة الخارجيّة تمتدّ حتى أسفل NET (جدول واحد متّصل)
        p.setPen(ink)
        p.drawLine(int(X(0)), int(hy1), int(X(0)), int(Yt(table_bot)))
        p.drawLine(int(X(T.CONTENT_W)), int(hy1), int(X(T.CONTENT_W)), int(Yt(table_bot)))

        p.setPen(QColor(theme.GRID_LINE))
        for r in range(nb_drawn + 1):
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
            tok = "computed_value" if color is cc else "table_body"
            f = v.tfont(tok)
            f.setBold(bool(bold) or f.bold())
            self._cell(p, px, Yt(row_mid(i)),
                       s, {"c": "center", "e": "e", "w": "w"}[anchor], f, color)

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
                # المبلغ المحسوب (IEP/HS في GAIN · Absence/Retard **موجباً**
                # في RETENUE، §9) — خليّةٌ للقراءة تُرسَم من BulletinView.
                spec = _ROW_SPECS[row.kind]
                col = spec.get("computed")
                if col and computed and row._amount is not None:
                    cell(col, i, fmt_montant(abs(row._amount)), "e", cc)

        # ---- TOTAL / NET À PAYER: بنيتهما تُرسَم **دائماً** (§3/§30) ----
        #  القيَم وحدها تبقى فارغة إذا تعذّر الحساب — «غير محسوبة» ≠ «صفر».
        #  TOTAL صفٌّ هادئ من الجدول؛ NET شريطٌ أسود بنصٍّ أبيض — المرساة
        #  البصريّة النهائيّة، بنفس روح شريط BULLETIN DE PAIE (§E.6/§E.7).
        tf = v.tfont("total_row")
        nf = v.tfont("net_row")
        ty0 = Yt(total_mm)
        p.setPen(ink)
        p.drawLine(int(X(0)), int(ty0), int(X(T.CONTENT_W)), int(ty0))
        p.drawLine(int(X(0)), int(Yt(net_mm)),
                   int(X(T.CONTENT_W)), int(Yt(net_mm)))
        #  المجاميع المعروضة من طبقة العرض المشتركة (§10/§11): TOTAL_GAIN و
        #  TOTAL_RETENUE مُصالَحان مع Absence/Retard الموجبة، والصافي من
        #  المحرّك بلا تغيير — فينطبق  Σgain − Σretenue == net.
        pres = getattr(sc, "_presented", None)
        mid = Yt(total_mm + T.ROW_H / 2)
        self._cell(p, col_x(T._colf("taux")[1]) - 3 * scale, mid, "TOTAL",
                   "e", tf, ink)
        if computed and pres is not None:
            self._cell(p, col_x(T._colf("gain")[1]) - 2.5 * scale, mid,
                       pres.total_gain_str, "e", tf, cc)
            self._cell(p, col_x(T._colf("retenue")[1]) - 2.5 * scale, mid,
                       pres.total_retenue_str, "e", tf, cc)

        #  NET — شريط أسود يملأ صفّه داخل الشبكة المتّصلة (لا يطفو، ارتفاعه
        #  = ROW_H بالضبط). النصّ والقيمة بيضاوان.
        p.fillRect(int(X(0)), int(Yt(net_mm)),
                   int(X(T.CONTENT_W) - X(0)), int(Yt(table_bot) - Yt(net_mm)),
                   QColor(theme.BAND_BLACK))
        p.setPen(ink)
        p.drawLine(int(X(0)), int(Yt(table_bot)),
                   int(X(T.CONTENT_W)), int(Yt(table_bot)))
        midn = Yt(net_mm + T.ROW_H / 2)
        self._cell(p, col_x(T._colf("taux")[1]) - 3 * scale, midn,
                   "NET À PAYER", "e", nf, QColor("white"))
        if computed and pres is not None:
            self._cell(p, col_x(T._colf("retenue")[1]) - 2.5 * scale, midn,
                       pres.net_str, "e", nf, QColor("white"))

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
    DRAFT_VERSION = 6          # E.3: نموذج الشريحة+الترتيب (الموضع البصريّ)

    #  أدنى عدد أسطر مرسومة تحت IRG (منطقة Zone C + فراغ) قبل TOTAL/NET —
    #  يُبقي أسفل الوثيقة ثابتاً بصرياً مهما قلّت الأسطر (§4). المساحة
    #  الزائدة شبكةٌ فارغة مرسومة، لا widgets وهميّة.
    MIN_BODY_SLOTS = L.MIN_BODY_SLOTS

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
        self._presented = None                          # PZ.Presented (طبقة العرض)
        self._computed = False                 # نتيجة حقيقية مقابل «غير محسوبة»

        self.build_ui()
        self.toolbar.setVisible(False)         # لا شريط أدوات في التصميم القديم
        self._build_fields()
        self._build_gutter_controls()          # أزرار ＋/－ على هامش الجدول (R2)
        self._init_default_rows()
        self._rebuild_nav()
        self.on_activate()
        QTimer.singleShot(0, self._relayout)
        self._recompute()
        self._dirty = False        # بناء الشاشة الافتراضية ليس «تعديل مستخدم»
        self._update_state_indicator()

    # ================== نموذج الصفوف — نموذج المناطق (R1) ==================
    #  النواة الثابتة فقط (§3): الأجر · CNAS · السلة · النقل · IRG. لا سطر
    #  Prime افتراضيّ — الإضافة تصير من الجدول نفسه (R2). TOTAL/NET يُرسمان
    #  دائماً بعدها.
    _FIXED_KINDS = ("salaire", "panier", "transport", "cnas", "irg")

    def _init_default_rows(self):
        for kind in self._FIXED_KINDS:
            self._rows.append(_Row(self, kind, self._next_rid))
            self._next_rid += 1
        sr = next(r for r in self._rows if r.kind == "salaire")
        self._widgets["r%d_nbase" % sr.rid].setText("30")           # jours

    def _ordered_rows(self):
        return sorted(self._rows, key=lambda r: r.sort_key())

    def _visible_body_rows(self):
        """الصفوف بترتيب الشرائح (§3): الأجر → [A] → CNAS → [B1] → PANIER →
        [B2] → TRANSPORT → [B3] → IRG → [C]."""
        return self._ordered_rows()

    def _segment_rows(self, segment):
        """الصفوف الاختيارية في شريحةٍ مرتَّبةً بترتيبها الدقيق."""
        return sorted((r for r in self._rows
                       if r.role == "optional" and r.segment == segment),
                      key=lambda r: r.order)

    def _zone_rows(self, zone):
        return [r for r in self._rows
                if r.role == "optional" and r.zone == zone]

    def _row_index(self, row) -> int:
        return self._visible_body_rows().index(row)

    # ---------- ترتيب الشرائح: تخصيص/تسوية الأرقام (§2/§5) ----------
    def _alloc_order(self, segment):
        return 1.0 + max((r.order for r in self._rows if r.role == "optional"
                          and r.segment == segment), default=-1.0)

    def _reindex_segments(self):
        """يُعيد تسوية ``order`` إلى ``0,1,2,…`` داخل كلّ شريحة (يمنع انجراف
        الكسور بعد عدّة إدراجات) دون تغيير الترتيب المرئيّ."""
        for seg in _SEGMENTS:
            for j, r in enumerate(self._segment_rows(seg)):
                r.order = float(j)

    def _add_row(self, kind: str, segment: str = None):
        """إضافةٌ إلى **آخر** الشريحة (المسار الافتراضيّ/القديم)."""
        if not self._can_add_smart(kind):                  # §7: IEP فريدة
            self.status.setText(
                f"«{_SMART_TYPES[kind]['label']}» موجودة مسبقاً — سطرٌ واحد فقط.")
            return None
        seg = segment if segment in _SEGMENTS \
            else _DEFAULT_SEGMENT.get(kind, "C")
        return self._insert_row_at(kind, seg, len(self._segment_rows(seg)))

    def _insert_row_at(self, kind: str, segment: str, index: int):
        """يُدرج صفّاً **في الموضع الدقيق** ``index`` داخل ``segment`` (§1/§3):
        يُزاح ما بعده ثمّ تُسوَّى الأرقام."""
        if self._locked:                          # 🔒 — لا تعديل بنية
            return None
        if len([r for r in self._rows
                if r.role != "system"]) + 2 >= _MAX_BODY_ROWS:      # §31
            from ui2.alerts import warn
            warn(self, self.TITLE,
                 ["بلغ الجدول الحدّ الأقصى للصفوف — احذف صفاً قبل الإضافة."])
            return None
        seg = segment if segment in _SEGMENTS else "A"
        index = max(0, min(int(index), len(self._segment_rows(seg))))
        r = _Row(self, kind, self._next_rid, segment=seg, order=index - 0.5)
        self._next_rid += 1
        self._rows.append(r)
        self._reindex_segments()
        self._refresh_libelle_suggestions()
        self._rebuild_nav()
        self._sync_row_styles()
        self.mark_dirty()
        self._recompute()
        self._relayout()
        cells = _ROW_SPECS[kind]["cells"]
        if cells:
            first = "libelle" if any(c["name"] == "libelle" for c in cells) \
                else cells[0]["name"]
            self._widgets[r.cell_key(first)].setFocus()
        return r

    # ---------- حارس النوع الفريد على مستوى النموذج (§7/§20) ----------
    def _can_add_smart(self, kind: str, exclude=None) -> bool:
        """‏``False`` إن كان ``kind`` نوعاً فريداً وموجوداً أصلاً (عدا
        ``exclude``). المرجعُ الوحيد — الاقتراحات مجرّد تسهيلٍ بصريّ."""
        if kind not in _SMART_UNIQUE:
            return True
        return not any(r.kind == kind and r is not exclude
                       for r in self._rows)

    def _dedupe_unique(self) -> bool:
        """يُبقي أوّل صفٍّ من كلّ نوعٍ فريد، ويُنزِّل الباقي إلى «حرّ + مراجعة»
        مع الحفاظ على بيانات المستخدم المرئيّة (§8). ``True`` إن غيّر شيئاً."""
        seen, changed = set(), False
        for i, r in enumerate(list(self._rows)):
            if r.kind not in _SMART_UNIQUE:
                continue
            if r.kind in seen:
                lbl = r.val("libelle") or _SMART_TYPES[r.kind]["label"]
                #  §8: لا نفقد بيانات المستخدم — نُضمّن قيمة المدخل القديم
                #  (النسبة) في التسمية المرئيّة قبل التنزيل إلى «حرّ».
                extra = " ".join(f"{c}={r.val(c)}" for c in ("taux", "code")
                                 if r.val(c))
                code = r.val("code")
                seg, order, rid = r.segment, r.order, r.rid
                r.dispose()
                fr = _Row(self, "free", rid, segment=seg, order=order)
                fr._review = "duplicate_unique"
                fr.set_val("libelle",
                           f"{lbl} (DOUBLON à revoir{' — ' + extra if extra else ''})")
                if code:
                    fr.set_val("code", code)
                self._rows[i] = fr
                changed = True
            else:
                seen.add(r.kind)
        return changed

    # ============= LIBELLÉ ذكيّ + التحويل (UX Redesign R3) =============
    def _refresh_libelle_suggestions(self):
        """يضبط اقتراحات كلّ حقل LIBELLÉ ذكيّ حسب منطقة سطره، ويستبعد
        الأنواع الفريدة الموجودة أصلاً (§13/§19/§24)."""
        present_unique = {r.kind for r in self._rows
                          if r.kind in _SMART_UNIQUE}
        for r in self._rows:
            w = r.widgets.get("libelle")
            if isinstance(w, _SmartLibelle):
                exclude = {u for u in present_unique if u != r.kind}
                w.set_suggestions(_zone_smart_labels(r.zone, exclude))

    def _on_libelle_committed(self, row):
        """LIBELLÉ سُلِّم (Enter/Tab/مغادرة/اختيار — §14/§15): طابِقه مع
        نوعٍ ذكيّ صالحٍ لمنطقة السطر (§13/§16). تطابق ⇒ حوِّل النوع في
        المكان (§14/§18)؛ لا تطابق على سطرٍ ذكيّ ⇒ رجوعٌ إلى «حرّ»؛ لا
        تطابق على «حرّ» ⇒ يبقى حرّاً (§16)."""
        if self._locked or row not in self._rows:
            return
        w = row.widgets.get("libelle")
        if not isinstance(w, _SmartLibelle):
            return
        text = w.text().strip()
        target = _smart_match(text, row.zone)
        if target == row.kind:
            return
        if target is None:
            if row.kind != "free":
                self._convert_row(row, "free", keep_libelle=text)
            return
        #  §7/§20: حارس النوع الفريد على مستوى النموذج — لا سطرٌ ذكيّ ثانٍ
        #  حتى لو كُتب الاسم يدوياً.
        if not self._can_add_smart(target, exclude=row):
            self.status.setText(
                f"«{_SMART_TYPES[target]['label']}» موجودة مسبقاً — سطرٌ واحد "
                "فقط. بقي السطر حرّاً.")
            return
        self._convert_row(row, target)

    def _convert_row(self, row, new_kind, *, keep_libelle=None):
        """يحوّل ``row`` إلى ``new_kind`` **في المكان** (§18): نفس الشريحة
        و``order`` (§2 — لا نقل بين المواضع). لا تُنقَل القيَم غير المتوافقة
        — فقط CODE إن كان يدوياً، وLIBELLÉ الحرّ إن طُلِب."""
        #  حارس إعادة الدخول: تغيير التركيز أثناء التحويل قد يعيد إطلاق
        #  ``_on_libelle_committed`` ⇒ تحويلٌ متداخل يخلّف widgetات يتيمة.
        if getattr(self, "_converting", False):
            return None
        try:
            i = self._rows.index(row)
        except ValueError:
            return None
        #  §7/§20: لا نوعٌ فريد ثانٍ (حتى استدعاءً مباشراً).
        if not self._can_add_smart(new_kind, exclude=row):
            return None
        self._converting = True
        try:
            keep_code = row.val("code") if row._code_manual else None
            code_manual = row._code_manual
            seg, order, rid = row.segment, row.order, row.rid
            row.dispose()
            nr = _Row(self, new_kind, rid, segment=seg, order=order)
            nr._code_manual = code_manual
            if keep_code:
                nr.set_val("code", keep_code)
            if keep_libelle is not None and "libelle" in nr.widgets:
                nr.set_val("libelle", keep_libelle)
            self._rows[i] = nr
            self._refresh_libelle_suggestions()
            self._rebuild_nav()
            self._sync_row_styles()
            self.mark_dirty()
            self._recompute()
            self._relayout()
            first_edit = next((c["name"] for c in _ROW_SPECS[new_kind]["cells"]
                               if c["kind"] != "smart"
                               and c["name"] not in ("code",)), None)
            if first_edit:
                self._widgets[nr.cell_key(first_edit)].setFocus()
        finally:
            self._converting = False
        return nr

    #  الشريحة الافتراضية لكلّ منطقة (Zone B ⇒ B3، قبل IRG).
    _ZONE_DEFAULT_SEGMENT = {_ZONE_A: "A", _ZONE_B: "B3", _ZONE_C: "C"}

    def _insert_free_row(self, zone: str):
        """يُدرج سطراً حرّاً في آخر شريحة المنطقة (المسار المختصر — الاختبارات
        والإدراج غير المتموضع). الإدراج الدقيق عبر ``_insert_row_at``."""
        seg = self._ZONE_DEFAULT_SEGMENT.get(zone, "A")
        return self._insert_row_at("free", seg, len(self._segment_rows(seg)))

    def _gutter_target(self, mm_y: float):
        """‏``(segment, index)`` للحدّ الأقرب لموضع ``mm_y`` بين **صفوفٍ
        فعليّة** (§1/§3/§4)، أو ``None`` إن كان الحدّ فوق الأجر القاعديّ
        (§3A — لا ＋ هناك). الأسطر الفارغة تحت آخر صفّ Zone C تنطبق على
        «بعد آخر صفّ C»."""
        rows = self._visible_body_rows()
        nb = len(rows)
        b = int(round((mm_y - T.BODY_TOP) / T.ROW_H))
        b = max(0, min(nb, b))
        if b == 0:
            return None
        above = rows[b - 1]
        seg = (above.segment if above.role == "optional"
               else _SEGMENT_BELOW_ANCHOR[above.kind])
        idx = sum(1 for r in rows[:b]
                  if r.role == "optional" and r.segment == seg)
        return seg, idx

    # ============= أزرار ＋/－ على هامش الجدول (Word-like — §6/§7/§33) =============
    def _build_gutter_controls(self):
        """زرّان صغيران على الهامش الأيسر للجدول: ＋ يُدرج سطراً حرّاً في
        المنطقة تحت المؤشّر، － يحذف السطر الاختياريّ تحت المؤشّر. يظهران
        بالـ hover فقط، يختفيان في القفل، وليسا جزءاً من الرسم (فلا يظهران
        في DOCX/PDF)."""
        from PySide6.QtWidgets import QToolButton
        self._plus_target = None            # (segment, index) للإدراج الدقيق
        self._minus_row = None
        self._btn_plus = QToolButton(self._canvas)
        self._btn_plus.setText("＋")
        self._btn_plus.setCursor(Qt.PointingHandCursor)
        self._btn_plus.setToolTip("إدراج سطر هنا")
        self._btn_plus.clicked.connect(
            lambda: self._plus_target is not None
            and self._insert_row_at("free", *self._plus_target))
        self._btn_minus = QToolButton(self._canvas)
        self._btn_minus.setText("－")
        self._btn_minus.setCursor(Qt.PointingHandCursor)
        self._btn_minus.setToolTip("حذف هذا السطر")
        self._btn_minus.clicked.connect(
            lambda: self._minus_row is not None
            and self._remove_row(self._minus_row))
        self._btn_plus.setStyleSheet(
            f"QToolButton {{ background:{theme.SURFACE}; "
            f"border:1px solid {theme.PRIMARY}; border-radius:9px; "
            f"color:{theme.PRIMARY}; font-weight:700; padding:0; }}"
            f"QToolButton:hover {{ background:{theme.PRIMARY}; color:#fff; }}")
        self._btn_minus.setStyleSheet(
            f"QToolButton {{ background:{theme.SURFACE}; "
            f"border:1px solid {theme.DANGER}; border-radius:9px; "
            f"color:{theme.DANGER}; font-weight:700; padding:0; }}"
            f"QToolButton:hover {{ background:{theme.DANGER}; color:#fff; }}")
        self._btn_plus.hide()
        self._btn_minus.hide()
        self._canvas.setMouseTracking(True)

    def _hide_gutter_controls(self):
        self._plus_target = None
        self._minus_row = None
        for b in (getattr(self, "_btn_plus", None),
                  getattr(self, "_btn_minus", None)):
            if b is not None:
                b.hide()

    def _gutter_mouse_move(self, canvas_pos):
        """يُستدعى من ``eventFilter`` عند حركة الفأرة فوق اللوحة (§E.5):
        ＋ في الهامش **الأيسر** عند حدّ الصفّ (إدراج سطر في تلك المنطقة)،
        － في الهامش **الأيمن** مقابل الصفّ الاختياريّ (حذفه). لا يجتمعان،
        ولا يغطّيان محتوى الجدول، ويتبعان الزوم عبر ``_DocView``."""
        if self._locked or not hasattr(self, "_btn_plus"):
            return
        v = self._view()
        mm_x = (canvas_pos.x() - v.x0) / v.scale - T.MARGIN_L
        mm_y = (canvas_pos.y() - v.y0) / v.scale
        top = T.BODY_TOP
        n = self._n_body_drawn()
        bot = top + n * T.ROW_H
        if not (top - 2.0 <= mm_y <= bot + 2.0):
            self._hide_gutter_controls()
            return
        size = max(13, min(24, int(v.px(4.4))))
        rows = self._visible_body_rows()
        r_idx = int((mm_y - top) // T.ROW_H)
        nb_real = len(rows)

        #  ＋ — الهامش الأيسر فقط (‎-13..+2mm‎)، عند أقرب حدّ **صفٍّ فعليّ**
        #  (§4: الأسطر الفارغة تنطبق على «بعد آخر صفّ C»). موضع الإدراج
        #  الدقيق = (segment, index) لا مجرّد المنطقة.
        b_real = max(0, min(nb_real, int(round((mm_y - top) / T.ROW_H))))
        target = self._gutter_target(mm_y)
        if -13.0 <= mm_x <= 2.0 and target is not None:
            self._plus_target = target
            self._btn_plus.setFixedSize(size, size)
            self._btn_plus.move(int(v.x(-6.0) - size),
                                int(v.y(top + b_real * T.ROW_H) - size / 2))
            self._btn_plus.raise_()
            self._btn_plus.show()
        else:
            self._plus_target = None
            self._btn_plus.hide()

        #  － — الهامش الأيمن فقط (خارج الجدول: من حافته إلى ‎+14mm‎)، مقابل
        #  صفٍّ اختياريّ. لا يظهر على الصفوف الثابتة/النظام.
        self._minus_row = None
        if (T.CONTENT_W - 4.0 <= mm_x <= T.CONTENT_W + 14.0
                and 0 <= r_idx < len(rows) and rows[r_idx].can_delete()):
            self._minus_row = rows[r_idx]
            self._btn_minus.setFixedSize(size, size)
            self._btn_minus.move(int(v.x(T.CONTENT_W) + 3),
                                 int(v.y(top + (r_idx + 0.5) * T.ROW_H)
                                     - size / 2))
            self._btn_minus.raise_()
            self._btn_minus.show()
        else:
            self._btn_minus.hide()

    def _remove_row(self, row: "_Row"):
        if self._locked or not row.can_delete() or row not in self._rows:
            return
        if not row.is_empty() and not confirm(
                self, "حذف السطر", "هذا السطر يحتوي بيانات — حذفه؟"):
            return
        row.dispose()
        self._rows.remove(row)
        self._reindex_segments()              # §25: يبقى الترتيب متّصلاً
        self._refresh_libelle_suggestions()
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
        #  Phase E.2: أيّ تحريك للفاصل (إخفاء/إظهار الشريط الجانبيّ أو
        #  سحبه) يغيّر عرض مساحة العمل ⇒ الخطاف المركزيّ لإعادة التموضع.
        split.splitterMoved.connect(
            lambda *_a: self._on_workspace_geometry_changed())
        self._split = split
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

        # §5: لا «＋ Ajouter» في الشريط الجانبيّ — الإضافة صارت من الجدول
        # نفسه عبر أزرار ＋/－ على الهامش عند المرور بالفأرة (R2).
        hint = QLabel("مرِّر الفأرة على يسار الجدول: ＋ يُدرج سطراً، － يحذفه. "
                      "موضع السطر يحدّد منطقته الحسابيّة.")
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

        # مؤشّر «🔒 نهائيّ» + فتح القفل للتحرير (§13/§14) — بديلٌ واضح عن
        # نقرة مزدوجة على شارة في مستكشف غير موجود بعد.
        self._state_lbl = QLabel("")
        self._state_lbl.setWordWrap(True)
        self._state_lbl.setStyleSheet(
            f"color:{theme.COMPUTED}; font-weight:700;")
        self._state_lbl.setVisible(False)
        lay.addWidget(self._state_lbl)
        self._unlock_btn = QPushButton("🔓 فتح القفل للتحرير")
        self._unlock_btn.clicked.connect(self._on_unlock)
        self._unlock_btn.setVisible(False)
        lay.addWidget(self._unlock_btn)

        bf = QFrame()
        bf.setFrameShape(QFrame.StyledPanel)
        bl = QVBoxLayout(bf)
        self._save_btn = QPushButton("💾 حفظ")
        self._save_btn.clicked.connect(self._on_save)
        bl.addWidget(self._save_btn)
        self._finalize_btn = QPushButton("✅ إصدار نهائيّ (Word + PDF)")
        self._finalize_btn.clicked.connect(self._on_finalize)
        bl.addWidget(self._finalize_btn)
        self._next_btn = QPushButton("📅 الشهر التالي")
        self._next_btn.setToolTip(
            "ينشئ كشفاً جديداً مستقلاً للشهر التالي — الأصل لا يتغيّر.")
        self._next_btn.clicked.connect(self.create_next_period_work)
        bl.addWidget(self._next_btn)
        for txt, fn in (("👁 معاينة / طباعة", self._on_preview),
                        ("💾 حفظ باسم…", self._on_save_as),
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
                      "segment": r.segment, "order": r.order,
                      "zone": r.zone,                      # مشتقٌّ — للقراءة فقط
                      "cells": {c: r.val(c) for c in r.widgets},
                      "iep_manual": r._iep_manual,
                      "code_manual": r._code_manual,
                      "review": r._review}
                     for r in self._rows],
            "incomplete": bool(v is not None and v.is_incomplete),
        }

    def apply_draft(self, data):
        data = data or {}
        # Phase B: نُسجّل العلم فقط. الاستعادة التلقائية للمسوّدة أثناء
        # الكتابة لا تُظهر تحذيرات الإلزاميّ (§14)؛ تفعيلها عند فتح عملٍ
        # محفوظ رسمياً كـ«غير مكتمل» = Phase C عبر ``show_required_warnings``.
        self._restored_incomplete = bool(data.get("incomplete"))
        self._cfg = None          # الفترة قد تختلف ⇒ أعِد تحميل params
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
            legacy_order = {}
            for spec in data.get("rows", []):
                kind = spec.get("kind")
                if kind not in _ROW_SPECS:
                    continue
                cells = spec.get("cells") or {}
                #  §5/§39: عملٌ قديم بلا ``segment`` ⇒ تُشتقّ من ``zone``
                #  القديم (A→A · B→B3 · C→C) وترتيب الملفّ، مرّةً في الذاكرة
                #  ثمّ تُحفَظ صريحةً عند الحفظ التالي.
                seg = spec.get("segment")
                order = spec.get("order")
                if seg not in _SEGMENTS:
                    seg = (_legacy_segment(kind, cells)
                           if not spec.get("zone")
                           else {_ZONE_A: "A", _ZONE_B: "B3",
                                 _ZONE_C: "C"}.get(spec["zone"],
                                                  _legacy_segment(kind, cells)))
                    order = legacy_order.get(seg, 0)
                    legacy_order[seg] = order + 1
                r = _Row(self, kind, self._next_rid, segment=seg, order=order)
                self._next_rid += 1
                self._rows.append(r)
                for c, val in cells.items():
                    r.set_val(c, val)
                r._iep_manual = bool(spec.get("iep_manual"))
                r._code_manual = bool(spec.get("code_manual"))
                r._review = spec.get("review") or ""
            for kind in self._FIXED_KINDS:
                if not any(r.kind == kind for r in self._rows):
                    self._rows.append(_Row(self, kind, self._next_rid))
                    self._next_rid += 1
            self._prev_text.clear()
        finally:
            self._suspend = set()
        self._reindex_segments()
        self._dedupe_unique()                 # §8: لا نوعٌ فريد مكرَّر
        self._refresh_libelle_suggestions()
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

    #  Phase E.1 §3/§5: هندسة الوثيقة كلّها من :mod:`layout_spec` بالمليمتر
    #  — لا معايرة بكسل، لا اعتماد على ``scale``. الزوم = ``_DocView`` فقط.
    def _row1_layout(self):
        """‏``(a_x, lieu_x)`` بالمليمتر لسطر تاريخ الميلاد (من المواصفة)."""
        return L.row1_layout()

    def _ident_row_y(self, r):
        return L.ident_row_y(r)

    def _ident_h(self):
        return L.IDENT_H_MM

    # --- هندسة جسم الجدول (R1: أسفل ثابت بصرياً — §4/§31) ---
    def _n_body(self):
        """عدد الصفوف الفعليّة (widgets/رسم القيَم)."""
        return len(self._visible_body_rows())

    def _n_body_drawn(self):
        """عدد أسطر الشبكة المرسومة: الصفوف الفعليّة + حشوٌ فارغ تحت IRG
        حتى ``MIN_BODY_SLOTS`` (§4). الفرق مساحة شبكة، لا widgets."""
        c = len(self._zone_rows(_ZONE_C))
        return self._n_body() + max(0, self.MIN_BODY_SLOTS - c)

    def _body_bottom_mm(self):
        return T.BODY_TOP + self._n_body_drawn() * T.ROW_H

    def _total_y_mm(self):
        #  متّصل بآخر سطر شبكة — لا فجوة عائمة (§31).
        return self._body_bottom_mm()

    def _net_y_mm(self):
        return self._total_y_mm() + T.ROW_H

    def _sheet_content_mm(self):
        """أدنى امتداد رأسيّ يلزم لاحتواء الوثيقة (لضبط طول اللوحة)."""
        return self._net_y_mm() + T.ROW_H + 12.0

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
        self._on_workspace_geometry_changed()

    # ---- الخطاف المركزيّ لأيّ تغيّر في هندسة مساحة العمل (Phase E.2) ----
    def _on_workspace_geometry_changed(self):
        """يُستدعى عند **أيّ** تغيّر لعرض/ارتفاع مساحة العمل: تكبير النافذة،
        تحريك الفاصل، إخفاء/إظهار الشريط الجانبيّ، تغيّر حجم منفذ عرض
        منطقة التمرير. يعيد ``_relayout`` كاملةً فتُشتقّ مواضع **كلّ** عناصر
        الوثيقة من مستطيل الصفحة الحاليّ — لا موضع بكسل قديم يبقى."""
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
        #  §28: في القفل، تُبتلَع كلّ محاولة تحرير عبر ComboBox (يبقى
        #  مفعَّلاً فلا يتحوّل رمادياً، لكنه لا يستجيب).
        if self._locked and isinstance(obj, QComboBox) and t in (
                QEvent.MouseButtonPress, QEvent.MouseButtonDblClick,
                QEvent.MouseButtonRelease, QEvent.KeyPress, QEvent.Wheel):
            return True
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
        #  ＋/－ على هامش الجدول — تتبُّع حركة الفأرة فوق اللوحة (R2)
        if t == QEvent.MouseMove and obj is getattr(self, "_canvas", None):
            self._gutter_mouse_move(ev.position().toPoint())
        elif t == QEvent.Leave and obj is getattr(self, "_canvas", None):
            self._hide_gutter_controls()
        #  Phase E.2: تغيّر حجم منفذ عرض منطقة التمرير (إخفاء الشريط
        #  الجانبيّ / سحب الفاصل / تكبير النافذة) لا يصل إلى ``resizeEvent``
        #  الشاشة — نلتقطه هنا ونعيد تموضع كلّ عناصر الوثيقة.
        if (t == QEvent.Resize and hasattr(self, "_scroll")
                and obj is self._scroll.viewport()):
            self._on_workspace_geometry_changed()
        return super().eventFilter(obj, ev)

    def _relayout(self):
        if not hasattr(self, "_canvas"):
            return
        #  حارس إعادة الدخول: ``setFixedSize`` على اللوحة قد يُظهر/يُخفي
        #  شريط تمرير ⇒ حدث Resize لمنفذ العرض ⇒ استدعاء ثانٍ. تمريرةٌ
        #  واحدة تكفي (كلّ شيء يُشتقّ من ``_view()`` الحاليّ).
        if getattr(self, "_in_relayout", False):
            return
        self._in_relayout = True
        try:
            self._relayout_impl()
        finally:
            self._in_relayout = False

    def _relayout_impl(self):
        self._hide_gutter_controls()          # تعاد عند حركة الفأرة التالية
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
                x_mm = self._row1_layout()[1]

            # ---- عمودياً (كلّه مليمترٌ ثابت من المواصفة) ----
            if slot.key in self._ident_row:
                ref_mm = self._ident_row_y(self._ident_row[slot.key])
                top_px = v.y(ref_mm) - fm.ascent() - chrome
                h_px = int(fm.height() + 2 * chrome)
            elif slot.baseline_mm is not None:
                top_px = v.y(slot.baseline_mm) - fm.ascent() - chrome
                h_px = int(fm.height() + 2 * chrome)
            else:                                          # خانة جدول
                top_px = v.y(slot.y_mm)
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
        #  مستطيلٌ **مُوسَّطٌ رياضياً** موحَّد لكلّ الخلايا (§22): من
        #  ``layout_spec.editor_rect_mm`` — لا رقم +0.7 سحريّ.
        f_row = v.tfont("table_body")             # نظام الخطوط المشترك (§9)
        for i, row in enumerate(self._visible_body_rows()):
            for cell, w in row.widgets.items():
                #  الموضع أوّلاً (يبقى ضمن الجدول حتى لو أُخفيت لاحقاً)،
                #  ثمّ الإظهار/الإخفاء.
                x_mm, y_mm, w_mm, h_mm = L.editor_rect_mm(row.column(cell), i)
                w.setFont(f_row)
                w.setFixedWidth(max(int(v.px(w_mm)), 12))
                w.setFixedHeight(max(int(v.px(h_mm)), 12))
                w.move(int(v.x(x_mm)), int(v.y(y_mm)))
                # خلية «classe» في «Autre» تظهر فقط حين sens = Gain
                if row.kind == "autre" and cell == "classe":
                    w.setVisible(row.val("sens") == "Gain")
                #  §14: RETENUE في سطرٍ حرٍّ خارج Zone C غير متاحة — تُخفى
                #  (لا تظهر رماديّةً؛ الخليّة تبقى كورقةٍ نظيفة).
                elif row.kind == "free" and cell == "retenue":
                    w.setVisible(row.zone == _ZONE_C)
                elif w.isHidden():
                    w.show()               # عادت مرئيّةً بعد تحويل/تغيّر منطقة
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
        if isinstance(w, DateField):
            w.refresh_style()
            if warn and not w.error_text():
                # حدّ تحذير خفيف فوق نمط DateField — آخر قاعدة QLineEdit
                # تفوز في Qt، ويُعيده refresh_style في الاستدعاء التالي.
                w._edit.setStyleSheet(
                    w._edit.styleSheet()
                    + f"\nQLineEdit{{border:1px solid {theme.WARNING};}}")
            return
        if isinstance(w, QComboBox):
            #  §29/§E.3: لا رمادي أبداً — خليّة صفراء نظيفة منذ الفتح، بلا
            #  حافة نافرة؛ التركيز يضيف حدّاً أزرق خفيفاً فقط.
            bd = theme.HOVER if w.hasFocus() else theme.FIELD_EMPTY
            if warn:
                bd = theme.WARNING
            w.setStyleSheet(
                f"QComboBox {{ background:{theme.FIELD_EMPTY}; color:{theme.TEXT};"
                f" border:1px solid {bd}; border-radius:0; padding:0 1px; }}"
                f"QComboBox::drop-down {{ border:0; width:12px; }}"
                f"QComboBox QAbstractItemView {{ background:#ffffff; "
                f"color:{theme.TEXT}; selection-background-color:{theme.PRIMARY};"
                f" selection-color:#ffffff; }}")
            return
        filled = bool(self._field_value(key))
        is_table_cell = bool(_ROW_CELL_KEY.match(key))
        if key in self._band_keys:
            focused = w.hasFocus()
            if focused:
                bg, fg, bd = theme.SURFACE, "#000000", theme.HOVER
            elif filled:
                bg, fg, bd = theme.BAND_BLACK, "#ffffff", theme.BAND_BLACK
            else:
                bg, fg, bd = theme.FIELD_EMPTY, "#000000", "#ffffff"
        elif is_table_cell:
            #  §E.3: خلايا الجدول صفراء **دائماً** (مملوءة أو لا) لتقرأ
            #  كحقول إدخال؛ التركيز يضيف حدّاً أزرق فقط، لا يغيّر الخلفية.
            bg = theme.FIELD_EMPTY
            fg = theme.TEXT
            bd = theme.HOVER if w.hasFocus() else theme.FIELD_EMPTY
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
        if k == "free":
            #  §37: سطرٌ حرّ فارغٌ تماماً ⇒ يُتجاهَل. بدأه المستخدم (اسم/رمز
            #  أو قيمة) وبلا مبلغٍ صالح ⇒ ناقص. GAIN و RETENUE معاً، أو
            #  RETENUE سالبة ⇒ غير صالح (يُبرَز في validate_screen).
            g, ret = r.val("gain").strip(), r.val("retenue").strip()
            started_free = bool(r.val("libelle") or r.val("code") or g or ret)
            has_amount = _num(g) > 0 or _num(ret) > 0
            ok = has_amount and not (g and ret) and not ret.startswith("-")
            return started_free, ok, "سطر حرّ"
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

    WORK_VERSION = 3          # E.3: segment + order لكلّ صفّ

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

    def load_work(self, row: dict, *, show_warnings=None):
        """يفتح عملاً محفوظاً (صفّ ``hr_documents``) للتحرير: يعيد بناء
        الشاشة من ``full_data_json``، يثبّت المعرّف، ويستعيد حالة ⚠️/🔒.

        ``show_warnings`` (افتراضياً ``None`` = «حسب الحالة»): عمل ⚠️ مُعاد
        فتحه من السجلّ ⇒ تُفعَّل تحذيرات الإلزاميّ (§5). Smart Next يمرّر
        ``False`` — نسخة وُلِّدت للتوّ لا تُفتَح بشاشة مليئة بالتحذيرات (Phase D §11)."""
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
        if show_warnings is None:
            show_warnings = (self._work_state == "incomplete")
        #  اضبط القفل صراحةً في الاتّجاهين — فتح عمل ⚠️ بعد عمل 🔒 يفتح القفل.
        self._set_locked(self._work_state == "final")
        if self._work_state != "final" and show_warnings:
            self.show_required_warnings()
        # نظّف بعد كلّ إعادة البناء: عملٌ مُحمَّل حديثاً = «غير ملموس»
        # (‏auto-draft لا يطغى عليه) — §26/§14.
        self._dirty = False
        self.clear_draft()
        self._update_incomplete_indicator()
        self._update_state_indicator()
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
        if self._locked:
            from ui2.alerts import warn
            warn(self, self.TITLE,
                 ["العمل مقفول (🔒). افتح القفل للتعديل قبل الحفظ."])
            return
        self._recompute()
        state = "incomplete"                      # SAVE لا يُنتج نهائياً أبداً
        #  §16: عمل كان 🔒 ثمّ فُتح وعُدِّل ⇒ يعود ⚠️، ولا تُلمَس ملفّاته
        #  النهائية على القرص. نُبقي مساريهما في الصفّ كـ«آخر ما صدر» فقط.
        rec = self._work_record(state, docx=self._final_docx or "",
                                pdf=self._final_pdf)
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
        صفّ ديناميكيّ)، وأزرار ＋/－ على الهامش تختفي (§28). لا يمسّ
        Zoom/Ctrl+Wheel/التمرير ولا أزرار المعاينة/الحفظ باسم."""
        self._locked = bool(locked)
        for w in self._widgets.values():
            if isinstance(w, QComboBox):
                #  §28/§29: لا رمادي — يبقى مفعَّلاً، والتفاعل يُبتلَع في
                #  ``eventFilter`` عند القفل.
                w.setEnabled(True)
            elif hasattr(w, "setReadOnly"):
                w.setReadOnly(True if isinstance(w, _InlineChoice) else locked)
            if isinstance(w, (_SmartLibelle, _InlineChoice)):
                w._arrow.setEnabled(not locked)     # القفل: لا قائمة، لا سهم
        if hasattr(self, "_add_btn"):
            self._add_btn.setEnabled(not locked)
        if locked:
            self._hide_gutter_controls()
        self._update_state_indicator()
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
            if r.kind == "free" and key in (r.cell_key("gain"),
                                            r.cell_key("retenue")):
                self._enforce_free_gain_retenue(r, key)
            if key in {r.cell_key(c) for c in r.choice_cells()}:
                relayout = True                  # قد يتغيّر عمود/ظهور خلية
        self._style_field(key)
        self.mark_dirty()
        self._recompute()
        if relayout:
            self._relayout()

    def _enforce_free_gain_retenue(self, r, edited_key):
        """§10: السطر الحرّ يقبل قيمةً في GAIN **أو** RETENUE لا كليهما،
        وRETENUE تُكتب موجبةً. الحقل المُحرَّر يفوز؛ والسالب يُنظَّف."""
        gk, rk = r.cell_key("gain"), r.cell_key("retenue")
        gw, rw = self._widgets[gk], self._widgets[rk]
        #  RETENUE سالبة → إزالة الإشارة (لا سالب مزدوج)
        if edited_key == rk and "-" in rw.text():
            self._suspend.add(rk)
            rw.setText(rw.text().replace("-", ""))
            self._suspend.discard(rk)
        #  الحقل المُحرَّر فيه قيمة ⇒ فرّغ الآخر
        if edited_key == gk and gw.text().strip() and rw.text().strip():
            self._suspend.add(rk)
            rw.clear()
            self._suspend.discard(rk)
            self._style_field(rk)
        elif edited_key == rk and rw.text().strip() and gw.text().strip():
            self._suspend.add(gk)
            gw.clear()
            self._suspend.discard(gk)
            self._style_field(gk)

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
            #  طبقة العرض المشتركة (§11): صفوفٌ ومجاميع معروضة — نفس ما
            #  يستهلكه PDF/DOCX.
            self._presented = PZ.build(
                self._bulletin_view,
                jours=_num(self._salaire_row().val("nbase"))
                if self._salaire_row() else None,
                pad_zone_c=False)
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
            self._presented = None
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

    def _finalize_paths(self):
        """مسارا docx/pdf النهائيّين لهذا العمل. إعادة إصدار العمل نفسه ⇒
        نفس المسارين (استبدال في المكان). أوّل إصدار ⇒ من الاسم/الفترة، مع
        زيادة رقميّة إن اصطدم باسم ملفٍّ **لا يخصّ هذا العمل** (§29)."""
        if self._final_docx and self._final_pdf:
            return self._final_docx, self._final_pdf
        base = paths.get_screen_dir(self.OUTPUT_DIRNAME)
        stem0 = (f"Bulletin_{_safe(self._employee_fullname())}"
                 f"_{_safe(self._w('mois'))}_{_safe(self._w('annee'))}")
        stem, n = stem0, 2
        while (os.path.exists(os.path.join(base, stem + ".pdf"))
               or os.path.exists(os.path.join(base, stem + ".docx"))):
            stem = f"{stem0}_{n:02d}"
            n += 1
        return (os.path.join(base, stem + ".docx"),
                os.path.join(base, stem + ".pdf"))

    def _on_finalize(self):
        """إصدار نهائيّ **شبه معامليّ** (§8): تحقّق → بناء docx+pdf في ملفّات
        مؤقّتة → استبدال ذرّيّ → حفظ الحالة → قفل. فشل أيّ خطوة ⇒ لا قفل،
        لا ادّعاء نجاح، لا فقدان Work Data، وتُنظَّف الملفّات الجزئية."""
        from ui2.alerts import warn
        self._recompute()
        if not self.show_required_warnings():
            warn(self, self.TITLE,
                 ["توجد معلومات ناقصة قبل إصدار الكشف النهائيّ."])
            return
        docx_path, pdf_path = self._finalize_paths()
        tmp_docx, tmp_pdf = docx_path + ".part", pdf_path + ".part"
        tpl = T.get_renderer(self._template_key)
        try:
            os.makedirs(os.path.dirname(docx_path), exist_ok=True)
            tpl.build_docx(tmp_docx, self._calc_input, self._calc_result,
                           self._employer_data(), self._employee_data(),
                           view=self._bulletin_view)
            tpl.build_pdf(tmp_pdf, self._calc_input, self._calc_result,
                          self._employer_data(), self._employee_data(),
                          view=self._bulletin_view)
        except TemplateNotReady as exc:
            _silent_unlink(tmp_docx, tmp_pdf)
            warn(self, self.TITLE, [str(exc)])
            return
        except Exception as exc:                              # noqa: BLE001
            _silent_unlink(tmp_docx, tmp_pdf)
            logger.warning("بناء ملفّات الإصدار فشل", exc_info=True)
            warn(self, self.TITLE,
                 ["لم يكتمل الإصدار النهائيّ — لم يُقفَل العمل ولم تُفقَد "
                  f"البيانات.\n{exc}"])
            return
        try:
            os.replace(tmp_docx, docx_path)
            os.replace(tmp_pdf, pdf_path)
        except OSError as exc:
            _silent_unlink(tmp_docx, tmp_pdf)
            logger.warning("استبدال ملفّات الإصدار فشل", exc_info=True)
            warn(self, self.TITLE, [f"تعذّرت كتابة الملفّات النهائية: {exc}"])
            return
        prev = self._work_state
        self._final_docx, self._final_pdf = docx_path, pdf_path
        self._has_final_artifacts = True
        self._work_state = "final"
        rec = self._work_record("final", docx=docx_path, pdf=pdf_path)
        try:
            if self._work_id is None:
                self._work_id = database.save_hr_work(rec, self.work_data())
            else:
                database.update_hr_work(self._work_id, rec, self.work_data())
        except Exception as exc:                              # noqa: BLE001
            self._work_state = prev                           # لا تدّعِ النجاح
            self._has_final_artifacts = bool(prev == "final")
            logger.warning("حفظ حالة الإصدار فشل", exc_info=True)
            warn(self, self.TITLE,
                 [f"وُلِّدت الملفّات لكن تعذّر حفظ حالة العمل — لم يُقفَل.\n{exc}"])
            return
        self._dirty = False
        self.clear_draft()
        self._set_locked(True)
        self._update_incomplete_indicator()
        self._update_state_indicator()
        self.status.setText("🔒 صدر الكشف النهائيّ — Word + PDF.")
        if confirm(self, self.TITLE,
                   f"🔒 صدر الكشف النهائيّ:\n{pdf_path}\n\nفتحه الآن؟"):
            try:
                os.startfile(pdf_path)                        # noqa: SIM115
            except OSError:
                pass

    def _on_unlock(self):
        if not self._locked:
            return
        if not confirm(self, self.TITLE,
                       "فتح القفل للتحرير؟\nالتعديل لن يغيّر الملفّات النهائية "
                       "على القرص حتى تُعيد الإصدار (Finalize) أو تحفظ باسم."):
            return
        self._set_locked(False)
        self._update_state_indicator()
        self.status.setText("🔓 فُتح القفل — التعديل لا يمسّ النسخة النهائية "
                            "حتى إعادة الإصدار.")

    def _on_preview(self):
        from ui2.alerts import warn
        p = self._final_pdf or self._final_docx
        if p and os.path.exists(p):
            try:
                os.startfile(p)                              # noqa: SIM115
            except OSError as exc:
                warn(self, self.TITLE, [f"تعذّر فتح الملف: {exc}"])
        else:
            warn(self, self.TITLE,
                 ["لا توجد نسخة نهائية بعد — استعمل «إصدار نهائيّ»."])

    def _on_save_as(self, label=None):
        """Save As = **استنساخ Work Item** (§17): ينسخ الحالة الحالية
        القابلة للتحرير إلى **معرّف جديد** بلا مستندات نهائية، ويتعامل
        معها كعمل مستقلّ (الشاشة تصير تحرّره). الأصل — صفّه، مساراته،
        ملفّاته — **لا يُلمَس**. ممكن حتى من عمل 🔒 بلا فتح القفل (§18)."""
        from ui2.alerts import warn
        if label is None:
            from PySide6.QtWidgets import QInputDialog
            label, ok = QInputDialog.getText(
                self, self.TITLE, "اسم النسخة الجديدة (اختياريّ):",
                text=self._employee_fullname())
            if not ok:
                return
        self._recompute()
        #  Work Data للنسخة: نفس المدخلات، لكن بلا أثر نهائيّ.
        wd = self.work_data()
        wd["has_final_artifacts"] = False
        wd["final_docx"] = wd["final_pdf"] = None
        rec = self._work_record("incomplete")
        if label:
            rec["doc_label"] = str(label)[:120]
        try:
            new_id = database.save_hr_work(rec, wd)
        except Exception as exc:                              # noqa: BLE001
            logger.warning("حفظ باسم فشل", exc_info=True)
            warn(self, self.TITLE, [f"تعذّر إنشاء النسخة: {exc}"])
            return
        #  الشاشة تصبح تحرّر النسخة الجديدة المستقلّة.
        self._work_id = new_id
        self._work_state = "incomplete"
        self._has_final_artifacts = False
        self._final_docx = self._final_pdf = None
        self._dirty = False
        if self._locked:
            self._set_locked(False)
        self.clear_draft()
        self._update_incomplete_indicator()
        self._update_state_indicator()
        self.status.setText("💾 أُنشئت نسخة مستقلّة (⚠️) — الأصل لم يتغيّر.")

    # ===================== Smart Next (Phase D) =====================
    def _next_period(self):
        """‏``(mois_maj, annee)`` للشهر التالي مباشرةً — دلاليّاً لا بربط
        نصوص. ``None`` إن كانت الفترة الحالية غير صالحة."""
        try:
            m = _MOIS_UP.index(self._w("mois").upper()) + 1
            y = int(self._w("annee"))
        except (ValueError, KeyError):
            return None
        if not (1 <= m <= 12 and 1900 <= y <= 2200):
            return None
        m2, y2 = (1, y + 1) if m == 12 else (m + 1, y)
        return _MOIS_UP[m2 - 1], f"{y2:04d}"

    def _find_period_work(self, nom, prenom, mois, annee):
        """صفّ ``hr_documents`` لعملٍ محفوظ بنفس هويّة الأجير (اسم+لقب) ونفس
        الفترة والخدمة — أبسط فحص آمن (لا سجلّ أجراء)؛ حدوده موثَّقة."""
        import json as _json
        for r in database.list_hr_documents(screen_key="hr_bulletin_paie",
                                            limit=500):
            try:
                wd = _json.loads(r.get("full_data_json") or "{}")
            except ValueError:
                continue
            emp = wd.get("employee") or {}
            per = wd.get("period") or {}
            if ((emp.get("nom") or "").strip().casefold()
                    == (nom or "").strip().casefold()
                    and (emp.get("prenom") or "").strip().casefold()
                    == (prenom or "").strip().casefold()
                    and (per.get("mois") or "").strip().upper() == mois
                    and str(per.get("annee") or "").strip() == annee):
                return r
        return None

    def create_next_period_work(self):
        """ينشئ **عملاً جديداً مستقلاً** لكشف الشهر التالي من الحالة الحالية
        الظاهرة: ينقل الهويّة والبنية المستقرّة (أجر/سلة/نقل/Prime/وجود IEP)،
        يحذف العرضيّ (Absence/Retard/HS/Avance/Autre)، يبدّل الفترة، ويعيد
        الحساب لـ params الفترة الجديدة. الأصل لا يُلمَس (صفّه، حالته،
        قفله، ملفّاته). يعمل من 🔒 بلا فتح القفل (§14)."""
        import copy
        import json as _json
        from ui2.alerts import warn

        nxt = self._next_period()
        if nxt is None:
            warn(self, self.TITLE,
                 ["الفترة الحالية غير صالحة — حدّد شهراً وسنةً صحيحين قبل "
                  "إنشاء كشف الشهر التالي."])
            return
        mois2, annee2 = nxt

        # §26: لا نفقد تعديلاً غير محفوظ في الأصل (وليس مقفولاً) — نحفظه ⚠️.
        if self._dirty and not self._locked:
            self._on_save()

        # §13: عمل محفوظ لنفس الأجير + الفترة الجديدة؟
        nom, prenom = self._w("id_nom"), self._w("id_prenom")
        existing = self._find_period_work(nom, prenom, mois2, annee2)
        if existing is not None:
            if confirm(self, self.TITLE,
                       f"يوجد كشف محفوظ لـ {mois2} {annee2}.\nفتحه؟ "
                       "(«لا» = إنشاء نسخة مستقلّة جديدة.)"):
                self.load_work(existing)
                return

        # ---- بناء Work Data للفترة الجديدة ----
        wd = copy.deepcopy(self.work_data())
        wd["header"] = dict(wd.get("header") or {})
        wd["header"]["mois"] = mois2
        wd["header"]["annee"] = annee2
        wd["period"] = {"mois": mois2, "annee": annee2}   # metadata متّسقة
        new_rows = []
        for row in wd.get("rows", []):
            k = row.get("kind")
            cells = row.get("cells") or {}
            if k == "free":
                #  §27: يُنقَل السطر الحرّ فقط إن كان **مكسباً مستقرّاً**
                #  (Prime): قيمة في GAIN وبلا RETENUE. الحرّ باقتطاع أو
                #  الفارغ ⇒ عرضيّ، يُحذَف.
                if not (cells.get("gain") or "").strip() \
                        or (cells.get("retenue") or "").strip():
                    continue
            elif k not in _SMART_NEXT_CARRY:
                continue                                  # §5/§6: يُحذَف
            row = dict(row)
            if k == "iep":
                #  §7: الوجود ينتقل؛ النسبة تعود لاقتراح المحرّك للفترة
                #  الجديدة (لا نسخ مبلغ/نسبة قديمة، لا قفل override دائم).
                row["cells"] = {}
                row["iep_manual"] = False
            new_rows.append(row)
        wd["rows"] = new_rows
        wd["incomplete"] = True
        wd["has_final_artifacts"] = False
        wd["final_docx"] = wd["final_pdf"] = None
        wd["source_work_id"] = self._work_id              # §12 — داخل JSON فقط
        wd["source_period"] = {"mois": self._w("mois"), "annee": self._w("annee")}

        rec = {
            "screen_key": "hr_bulletin_paie", "doc_label": self.DOC_LABEL,
            "employer_name": self._w("emp_raison_sociale"),
            "employee_name": self._employee_fullname(),
            "doc_date": f"{mois2} {annee2}".strip(),
            "client_id": None, "file_path": "", "pdf_path": None,
            "state": "incomplete",
        }
        try:
            new_id = database.save_hr_work(rec, wd)
        except Exception as exc:                              # noqa: BLE001
            logger.warning("إنشاء كشف الشهر التالي فشل", exc_info=True)
            warn(self, self.TITLE, [f"تعذّر إنشاء كشف الشهر التالي: {exc}"])
            return

        # الشاشة تنتقل لتحرّر الكشف الجديد — بلا تحذيرات إلزاميّ تلقائية (§11)،
        # وبلا قفل مهما كانت حالة الأصل (§10/§14).
        self.load_work(database.get_hr_document(new_id), show_warnings=False)
        self._recompute()                                    # params الفترة الجديدة
        self.status.setText(f"📅 أُنشئ كشف {mois2} {annee2} — راجِعه ثمّ "
                            "احفظ/أصدِر. الأصل لم يتغيّر.")

    def _update_state_indicator(self):
        lbl = getattr(self, "_state_lbl", None)
        if lbl is None or not hasattr(self, "_unlock_btn"):
            return
        if self._work_state == "final":
            lbl.setText("🔒 كشف نهائيّ"
                        + ("" if self._locked else " — مفتوح للتحرير"))
            lbl.setVisible(True)
        else:
            lbl.setVisible(False)
        self._unlock_btn.setVisible(self._locked)

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
        self._work_id = None                   # مسح ⇒ عمل جديد بلا هويّة
        self._work_state = None
        self._has_final_artifacts = False
        self._final_docx = self._final_pdf = None
        self._set_locked(False)
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
        self._update_state_indicator()

    def has_unsaved_changes(self):
        #  Phase C §26: تغييرات فعلية منذ آخر حفظ/تحميل — لا «فيه محتوى».
        #  عملٌ مُحمَّل وغير ملموس ⇒ False؛ أوّل تعديل ⇒ True؛ Save ⇒ False.
        return self._dirty
