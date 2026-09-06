"""نظام الأنماط الموحّد لـ ui2 — ألوان، خط، مسافات، QSS، وإعداد RTL مركزي.

كل ما يخصّ المظهر واتجاه التخطيط يُضبط من هنا عبر ``apply_theme(app)``.
المكوّنات الأخرى **لا تستدعي** ``setLayoutDirection`` ولا تعرّف ألواناً.
الاستثناء الوحيد المسموح على مستوى المكوّن هو اتجاه *حقل مفرد* لاتيني
(أرقام/تواريخ) — سلوك مكتبة مقصود في ``ui2.form`` و``ui2.table``.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

# ------------------------- لوحة الألوان -------------------------
BG          = "#f4f5f7"
SURFACE     = "#ffffff"
BORDER      = "#d6d9de"
TEXT        = "#1f2430"
TEXT_DIM    = "#6b7280"
PRIMARY     = "#2f6fb2"
PRIMARY_DK  = "#255a91"
SELECTION   = "#dbe9f7"
ROW_ALT     = "#fafbfc"
WARNING     = "#b4690e"
DANGER      = "#b23b3b"
FIELD_EMPTY = "#fff8e1"

# ------------------------- المسافات (px) -------------------------
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 18, "xl": 26}

# ------------------------- الخط -------------------------
# قابل للضبط من مكان واحد. على ويندوز "Segoe UI" و"Tahoma" يحملان
# العربية؛ البقية fallback لبيئات أخرى (لينكس/سحابة).
FONT_FAMILIES = ["Segoe UI", "Tahoma", "Noto Naskh Arabic", "Arial", "DejaVu Sans"]
FONT_POINT_SIZE = 10

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
