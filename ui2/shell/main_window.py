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
        #  اتجاهٌ نصّيّ RTL صريح خاصّ بمحتوى هذه اللوحة — مستقلّ عن
        #  الاتجاه البنيويّ الذي يفرضه splitter الأب (P0.1 §1/§2: هندسة
        #  الموضع Left/Right شيء، واتجاه القراءة داخل اللوحة شيءٌ آخر).
        self.setLayoutDirection(Qt.RightToLeft)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(140)
        #  الحدّ على الحافة اليمنى (لا اليسرى) — Explorer صار يسار
        #  الشاشة هندسياً (P0.1 §1)، فحدّه الفاصل عن Workspace يقع يميناً.
        self.setStyleSheet(
            f"background: {theme.BG}; color: {theme.TEXT_DIM};"
            f" border-right: 1px solid {theme.BORDER};"
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
        #  STRUCTURAL DIRECTION != TEXT DIRECTION (P0.1 §1): هذا الحاوي
        #  وحده مسؤولٌ عن موضع Explorer/Workspace هندسياً — Explorer
        #  يسار الشاشة دائماً، Workspace يمينها دائماً، بغضّ النظر عن
        #  اتجاه القراءة العامّ للتطبيق (RTL العربيّة). لهذا يُثبَّت هنا
        #  LTR صراحةً بدل الاعتماد على apply_theme العامّ — فتغيّر ذلك
        #  الإعداد لاحقاً (أو انعكاسه) لا يقلب مكان Explorer.
        #
        #  هذا الاتجاه البنيويّ ينتشر افتراضياً لأبنائه المباشرين
        #  (Qt يورّث LayoutDirection للفروع بلا إعدادٍ صريح خاصّ بها) —
        #  لذا كلٌّ من ExplorerPlaceholder وWorkspaceHost يُعيد ضبط
        #  اتجاهه **النصّيّ** الخاصّ (RTL) صراحةً في بانيه هو، فلا يتأثّر
        #  محتواهما الداخليّ (عربيّ) بهذا القرار الهندسيّ البحت.
        self.splitter.setLayoutDirection(Qt.LeftToRight)
        self.splitter.setChildrenCollapsible(False)
        outer.addWidget(self.splitter, 1)

        self.explorer_placeholder = ExplorerPlaceholder(self.splitter)
        self.splitter.addWidget(self.explorer_placeholder)

        self.workspace = WorkspaceHost(self.splitter)
        self.splitter.addWidget(self.workspace)

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([220, 960])
        #  مزامنة عرض Brand Zone في TopBar مع عرض Explorer الفعليّ —
        #  بصريّ فقط (بند 1 في P0.2: «يتناسق بصرياً مع عرض Explorer»).
        self.splitter.splitterMoved.connect(self._sync_brand_width)

        self.workspace.home_view.serviceRequested.connect(self._open_service_start)

        self.setStatusBar(self.statusBar())
        self.statusBar().showMessage("جاهز")

        #  Home هي الشاشة الابتدائية — زرّها في TopBar يبدأ نشِطاً.
        self.top_bar.set_home_active(True)

    # ------------------------------------------------------------- تنقّل
    def go_home(self) -> None:
        self.workspace.show_home()
        self.top_bar.set_home_active(True)
        self.statusBar().showMessage("الرئيسية")

    def _open_service_start(self, key: str) -> None:
        service = next(
            (s for s in self.workspace.home_view.services() if s.key == key), None
        )
        if service is None:
            return
        self.workspace.show_service_start(service)
        self.top_bar.set_home_active(False)
        self.statusBar().showMessage(f"خدمة: {service.title}")

    def open_service_start(self, service: ServiceDescriptor) -> None:
        """نقطة دخول برمجية مباشرة (تُستخدم في الاختبارات)."""
        self.workspace.show_service_start(service)
        self.top_bar.set_home_active(False)

    def _sync_brand_width(self, *_args) -> None:
        sizes = self.splitter.sizes()
        if sizes:
            self.top_bar.set_brand_width(sizes[0])
