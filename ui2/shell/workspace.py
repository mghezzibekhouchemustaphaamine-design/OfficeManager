"""WorkspaceHost — قلب Shell: CommandBar + WorkTabBar + ContentStack.

قصداً **لا** ``QTabWidget`` كحاوية موحّدة — التبويبات (أعمال مفتوحة
مستقبلاً) منفصلة معمارياً عن محتوى العرض (Home / Service Start View).
Home وService Start View تُعرَضان في ``ContentStack`` بلا أن تصبحا
تبويباً. راجع بند 4/9 في المهمّة.

``WorkTabBar`` هنا Prototype بلا ربط بأعمال حقيقية بعد — ``_debug_add_tab``
موجودة فقط لإثبات أن الشريط يبقى مستقلاً عن ContentStack، وليست جزءاً من
سلوك المنتج (لا يستدعيها أي شيء تلقائياً).
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel, QPushButton, QStackedWidget, QTabBar, QVBoxLayout, QWidget,
)

from ui2 import theme
from ui2.shell.command_bar import CommandBar
from ui2.shell.home import HomeView
from ui2.shell.services import ServiceDescriptor
from ui2.shell.work_status_bar import WorkStatusBar

WORK_TAB_BAR_HEIGHT = 34


class WorkTabBar(QTabBar):
    """شريط تبويبات الأعمال المفتوحة — منفصل تماماً عن ContentStack.

    Prototype: لا تبويبات حقيقية بعد. يبقى ظاهراً وبارتفاع ثابت حتى وهو
    فارغ (بند 5 — ثبات الـ layout).

    **لغة بصريّة Active/Inactive (P0.2 §5)** — تجهيزٌ بصريّ مسبق قبل ربط
    أعمالٍ حقيقية:

    * ACTIVE (التبويب الحاليّ): خطٌّ سفليّ بلون Accent (``theme.PRIMARY``)
      + نصٌّ بلون Accent غامق — واضحٌ بصرياً، لا مجرّد اختلاف خلفية خفيف.
    * OPEN BUT INACTIVE: خلفية محايدة رماديّة (``theme.ROW_ALT``) —
      مفتوحٌ لكن غير مركَّزٌ عليه.
    * HOVER: درجة بين الاثنين (``theme.SELECTION``).

    عندما لا توجد تبويبات (Home/ServiceStartView معروضتان) لا شيء
    "نشِط" أصلاً — ``currentIndex() == -1`` طبيعياً، فحالة :selected لا
    تُطبَّق على أيّ شيء. مؤشّرات مستقبليّة (●  للتعديل غير المحفوظ، 🔒
    للقفل) غير منفَّذة الآن — تحتاج lifecycle عملٍ حقيقيّ لاحقاً."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(WORK_TAB_BAR_HEIGHT)
        self.setExpanding(False)
        self.setDrawBase(False)
        #  ‏P0.3 §6: زرّ إغلاق × قياسيّ من Qt على كلّ تبويب — يظهر فقط
        #  حين توجد تبويبات (Demo أو حقيقية مستقبلاً)؛ بلا أثرٍ حين
        #  الشريط فارغ. تبسيطٌ مقصود (بلا تخصيص شفافية إضافي per-state).
        self.setTabsClosable(True)
        self.tabCloseRequested.connect(self.removeTab)
        #  ‏P0.1 §4: خلفية الشريط نفسه كانت مطابقةً تماماً لخلفية النافذة
        #  (BG) فيختفي بصرياً حين يكون فارغاً بلا تبويبات — الآن SURFACE
        #  + حدّ سفليّ خفيف يجعلان مكان «منطقة تبويبات الأعمال» مقروءاً
        #  دائماً، فارغاً كان أم لا، بلا أيّ تبويب وهميّ.
        #
        #  ‏P0.3 §6/§9: ``QTabBar.setCurrentIndex(-1)`` **لا يعمل** فعلياً
        #  بعد إضافة تبويبات (Qt يُبقي فهرساً صالحاً دائماً، يتجاهل -1
        #  صامتاً) — فلا يمكن الاعتماد على "لا فهرس محدَّد" لإخفاء حالة
        #  Active بصرياً عند Home. البديل: خاصّية Qt الديناميكية
        #  ``workActive`` تتحكّم بتفعيل نمط ``:selected`` نفسه عبر QSS —
        #  عند Home/ServiceStartView تصير False فيبدو التبويب "الحاليّ"
        #  محايداً كأيّ تبويبٍ آخر، دون التأثير في فهرسه الداخليّ.
        self.setProperty("workActive", False)
        self.setStyleSheet(f"""
            QTabBar {{ background: {theme.SURFACE};
                       border-bottom: 1px solid {theme.BORDER}; }}
            QTabBar::tab {{
                background: {theme.ROW_ALT};
                color: {theme.TEXT_DIM};
                border: 1px solid {theme.BORDER};
                border-bottom: none;
                padding: 6px 14px;
                margin-right: 2px;
            }}
            QTabBar::tab:hover {{
                background: {theme.SELECTION};
                color: {theme.TEXT};
            }}
            QTabBar[workActive="true"]::tab:selected {{
                background: {theme.SURFACE};
                color: {theme.PRIMARY_DK};
                font-weight: 600;
                border-bottom: 2px solid {theme.PRIMARY};
            }}
        """)

    def set_active(self, active: bool) -> None:
        """يتحكّم بظهور نمط ACTIVE (خطّ Accent) على التبويب "الحاليّ" —
        منفصلٌ عمداً عن ``currentIndex`` (انظر الشرح أعلاه)."""
        self.setProperty("workActive", bool(active))
        self.style().unpolish(self)
        self.style().polish(self)

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
        #  ‏P0.2 §3: محاذاةٌ **مطلقة** يميناً (Qt.AlignRight — لا AlignLeading
        #  التي تتبع اتجاه النصّ المكتشَف تلقائياً) — عنوانٌ لاتينيّ محضٌ
        #  مثل "CD" كان يُحاذى يساراً تلقائياً فيقفز عن بقيّة العناوين
        #  العربية. الموضع الآن ثابتٌ يميناً دائماً؛ شكل النصّ نفسه
        #  (تشكيل الحروف LTR/RTL) يبقى تابعاً لمحتواه كما هو طبيعيّ.
        self._title.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self._title)

        self._desc = QLabel()
        self._desc.setStyleSheet(f"color: {theme.TEXT_DIM};")
        self._desc.setWordWrap(True)
        self._desc.setAlignment(Qt.AlignRight | Qt.AlignTop)
        lay.addWidget(self._desc)

        self.btn_nouveau = QPushButton("جديد")
        self.btn_ouvrir = QPushButton("فتح موجود")
        lay.addWidget(self.btn_nouveau)
        lay.addWidget(self.btn_ouvrir)
        lay.addStretch(1)

    def set_service(self, service: ServiceDescriptor) -> None:
        self._title.setText(service.title)
        self._desc.setText(service.description)


