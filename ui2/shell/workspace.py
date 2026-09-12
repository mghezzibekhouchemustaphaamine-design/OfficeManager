"""WorkspaceHost — قلب Shell: CommandBar + WorkTabBar + ContentStack.

قصداً **لا** ``QTabWidget`` كحاوية موحّدة — التبويبات (أعمال مفتوحة
مستقبلاً) منفصلة معمارياً عن محتوى العرض (Home / Service Start View).
Home وService Start View تُعرَضان في ``ContentStack`` بلا أن تصبحا
تبويباً. راجع بند 4/9 في المهمّة.

``WorkTabBar`` هنا Prototype بلا ربط بأعمال حقيقية بعد — ``_debug_add_tab``
موجودة فقط لإثبات أن الشريط يبقى مستقلاً عن ContentStack، وليست جزءاً من
سلوك المنتج (لا يستدعيها أي شيء تلقائياً).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel, QPushButton, QStackedWidget, QTabBar, QVBoxLayout, QWidget,
)

from ui2 import theme
from ui2.shell.command_bar import CommandBar
from ui2.shell.home import HomeView
from ui2.shell.services import ServiceDescriptor

WORK_TAB_BAR_HEIGHT = 34


class WorkTabBar(QTabBar):
    """شريط تبويبات الأعمال المفتوحة — منفصل تماماً عن ContentStack.

    Prototype: لا تبويبات حقيقية بعد. يبقى ظاهراً وبارتفاع ثابت حتى وهو
    فارغ (بند 5 — ثبات الـ layout)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(WORK_TAB_BAR_HEIGHT)
        self.setExpanding(False)
        self.setDrawBase(False)
        #  ‏P0.1 §4: خلفية الشريط نفسه كانت مطابقةً تماماً لخلفية النافذة
        #  (BG) فيختفي بصرياً حين يكون فارغاً بلا تبويبات — الآن SURFACE
        #  + حدّ سفليّ خفيف يجعلان مكان «منطقة تبويبات الأعمال» مقروءاً
        #  دائماً، فارغاً كان أم لا، بلا أيّ تبويب وهميّ.
        self.setStyleSheet(
            f"QTabBar {{ background: {theme.SURFACE};"
            f" border-bottom: 1px solid {theme.BORDER}; }}"
            f"QTabBar::tab {{ background: {theme.BG}; border: 1px solid {theme.BORDER};"
            f" border-bottom: none; padding: 4px 12px; }}"
            f"QTabBar::tab:selected {{ background: {theme.SURFACE}; }}"
        )

    def _debug_add_tab(self, title: str) -> int:
        """أداة تطوير/إثبات معماري فقط — غير مستخدَمة في مسار المنتج."""
        return self.addTab(title)


class ServiceStartView(QWidget):
    """نقطة انطلاق خدمة — اسم + وصف + Nouveau/Ouvrir existant (placeholders).

    لا تُنشئ Work Tab ولا تنفّذ أي workflow حقيقي في هذه المرحلة."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(
            theme.SPACE["lg"], theme.SPACE["lg"], theme.SPACE["lg"], theme.SPACE["lg"]
        )
        lay.setSpacing(theme.SPACE["md"])

        self._title = QLabel()
        self._title.setStyleSheet(
            f"font-size: {theme.FONT_SIZES['title']}px; font-weight: 600;"
        )
        lay.addWidget(self._title)

        self._desc = QLabel()
        self._desc.setStyleSheet(f"color: {theme.TEXT_DIM};")
        self._desc.setWordWrap(True)
        lay.addWidget(self._desc)

        self.btn_nouveau = QPushButton("جديد")
        self.btn_ouvrir = QPushButton("فتح موجود")
        lay.addWidget(self.btn_nouveau)
        lay.addWidget(self.btn_ouvrir)
        lay.addStretch(1)

    def set_service(self, service: ServiceDescriptor) -> None:
        self._title.setText(service.title)
        self._desc.setText(service.description)


class WorkspaceHost(QWidget):
    """يجمّع CommandBar + WorkTabBar + ContentStack عمودياً.

    ``show_home()`` / ``show_service_start(descriptor)`` يتحكّمان بمحتوى
    ContentStack فقط — CommandBar وWorkTabBar لا يتغيّر مكانهما."""

    def __init__(self, parent=None):
        super().__init__(parent)
        #  ‏P0.1 §1: splitter الأب صار LTR هندسياً (Explorer|Workspace) —
        #  ذلك الاتجاه يورَّث افتراضياً لهذا الودجت وكل أبنائه. محتوى
        #  Workspace نفسه (عناوين/بطاقات/أزرار عربيّة) يبقى RTL كما كان
        #  دائماً — إعادة ضبطٍ صريحة هنا تفصل اتجاه القراءة الداخليّ عن
        #  القرار الهندسيّ الخارجيّ (STRUCTURAL DIRECTION != TEXT DIRECTION).
        self.setLayoutDirection(Qt.RightToLeft)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.command_bar = CommandBar(self)
        lay.addWidget(self.command_bar)

        self.work_tab_bar = WorkTabBar(self)
        lay.addWidget(self.work_tab_bar)

        self.content_stack = QStackedWidget(self)
        lay.addWidget(self.content_stack, 1)

        self.home_view = HomeView(parent=self)
        self.content_stack.addWidget(self.home_view)

        self.service_start_view = ServiceStartView(self)
        self.content_stack.addWidget(self.service_start_view)

        self.show_home()

    def show_home(self) -> None:
        self.content_stack.setCurrentWidget(self.home_view)

    def show_service_start(self, service: ServiceDescriptor) -> None:
        self.service_start_view.set_service(service)
        self.content_stack.setCurrentWidget(self.service_start_view)

    def current_view(self) -> QWidget:
        return self.content_stack.currentWidget()
