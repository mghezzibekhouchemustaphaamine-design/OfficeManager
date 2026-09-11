"""OfficeMainWindow — الهيكل الأم للبرنامج (Prototype).

يركّب TopBar + MainSplitter (Explorer placeholder | WorkspaceHost) +
StatusBar فقط. **لا** business logic خاصّ بأي خدمة هنا — الربط الحقيقي
بـ Paie/CD/Explorer خارج نطاق هذه المرحلة (راجع docs/CHANGELOG.md).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QSplitter, QVBoxLayout, QWidget

from ui2 import theme
from ui2.shell.services import ServiceDescriptor
from ui2.shell.top_bar import TopBar
from ui2.shell.workspace import WorkspaceHost


class ExplorerPlaceholder(QLabel):
    """مكان محجوز بصرياً لِـ Explorer — بلا أي منطق حقيقي في هذه المرحلة."""

    def __init__(self, parent=None):
        super().__init__("Explorer", parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(140)
        self.setStyleSheet(
            f"background: {theme.BG}; color: {theme.TEXT_DIM};"
            f" border-left: 1px solid {theme.BORDER};"
        )


class OfficeMainWindow(QMainWindow):
    """نافذة Shell الأم — TopBar / MainSplitter(Explorer, Workspace) / StatusBar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OfficeManager — Shell (Prototype)")
        self.resize(1180, 720)

        central = QWidget(self)
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.top_bar = TopBar(self)
        self.top_bar.homeRequested.connect(self.go_home)
        outer.addWidget(self.top_bar)

        self.splitter = QSplitter(Qt.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)
        outer.addWidget(self.splitter, 1)

        self.explorer_placeholder = ExplorerPlaceholder(self.splitter)
        self.splitter.addWidget(self.explorer_placeholder)

        self.workspace = WorkspaceHost(self.splitter)
        self.splitter.addWidget(self.workspace)

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([220, 960])

        self.workspace.home_view.serviceRequested.connect(self._open_service_start)

        self.setStatusBar(self.statusBar())
        self.statusBar().showMessage("جاهز")

    # ------------------------------------------------------------- تنقّل
    def go_home(self) -> None:
        self.workspace.show_home()
        self.statusBar().showMessage("الرئيسية")

    def _open_service_start(self, key: str) -> None:
        service = next(
            (s for s in self.workspace.home_view.services() if s.key == key), None
        )
        if service is None:
            return
        self.workspace.show_service_start(service)
        self.statusBar().showMessage(f"خدمة: {service.title}")

    def open_service_start(self, service: ServiceDescriptor) -> None:
        """نقطة دخول برمجية مباشرة (تُستخدم في الاختبارات)."""
        self.workspace.show_service_start(service)