class DemoWorkView(QWidget):
    """محتوى Placeholder بسيط جداً لعملٍ تجريبيّ — يثبت فقط أنّ اختيار
    تبويبٍ Demo يبدّل ContentStack (P0.3 §6)؛ لا workflow حقيقي."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(
            theme.SPACE["lg"], theme.SPACE["lg"], theme.SPACE["lg"], theme.SPACE["lg"]
        )
        self._label = QLabel("")
        self._label.setStyleSheet(
            f"font-size: {theme.FONT_SIZES['title']}px; font-weight: 600;"
            f" color: {theme.TEXT_DIM};"
        )
        self._label.setAlignment(Qt.AlignRight | Qt.AlignTop)
        lay.addWidget(self._label)
        lay.addStretch(1)

    def set_title(self, title: str) -> None:
        self._label.setText(f"معاينة تجريبية — {title}")


class WorkspaceHost(QWidget):
    """يجمّع CommandBar + WorkTabBar + ContentStack + WorkStatusBar عمودياً.

    ``show_home()`` / ``show_service_start(descriptor)`` يتحكّمان بمحتوى
    ContentStack فقط — بقيّة الأشرطة لا يتغيّر مكانها (P0.2 §8: لا
    layout jumping). WorkStatusBar أسفل Workspace فقط — لا يمتدّ تحت
    Explorer (ليس ابناً لِـ splitter، بل لهذا الودجت وحده).

    ‏**Demo Work Tabs (P0.3 §6)**: معطَّلة افتراضياً (``work_tab_bar``
    فارغ في الوضع العاديّ). :meth:`enable_demo_tabs` وحدها تملؤها —
    تُستدعى فقط من نقطة الدخول التجريبية، لا تلقائياً أبداً."""

    #  يُصدَر عند اختيار تبويب Demo — main_window يستمع له ليُنشِّط
    #  حالة Home غير النشِطة في TopBar (نفس معاملة ServiceStartView).
    demoWorkActivated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        #  ‏P0.1 §1: splitter الأب صار LTR هندسياً (Explorer|Workspace) —
        #  ذلك الاتجاه يورَّث افتراضياً لهذا الودجت وكل أبنائه. محتوى
        #  Workspace نفسه (عناوين/بطاقات/أزرار عربيّة) يبقى RTL كما كان
        #  دائماً — إعادة ضبطٍ صريحة هنا تفصل اتجاه القراءة الداخليّ عن
        #  القرار الهندسيّ الخارجيّ (STRUCTURAL DIRECTION != TEXT DIRECTION).
        self.setLayoutDirection(Qt.RightToLeft)
        self._demo_tabs_enabled = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.command_bar = CommandBar(self)
        lay.addWidget(self.command_bar)

        self.work_tab_bar = WorkTabBar(self)
        self.work_tab_bar.currentChanged.connect(self._on_tab_changed)
        #  ‏P0.3 §6/§9: Qt يختار تلقائياً الفهرس 0 عند أوّل ``addTab`` بلا
        #  إصدار currentChanged (لا "تغيّر" فعليّ من منظوره) — فالنقر
        #  الحقيقيّ الأوّل على ذلك التبويب بالذات لن يُفعِّله بصرياً لو
        #  اعتمدنا على currentChanged وحدها. ``tabBarClicked`` يُصدَر عند
        #  كل نقرةٍ فعليّة بصرف النظر عن تغيّر الفهرس من عدمه.
        self.work_tab_bar.tabBarClicked.connect(self._on_tab_changed)
        lay.addWidget(self.work_tab_bar)

        self.content_stack = QStackedWidget(self)
        lay.addWidget(self.content_stack, 1)

        self.home_view = HomeView(parent=self)
        self.content_stack.addWidget(self.home_view)

        self.service_start_view = ServiceStartView(self)
        self.content_stack.addWidget(self.service_start_view)

        self.demo_work_view = DemoWorkView(self)
        self.content_stack.addWidget(self.demo_work_view)

        self.work_status_bar = WorkStatusBar(self)
        lay.addWidget(self.work_status_bar)

        self.show_home()

    def show_home(self) -> None:
        self.content_stack.setCurrentWidget(self.home_view)
        self._deactivate_tabs()

    def show_service_start(self, service: ServiceDescriptor) -> None:
        self.service_start_view.set_service(service)
        self.content_stack.setCurrentWidget(self.service_start_view)
        self._deactivate_tabs()

    def current_view(self) -> QWidget:
        return self.content_stack.currentWidget()

    def _deactivate_tabs(self) -> None:
        """لا تبويب Demo يبدو Active عند Home أو ServiceStartView (بند 6:
        «لا يجب أن يبدو أي Work Tab active»). ``WorkTabBar.set_active(False)``
        يُخفي نمط ACTIVE بصرياً فقط — ``currentIndex`` الداخليّ يبقى
        كما هو (Qt لا يقبل -1 فعلياً بعد إضافة تبويبات)."""
        if self._demo_tabs_enabled:
            self.work_tab_bar.set_active(False)

    # --------------------------------------------------- Demo Tabs (P0.3 §6)
    def enable_demo_tabs(self, items) -> None:
        """يملأ WorkTabBar بتبويبات تجريبية للتقييم البصريّ فقط — انظر
        تحذير ``ui2.shell.demo_tabs`` (لا تدخل مسار المنتج الحقيقي)."""
        self._demo_tabs_enabled = True
        self.work_tab_bar.blockSignals(True)
        while self.work_tab_bar.count():                 # QTabBar لا تملك clear()
            self.work_tab_bar.removeTab(0)
        for item in items:
            idx = self.work_tab_bar.addTab(item.display_text())
            self.work_tab_bar.setTabData(idx, item.title)
        self.work_tab_bar.blockSignals(False)
        self._deactivate_tabs()

    def _on_tab_changed(self, index: int) -> None:
        if not self._demo_tabs_enabled or index < 0:
            return
        title = self.work_tab_bar.tabData(index)
        self.demo_work_view.set_title(title)
        self.content_stack.setCurrentWidget(self.demo_work_view)
        self.work_tab_bar.set_active(True)
        self.demoWorkActivated.emit(title)
