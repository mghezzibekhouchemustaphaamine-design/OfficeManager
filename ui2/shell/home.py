"""HomeView — بوابة الخدمات (Prototype).

تعرض بطاقة لكل خدمة مفعّلة من ``ui2.shell.services``. الضغط على بطاقة
يُصدر ``serviceRequested(key)`` — من يستمع (WorkspaceHost) يقرّر ماذا
يفعل. لا منطق فتح خدمة هنا، ولا Nouveau/Historique/Stats داخل البطاقة —
هذا مقصود في هذه المرحلة (راجع الكلاودمد.md لبند 6).
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from ui2 import theme
from ui2.shell.services import ServiceDescriptor, default_services

#  عرضٌ أقصى لمحتوى Home (بند 2 — P0.2): يمنع تمدّد البطاقات على كامل
#  عرض Workspace في الشاشات الواسعة، ويُبقيها متمركزة أفقياً بدل تكدّسها
#  في ركنٍ واحد مع فراغٍ كبير.
_CONTENT_MAX_WIDTH = 960
#  عتبات تبسيطيّة لعدد الأعمدة حسب عرض المحتوى المتاح — استجابةٌ خفيفة
#  («بقدر بسيط» كما طُلب)، لا Grid ديناميكيّ معقّد.
_COLUMN_BREAKPOINTS = (560, 760)   # < 560 → عمود واحد · < 760 → عمودان · وإلا 3

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
        self._cols = 3

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)

        #  توسيطٌ أفقيّ + عرضٌ أقصى (بند 2): viewport_host يحمل stretch على
        #  الجانبين حول content بعرضٍ محدود، ومحاذاة أعلى (لا توسيطٌ عموديّ
        #  — المحتوى يبقى في أعلى الشاشة).
        viewport_host = QWidget()
        scroll.setWidget(viewport_host)
        center_lay = QHBoxLayout(viewport_host)
        center_lay.setContentsMargins(0, 0, 0, 0)
        center_lay.addStretch(1)

        content = QWidget()
        content.setMaximumWidth(_CONTENT_MAX_WIDTH)
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(
            theme.SPACE["lg"], theme.SPACE["lg"], theme.SPACE["lg"], theme.SPACE["lg"]
        )
        content_lay.setSpacing(theme.SPACE["lg"])

        heading = QLabel("خدمات OfficeManager")
        heading.setStyleSheet(
            f"font-size: {theme.FONT_SIZES['title']}px; font-weight: 600;"
        )
        content_lay.addWidget(heading)

        grid_host = QWidget()
        self._grid = QGridLayout(grid_host)
        self._grid.setSpacing(theme.SPACE["lg"])
        content_lay.addWidget(grid_host)

        center_lay.addWidget(content, 0, Qt.AlignTop)
        center_lay.addStretch(1)

        self._cards: dict[str, ServiceCard] = {}
        for svc in self._services:
            if not svc.enabled:
                continue
            card = ServiceCard(svc)
            card.clicked.connect(self.serviceRequested)
            self._cards[svc.key] = card
        self._place_cards(self._cols)

        self._content = content

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().resizeEvent(event)
        #  استجابةٌ خفيفة لعدد الأعمدة حسب العرض المتاح — بلا إعادة بناء
        #  البطاقات نفسها، فقط إعادة توزيعها.
        w = self.width()
        cols = 1 if w < _COLUMN_BREAKPOINTS[0] \
            else 2 if w < _COLUMN_BREAKPOINTS[1] else 3
        if cols != self._cols:
            self._cols = cols
            self._place_cards(cols)

    def _place_cards(self, cols: int) -> None:
        for card in self._cards.values():
            self._grid.removeWidget(card)
        row = col = 0
        for card in self._cards.values():
            self._grid.addWidget(card, row, col)
            col += 1
            if col >= cols:
                col = 0
                row += 1
        self._grid.setRowStretch(row + 1, 1)
        self._grid.setColumnStretch(cols, 1)

    def services(self) -> list[ServiceDescriptor]:
        return list(self._services)
