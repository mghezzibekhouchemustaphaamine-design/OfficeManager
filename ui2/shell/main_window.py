"""OfficeMainWindow — الهيكل الأم للبرنامج (Prototype).

يركّب TopBar + MainSplitter (Explorer placeholder | WorkspaceHost) فقط.
**لا** business logic خاصّ بأي خدمة هنا — الربط الحقيقي بـ Paie/CD/Explorer
خارج نطاق هذه المرحلة (راجع docs/CHANGELOG.md).

P0.3 §4: لا شريط حالة ثانٍ — رسائل الحالة تعيش في
``WorkspaceHost.work_status_bar`` وحدها؛ ``QMainWindow.statusBar()``
الأصليّة تبقى بنيةً متاحة (لم تُحذَف) لكن Shell الجديد لا يستدعيها.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QSplitter, QVBoxLayout, QWidget

from ui2 import theme
from ui2.shell.services import ServiceDescriptor
from ui2.shell.top_bar import TopBar
from ui2.shell.workspace import WorkspaceHost

#  ‏P0.3 §1: حدود عرضٍ مبدئية للـPrototype — ليست قوانين نهائية. تمنع
#  سحب Explorer حتى يبتلع Workspace (أو العكس: سحقه شبه الصفر).
EXPLORER_MIN_WIDTH = 180
EXPLORER_DEFAULT_WIDTH = 220
EXPLORER_MAX_WIDTH = 460
WORKSPACE_MIN_WIDTH = 600


class ExplorerPlaceholder(QLabel):
    """مكان محجوز بصرياً لِـ Explorer — بلا أي منطق حقيقي في هذه المرحلة."""

    def __init__(self, parent=None):
        super().__init__("Explorer", parent)
        #  اتجاهٌ نصّيّ RTL صريح خاصّ بمحتوى هذه اللوحة — مستقلّ عن
        #  الاتجاه البنيويّ الذي يفرضه splitter الأب (P0.1 §1/§2: هندسة
        #  الموضع Left/Right شيء، واتجاه القراءة داخل اللوحة شيءٌ آخر).
        self.setLayoutDirection(Qt.RightToLeft)
        self.setAlignment(Qt.AlignCenter)
        #  ‏P0.3 §1: حدّا عرضٍ أدنى/أقصى — يمنعان Explorer من ابتلاع
        #  Workspace عند السحب، أو الانسحاق عن حدٍّ معقول للقراءة.
        self.setMinimumWidth(EXPLORER_MIN_WIDTH)
        self.setMaximumWidth(EXPLORER_MAX_WIDTH)
        #  الحدّ على الحافة اليمنى (لا اليسرى) — Explorer صار يسار
        #  الشاشة هندسياً (P0.1 §1)، فحدّه الفاصل عن Workspace يقع يميناً.
        self.setStyleSheet(
            f"background: {theme.BG}; color: {theme.TEXT_DIM};"
            f" border-right: 1px solid {theme.BORDER};"
        )


class OfficeMainWindow(QMainWindow):
    """نافذة Shell الأم — TopBar / MainSplitter(Explorer, Workspace)."""

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
        #  ‏P0.3 §1: حدٌّ أدنى محترم لِـWorkspace — لا يُسحَق شبه الصفر
        #  عند سحب الفاصل نحو Explorer. النافذة نفسها ترفض الانكماش دون
        #  مجموع الحدّين الأدنيين (سلوك Qt الطبيعي لتخطيطٍ بحدود دنيا) —
        #  بلا منع resize العاديّ، فقط حدٌّ سفليّ معقول.
        self.workspace.setMinimumWidth(WORKSPACE_MIN_WIDTH)
        self.splitter.addWidget(self.workspace)

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([EXPLORER_DEFAULT_WIDTH, 960])
        #  مزامنة عرض Brand Zone في TopBar مع عرض Explorer الفعليّ —
        #  بصريّ فقط (P0.2 §2)، بحدٍّ أقصى مضبوطٍ داخل TopBar نفسه
        #  (P0.3 §2: لا تتمدّد Brand Zone بلا حدود مع اتساع Explorer).
        self.splitter.splitterMoved.connect(self._sync_brand_width)

        self.workspace.home_view.serviceRequested.connect(self._open_service_start)
        self.workspace.workspace_manager.activated.connect(self._on_work_activated)
        #  ‏P2 §10: رسالة WorkStatusBar عامّة عند تنفيذ أيّ أمر — لا فرع
        #  حسب service_key هنا (Shell لا تعرف معنى الخدمة، P2 §14).
        self.workspace.command_manager.commandExecuted.connect(self._on_command_executed)

        #  ‏P0.3 §4: لا شريط حالة ثانٍ — الرسائل تعيش في WorkStatusBar
        #  وحدها (لا نستدعي self.statusBar()/setStatusBar هنا؛ البنية
        #  الأصلية لِـQMainWindow تبقى متاحة، فقط غير مُستخدَمة في Shell).
        self.workspace.work_status_bar.set_message("جاهز")

        #  Home هي الشاشة الابتدائية — زرّها في TopBar يبدأ نشِطاً.
        self.top_bar.set_home_active(True)

    # ------------------------------------------------------------- تنقّل
    def go_home(self) -> None:
        self.workspace.show_home()
        self.top_bar.set_home_active(True)
        self.workspace.work_status_bar.set_message("الرئيسية")

    def _open_service_start(self, key: str) -> None:
        service = next(
            (s for s in self.workspace.home_view.services() if s.key == key), None
        )
        if service is None:
            return
        self.workspace.show_service_start(service)
        self.top_bar.set_home_active(False)
        self.workspace.work_status_bar.set_message(f"خدمة: {service.title}")

    def open_service_start(self, service: ServiceDescriptor) -> None:
        """نقطة دخول برمجية مباشرة (تُستخدم في الاختبارات)."""
        self.workspace.show_service_start(service)
        self.top_bar.set_home_active(False)

    def _on_work_activated(self, key) -> None:
        """‏P1 §15: تحديث بسيطٌ لرسالة WorkStatusBar عند تفعيل عملٍ —
        اختياريّ، بلا ربط Commands/Zoom/Pages حقيقية. ``key=None`` (لا
        عمل نشِط) لا يفعل شيئاً هنا؛ go_home()/_open_service_start()
        يضبطان رسالتيهما الخاصّتين صراحةً."""
        if key is None:
            return
        session = self.workspace.workspace_manager.get(key)
        if session is None:
            return
        self.top_bar.set_home_active(False)
        self.workspace.work_status_bar.set_message(session.title)

    def _on_command_executed(self, key, command_id) -> None:
        """‏P2 §10: تحديثٌ عامّ لرسالة WorkStatusBar بعد تنفيذ أمرٍ —
        النصّ مبنيّ من ``CommandSpec.label`` العامّ + عنوان العمل، بلا
        أيّ معرفة بمعنى الخدمة (لا ``if service_key == ...`` هنا)."""
        session = self.workspace.workspace_manager.get(key)
        if session is None:
            return
        from ui2.shell.commands import COMMAND_REGISTRY
        spec = next((s for s in COMMAND_REGISTRY if s.id == command_id), None)
        label = spec.label if spec is not None else str(command_id)
        self.workspace.work_status_bar.set_message(f"تم تنفيذ {label} — {session.title}")

    def _sync_brand_width(self, *_args) -> None:
        sizes = self.splitter.sizes()
        if sizes:
            self.top_bar.set_brand_width(sizes[0])

    # --------------------------------------------------- Demo Works (P1 §11)
    def enable_demo_tabs(self) -> None:
        """يفتح ثلاثة أعمالٍ تجريبية **عبر WorkspaceManager الحقيقيّ**
        (نفس الأنبوب الذي ستستعمله Paie/CD لاحقاً) لتقييم WorkTabBar
        بصرياً فقط — لا Work lifecycle حقيقيّ إضافي، لا كتابة قاعدة
        بيانات. تُستدعى فقط من نقطة الدخول التجريبية
        (``python -m ui2.shell --demo-tabs``) أو صراحةً من اختبار.

        تنتهي على Home (لا على آخر عملٍ فُتح) — إثباتٌ حيّ أنّ العودة
        لِـHome لا تُغلق الأعمال المفتوحة (P1 §6)."""
        from ui2.shell.demo_tabs import DEMO_WORK_SPECS, build_demo_session
        for spec in DEMO_WORK_SPECS:
            self.workspace.workspace_manager.open_work(build_demo_session(spec))
        self.go_home()

    def enable_demo_many_tabs(self, count: int = 13) -> None:
        """‏P2.1 §15: يفتح ``count`` عملاً تجريبياً (عناوين قصيرة/طويلة
        مختلطة عمداً) عبر ``WorkspaceManager`` الحقيقيّ — لإثبات العرض
        الموحَّد + ellipsis + overflow/scroll + قائمة «كلّ الأعمال»
        يدوياً (``python -m ui2.shell --demo-many-tabs``) أو من اختبار."""
        from ui2.shell.demo_tabs import build_many_demo_sessions
        for session in build_many_demo_sessions(count):
            self.workspace.workspace_manager.open_work(session)
        self.go_home()
