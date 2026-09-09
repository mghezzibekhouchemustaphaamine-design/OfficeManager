"""نظام الأنماط الموحّد لـ ui2 — ألوان، خط، مسافات، QSS، وإعداد RTL مركزي.

كل ما يخصّ المظهر واتجاه التخطيط يُضبط من هنا عبر ``apply_theme(app)``.
المكوّنات الأخرى **لا تستدعي** ``setLayoutDirection`` ولا تعرّف ألواناً.
الاستثناء الوحيد المسموح على مستوى المكوّن هو اتجاه *حقل مفرد* لاتيني
(أرقام/تواريخ) — سلوك مكتبة مقصود في ``ui2.form`` و``ui2.table``.

مبدأ القيَم (المرحلة 3-صفر / البند 2): **مطابقة حرفية لبرنامج Tkinter
الحالي**، لا ذوق مستقل. كل قيمة مستخرَجة من الكود القديم أو من palette
نمط ``windowsvista`` الفعلي — لا تخمين. المصدر مذكور بجانب كل token.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

# ------------------------- لوحة الألوان -------------------------
# المصدر: [ui] = قيمة hex صريحة في ui/ القديم · [vista] = دور في
# QPalette الفعلي لنمط windowsvista (app.palette()، ألوان نظام ويندوز).
BG           = "#f0f0f0"   # [ui] ui/cd/tab.py:561 (fallback خلفية TFrame) + [vista] Window
SURFACE      = "#ffffff"   # [ui] widgets.py:29 FILLED_BG_COLOR + [vista] Base
BORDER       = "#e3e3e3"   # [vista] Midlight — فاصل/حدّ خفيف (Mid #a0a0a0 لحدّ أقوى)
TEXT         = "#202124"   # [ui] hr/bulletin_paie.py:39 _INK · hr/base.py:114
TEXT_DIM     = "#888888"   # [ui] الأكثر تكراراً للنص الخافت: #888 (cd/tab.py:773,777 · settings_screen.py:133)
PRIMARY      = "#0078d7"   # [vista] Highlight — إبراز ويندوز (تركيز، زر افتراضي، فواصل)
PRIMARY_DK   = "#00599f"   # [vista] Highlight.darker(135) — حالة الضغط
SELECTION    = "#e8f0fe"   # [ui] file_explorer.py:244 (تظليل صفّ التمرير) — لا دور «تظليل باهت» في QPalette
ROW_ALT      = "#f5f5f5"   # [vista] AlternateBase — تناوب صفوف الجداول
WARNING      = "#b4690e"   # (بلا مصدر: لا دور QPalette، لا hex في ui/ — يستهلكه ui2 فقط؛ يُراجَع في البند 3)
DANGER       = "#b23b3b"   # (بلا مصدر — نفس WARNING)
FIELD_EMPTY  = "#fff3cd"   # [ui] widgets.py:28 EMPTY_BG_COLOR (تنبيه الحقل الفارغ — يعيده cd/tab.py:430 حرفياً)
FIELD_INVALID = "#fbe3e3"  # [ui] widgets.py:162,633 _INVALID_BG (تاريخ مستحيل)
HOVER        = "#4a90d9"   # [ui] cd/constants.py:86 HOVER_ON_COLOR · hr/bulletin_paie.py:37 _HOVER_ON
BAND_BLACK   = "#111111"   # [ui] hr/bulletin_paie.py:38 _BAND_BG (شريط NET À PAYER الأسود)
COMPUTED     = "#1a56b0"   # [ui] hr/paie/template_simple.py:45 COMPUTED_COLOR (قيَم محسوبة تلقائياً)

# خلفية منطقة عرض ورقة المستند — سياقان مختلفان، لكلٍّ قيمته الأصلية:
CANVAS_BG_CD = "#c9c9c9"   # [ui] cd/tab.py:1159,1178,1182
CANVAS_BG_HR = "#9aa0a6"   # [ui] hr/a4_canvas.py:34 · hr/bulletin_paie.py:201

# ورقة A4 في شاشة الكشف (استمارة فوق لوحة) — مستخرَجة من الكود القديم:
PAGE_SHADOW = "#5f6368"    # [ui] hr/bulletin_paie.py:696 (ظلّ الورقة) · hr/a4_canvas.py
PAGE_BORDER = "#3c4043"    # [ui] hr/bulletin_paie.py:697 (حدّ الورقة)
GRID_LINE   = "#c8c8c8"    # [ui] hr/paie/template_simple.py:299 (خطوط أسطر الجدول الأفقية)

# ------------------------- المسافات (px) -------------------------
# القيَم المستعملة فعلياً في ui/ (hr/base.py، cd/tab.py): 4·6·8·10·12·14.
# المفاتيح كما هي (لا يُلمَس أيّ مستدعٍ) — القيَم فقط صُحِّحت.
SPACE = {"xs": 4, "sm": 6, "md": 10, "lg": 14, "xl": 18}

# ------------------------- الخط -------------------------
# [ui] ui/home/app_window.py:141-142 — الخط الأساسي للواجهة: Segoe UI حجم 10.
FONT_FAMILIES = ["Segoe UI", "Tahoma", "Noto Naskh Arabic", "Arial", "DejaVu Sans"]
FONT_POINT_SIZE = 10

# أحجام العناوين [ui] ui/home/app_window.py:143-146 (Title/CardTitle/Subtitle/Status).
FONT_SIZES = {"title": 20, "card": 13, "subtitle": 10, "base": 10, "status": 9}

# خط الحقول اللاتينية فوق صورة المستند [ui] widgets.py:35 (Courier New) +
# تصحيح cd/constants.py:75 BASE_FONT_SIZE = 10 (لا 9 القديمة).
MONO_FAMILY = "Courier New"
MONO_SIZE = 10

_config = {
    "families": list(FONT_FAMILIES),
    "point_size": FONT_POINT_SIZE,
    "direction": Qt.RightToLeft,
}


def configure(*, families=None, point_size=None, direction=None):
    """تجاوز إعدادات المظهر قبل ``apply_theme`` (من مكان واحد فقط)."""
    if families is not None:
        _config["families"] = list(families)
    if point_size is not None:
        _config["point_size"] = int(point_size)
    if direction is not None:
        _config["direction"] = direction


def resolved_font_family() -> str:
    """أول عائلة مطلوبة متوفّرة فعلياً على الجهاز (لأغراض العرض/التشخيص)."""
    available = set(QFontDatabase.families())
    for fam in _config["families"]:
        if fam in available:
            return fam
    return _config["families"][0] + "  (غير متوفّرة — fallback نظام)"


def build_font() -> QFont:
    f = QFont()
    f.setFamilies(_config["families"])          # Qt6: قائمة fallback حقيقية
    f.setPointSize(_config["point_size"])
    f.setStyleHint(QFont.SansSerif)
    return f


def _qss() -> str:
    s = SPACE
    return f"""
    QWidget {{ color: {TEXT}; }}
    QMainWindow, QDialog, QWidget#GalleryPage {{ background: {BG}; }}
    QLabel {{ background: transparent; }}

    QLineEdit, QPlainTextEdit, QDateEdit, QComboBox {{
        background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 4px;
        padding: 4px 6px; selection-background-color: {SELECTION};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QDateEdit:focus, QComboBox:focus {{
        border-color: {PRIMARY};
    }}
    QLineEdit[empty="true"] {{ background: {FIELD_EMPTY}; }}

    QPushButton {{
        background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 4px;
        padding: 5px 14px;
    }}
    QPushButton:hover {{ border-color: {PRIMARY}; }}
    QPushButton:default {{ background: {PRIMARY}; color: white; border-color: {PRIMARY_DK}; }}
    QPushButton:default:hover {{ background: {PRIMARY_DK}; }}
    QPushButton:disabled {{ color: {TEXT_DIM}; }}

    QToolBar {{
        background: {SURFACE}; border-bottom: 1px solid {BORDER};
        spacing: {s['xs']}px; padding: {s['xs']}px;
    }}
    QToolButton {{ padding: 4px 10px; border-radius: 4px; }}
    QToolButton:hover {{ background: {SELECTION}; }}

    QTableView {{
        background: {SURFACE}; alternate-background-color: {ROW_ALT};
        gridline-color: {BORDER}; border: 1px solid {BORDER};
        selection-background-color: {SELECTION}; selection-color: {TEXT};
    }}
    QHeaderView::section {{
        background: {BG}; border: none; border-bottom: 1px solid {BORDER};
        padding: 6px 8px; font-weight: 600;
    }}

    QTabWidget::pane {{ border: 1px solid {BORDER}; background: {SURFACE}; }}
    QTabBar::tab {{ background: {BG}; border: 1px solid {BORDER}; padding: 6px 14px; }}
    QTabBar::tab:selected {{ background: {SURFACE}; }}

    QStatusBar {{ background: {SURFACE}; border-top: 1px solid {BORDER}; }}
    """


def apply_theme(app: QApplication) -> None:
    """يطبّق المظهر واتجاه RTL على التطبيق كله — النقطة المركزية الوحيدة."""
    app.setStyle("Fusion")                        # سلوك QSS/RTL متّسق عبر المنصّات
    app.setLayoutDirection(_config["direction"])  # ← RTL مركزي، هنا فقط
    app.setFont(build_font())
    app.setStyleSheet(_qss())
