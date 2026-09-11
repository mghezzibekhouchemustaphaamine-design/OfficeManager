"""HomeView — بوابة الخدمات (Prototype).

تعرض بطاقة لكل خدمة مفعّلة من ``ui2.shell.services``. الضغط على بطاقة
يُصدر ``serviceRequested(key)`` — من يستمع (WorkspaceHost) يقرّر ماذا
يفعل. لا منطق فتح خدمة هنا، ولا Nouveau/Historique/Stats داخل البطاقة —
هذا مقصود في هذه المرحلة (راجع الكلاودمد.md لبند 6).
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from ui2 import theme
from ui2.shell.services import ServiceDescriptor, default_services

_CARD_QSS = f"""
QFrame#ServiceCard {{
    background: {theme.SURFACE};
    border: 1px solid {theme.BORDER};
    border-radius: 6px;
}}
QFrame#ServiceCard:hover {{
    border-color: {theme.PRIMARY};
}}
"""


class ServiceCard(QFrame):
    """بطاقة خدمة واحدة — Icon + عنوان + وصف قصير، قابلة للضغط بالكامل."""

    clicked = Signal(str)

    def __init__(self, service: ServiceDescriptor, parent=None):
        super().__init__(parent)
        self.service = service
        self.setObjectName("ServiceCard")
        self.setStyleSheet(_CARD_QSS)
        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.NoFrame)
        self.setMinimumSize(180, 110)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(*(theme.SPACE["md"],) * 4)
        lay.setSpacing(theme.SPACE["xs"])

        icon = QLabel(service.icon or "🗂️")
        icon.setStyleSheet(f"font-size: {theme.FONT_SIZES['title']}px;")
        lay.addWidget(icon)

        title = QLabel(service.title)
        title.setStyleSheet(
            f"font-size: {theme.FONT_SIZES['card']}px; font-weight: 600;"
        )
        title.setWordWrap(True)
        lay.addWidget(title)

        desc = QLabel(service.description)
        desc.setStyleSheet(f"color: {theme.TEXT_DIM};")
        desc.setWordWrap(True)
        lay.addWidget(desc)
        lay.addStretch(1)

    def mousePressEvent(self, event):  # noqa: N802 — Qt override
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.service.key)
        super().mousePressEvent(event)


class HomeView(QWidget):
    """بوابة الخدمات — تُبنى بالكامل من السجلّ، بلا بطاقات مكتوبة يدوياً."""

    serviceRequested = Signal(str)

    def __init__(self, services: list[ServiceDescriptor] | None = None, parent=None):
        super().__init__(parent)
        self._services = services if services is not None else default_services()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            theme.SPACE["lg"], theme.SPACE["lg"], theme.SPACE["lg"], theme.SPACE["lg"]
        )

        heading = QLabel("خدمات OfficeManager")
        heading.setStyleSheet(
            f"font-size: {theme.FONT_SIZES['title']}px; font-weight: 600;"
        )
        outer.addWidget(heading)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll, 1)

        grid_host = QWidget()
        scroll.setWidget(grid_host)
        self._grid = QGridLayout(grid_host)
        self._grid.setSpacing(theme.SPACE["lg"])

        self._cards: dict[str, ServiceCard] = {}
        cols = 3
        row = col = 0
        for svc in self._services:
            if not svc.enabled:
                continue
            card = ServiceCard(svc)
            card.clicked.connect(self.serviceRequested)
            self._cards[svc.key] = card
            self._grid.addWidget(card, row, col)
            col += 1
            if col >= cols:
                col = 0
                row += 1
        self._grid.setRowStretch(row + 1, 1)
        self._grid.setColumnStretch(cols, 1)

    def services(self) -> list[ServiceDescriptor]:
        return list(self._services)
