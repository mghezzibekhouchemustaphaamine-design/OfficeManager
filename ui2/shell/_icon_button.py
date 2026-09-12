"""زرّ أيقونة مسطّح مشترك — TopBar وWorkStatusBar (Prototype، P0.2).

بديلٌ خفيف عن ``QPushButton`` الأبيض الثقيل: بلا حدّ ولا خلفية إلا عند
Hover، مع دعم حالة "نشِط" اختيارية (خلفية Accent خفيفة) — تُستعمَل حالياً
لزرّ Home في TopBar فقط. لا منطق خدمة هنا، مجرّد عنصر عرضٍ مشترك.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolButton

from ui2 import theme

_QSS = f"""
QToolButton {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
    color: {theme.TEXT};
}}
QToolButton:hover {{ background: {theme.SELECTION}; }}
QToolButton:pressed {{ background: {theme.SELECTION}; }}
QToolButton:disabled {{ color: {theme.TEXT_DIM}; }}
QToolButton:checked {{
    background: {theme.SELECTION};
    color: {theme.PRIMARY_DK};
    font-weight: 600;
}}
"""


class IconButton(QToolButton):
    """زرّ مسطّح (نصّ/أيقونة placeholder + تسمية اختيارية) مع ToolTip."""

    def __init__(self, glyph: str, label: str = "", tooltip: str = "",
                 *, checkable: bool = False, parent=None):
        super().__init__(parent)
        text = f"{glyph}  {label}".strip() if label else glyph
        self.setText(text)
        if tooltip:
            self.setToolTip(tooltip)
        self.setCursor(Qt.PointingHandCursor)
        self.setAutoRaise(True)
        self.setCheckable(checkable)
        self.setStyleSheet(_QSS)
        self.setFocusPolicy(Qt.NoFocus)
