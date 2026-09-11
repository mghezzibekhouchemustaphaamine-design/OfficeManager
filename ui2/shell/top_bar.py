"""TopBar — شريط عامّ ثابت خاصّ بـ OfficeManager (وليس بأيّ خدمة).

Prototype: اسم البرنامج + زرّ Home فعليّ + Settings/Lock كـ placeholders
بصريّة معطّلة. **لا** Save/Print/Undo/Zoom هنا — هذه أدوات خدمة تعيش في
``CommandBar`` مستقبلاً.
"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ui2 import theme


class TopBar(QWidget):

    homeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setStyleSheet(
            f"background: {theme.SURFACE}; border-bottom: 1px solid {theme.BORDER};"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(theme.SPACE["lg"], 0, theme.SPACE["lg"], 0)
        lay.setSpacing(theme.SPACE["md"])

        brand = QLabel("OfficeManager")
        brand.setStyleSheet(
            f"font-size: {theme.FONT_SIZES['card']}px; font-weight: 700;"
        )
        lay.addWidget(brand)
        lay.addStretch(1)

        self.btn_home = QPushButton("الرئيسية")
        self.btn_home.clicked.connect(self.homeRequested)
        lay.addWidget(self.btn_home)

        # placeholders بصرية فقط — بلا سلوك في هذه المرحلة
        self.btn_settings = QPushButton("الإعدادات")
        self.btn_settings.setEnabled(False)
        lay.addWidget(self.btn_settings)

        self.btn_lock = QPushButton("قفل")
        self.btn_lock.setEnabled(False)
        lay.addWidget(self.btn_lock)
