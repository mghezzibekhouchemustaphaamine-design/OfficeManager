"""WorkspaceHost — قلب Shell: CommandBar + WorkTabBar + ContentStack.

قصداً **لا** ``QTabWidget`` كحاوية موحّدة — Works منفصلة معمارياً عن
محتوى العرض (Home / Service Start View)؛ الأخيرتان تُعرَضان في
``ContentStack`` بلا أن تصبحا Work (P1 §7).

‏**فصل P1 §4**: ``WorkTabBar`` هنا عرضٌ بصريّ بحت (presentation) — لا
تعرف شيئاً عن ``WorkSession``/``WorkspaceManager``. مصدر الحقيقة عن
الأعمال المفتوحة هو ``ui2.shell.workspace_manager.WorkspaceManager``
وحده (``WorkspaceHost.workspace_manager``)؛ هذا الشريط يعرض فقط ما
تُمليه إشاراته، ويُصدر أحداث النقر/الإغلاق ليقرِّر المدير بها.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel, QPushButton, QStackedWidget, QTabBar, QVBoxLayout, QWidget,
)

from ui2 import theme
from ui2.shell.command_bar import CommandBar
from ui2.shell.command_manager import CommandManager
from ui2.shell.home import HomeView
from ui2.shell.services import ServiceDescriptor
from ui2.shell.work import WorkKey
from ui2.shell.work_status_bar import WorkStatusBar
from ui2.shell.workspace_manager import WorkspaceManager

WORK_TAB_BAR_HEIGHT = 34


class WorkTabBar(QTabBar):
    """عرضٌ بصريّ بحت لأعمالٍ مفتوحة — لا حالة خاصّة به (P1 §4): كل
    تبويبٍ يحمل ``WorkKey`` صاحبه عبر ``setTabData`` (لا تطابق بالعنوان
    — P1 §8)، ويبقى ظاهراً وبارتفاع ثابت حتى فارغاً (P0 §5).

    **ترتيب Tabs ثابتٌ LEFT to RIGHT (P1 §1)**: أوّل عملٍ يُفتَح أقصى
    اليسار، وكلّ عملٍ جديد يُضاف يمين سابقه — ``setLayoutDirection``
    صريحٌ هنا (STRUCTURAL DIRECTION != TEXT DIRECTION، نفس مبدأ
    splitter/WorkStatusBar) لأنّ QTabBar بلا هذا يرث RTL من
    WorkspaceHost الأب فينعكس ترتيب التبويبات بالكامل.

    **لغة بصريّة Active/Inactive/Hover** كما في P0 (بلا تغيير): ACTIVE
    بخطٍّ سفليّ Accent، INACTIVE برماديّ محايد، HOVER بينهما. مؤشّرا
    dirty(●)/locked(🔒) يصلان ضمن نصّ التبويب نفسه (``WorkSession.
    display_text``) — لا لونٌ إضافيّ للتبويب كاملاً بسببهما (P1 §9)."""

    #  نقرة/تنشيط تبويب أو طلب إغلاقه — كلاهما يحمل WorkKey صاحب
    #  التبويب مباشرةً، لا فهرساً خاماً (المستهلك: WorkspaceHost).
    tabActivateRequested = Signal(object)      # WorkKey
    tabCloseKeyRequested = Signal(object)      # WorkKey

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(WORK_TAB_BAR_HEIGHT)
        self.setExpanding(False)
        self.setDrawBase(False)
        #  P1 §1: انظر شرح الصنف أعلاه — بلا هذا يرث RTL من الأب فينعكس
        #  ترتيب Tabs (أوّل عملٍ يظهر يميناً بدل يساراً).
        self.setLayoutDirection(Qt.LeftToRight)
        #  P0.3 §6: زرّ إغلاق × قياسيّ من Qt على كلّ تبويب — يظهر فقط
        #  حين توجد تبويبات؛ بلا أثرٍ حين الشريط فارغ.
        self.setTabsClosable(True)
        self.tabCloseRequested.connect(self._emit_close_requested)
        #  ‏P2 (Drag & Drop): إعادة ترتيب الأعمال المفتوحة بالسحب. Qt
        #  ينقل التبويب بصرياً (مع tabData الخاصّ به) بنفسه؛ WorkspaceHost
        #  يستمع لِـtabMoved ليزامن WorkspaceManager._order معه — هذا
        #  الصنف لا يعرف شيئاً عن WorkspaceManager (presentation بحتة).
        self.setMovable(True)
        #  نقرةٌ حقيقية على أيّ تبويب — بما فيها الفهرس 0 (Qt يختاره
        #  تلقائياً عند أوّل addTab بلا إصدار currentChanged، فلا يكفي
        #  الاعتماد عليها وحدها لالتقاط أوّل نقرة فعلية على ذلك التبويب).
        self.tabBarClicked.connect(self._emit_activate_requested)
        #  ‏P2 (Drag & Drop): currentChanged يُصدَره Qt أيضاً حين يتحرّك
        #  التبويب "الحاليّ" فعلياً بلا أن يتغيّر (سحب/moveTab — نفس
        #  الهويّة، فقط موضعٌ رقميّ مختلف) — لا حين يختار المستخدم تبويباً
        #  آخر فعلياً. ``_last_current_key`` يميّز الحالتين (راجع
        #  ``_on_current_changed``) بدل الاعتماد المباشر على الفهرس.
        self._last_current_key = None
        self.currentChanged.connect(self._on_current_changed)
        #  P0.1 §4: خلفية الشريط نفسه كانت مطابقةً تماماً لخلفية النافذة
        #  (BG) فيختفي بصرياً حين يكون فارغاً بلا تبويبات — الآن SURFACE
        #  + حدّ سفليّ خفيف يجعلان مكان «منطقة تبويبات الأعمال» مقروءاً
        #  دائماً، فارغاً كان أم لا، بلا أيّ تبويب وهميّ.
        #
        #  P0.3 §6/§9: QTabBar.setCurrentIndex(-1) لا يعمل فعلياً بعد
        #  إضافة تبويبات (Qt يُبقي فهرساً صالحاً دائماً، يتجاهل -1
        #  صامتاً) — فلا يمكن الاعتماد على "لا فهرس محدَّد" لإخفاء حالة
        #  Active بصرياً عند Home. البديل: خاصّية Qt الديناميكية
        #  workActive تتحكّم بتفعيل نمط :selected نفسه عبر QSS — عند
        #  Home/ServiceStartView تصير False فيبدو التبويب "الحاليّ"
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

    def index_for_key(self, key: WorkKey) -> int:
        """فهرس تبويبٍ مفتاحه ``key``، أو -1 — مطابقةٌ بالمفتاح لا
        بالعنوان (P1 §8): إعادة ترتيب/تسمية لا تُفقِد العلاقة."""
        for i in range(self.count()):
            if self.tabData(i) == key:
                return i
        return -1

    def mark_current_key(self, key: WorkKey) -> None:
        """يُخبر الشريط أنّ ``key`` أصبح تبويب Qt "الحاليّ" فعلياً — يُستدعى
        من ``WorkspaceHost`` كلّما ضبط ``currentIndex`` برمجياً (حتى مع
        ``blockSignals``)، ليبقى ``_last_current_key`` مطابقاً للواقع
        (P2 Drag & Drop: بدونه، أوّل سحبٍ للتبويب الحاليّ بعد أيّ تفعيلٍ
        صامت كان سيُقرأ خطأً كاختيارٍ جديد)."""
        self._last_current_key = key

    def _emit_activate_requested(self, index: int) -> None:
        if index < 0:
            return
        key = self.tabData(index)
        if key is not None:
            self._last_current_key = key
            self.tabActivateRequested.emit(key)

    def _on_current_changed(self, index: int) -> None:
        """مثل ``_emit_activate_requested`` مع حارسٍ إضافي: تغيّر
        ``currentIndex`` الرقميّ بلا تغيّر هويّة التبويب "الحاليّ" فعلياً
        (يحدث عند سحب/``moveTab`` لنفس التبويب المُفعَّل مسبقاً) لا يجب
        أن يُصدر طلب تفعيل — فقط اختيارٌ حقيقيّ لهويّةٍ مختلفة (نقرة على
        تبويبٍ آخر، تنقّل لوحة مفاتيح، أو ``setCurrentIndex`` برمجيّ
        مقصود) يفعل."""
        if index < 0:
            return
        key = self.tabData(index)
        if key is None or key == self._last_current_key:
            return
        self._last_current_key = key
        self.tabActivateRequested.emit(key)

    def _emit_close_requested(self, index: int) -> None:
        key = self.tabData(index)
        if key is not None:
            self.tabCloseKeyRequested.emit(key)

    def _debug_add_tab(self, title: str) -> int:
        """أداة تطوير/إثبات معماري فقط — غير مستخدَمة في مسار المنتج."""
        return self.addTab(title)


class ServiceStartView(QWidget):
    """نقطة انطلاق خدمة — اسم + وصف + Nouveau/Ouvrir existant (placeholders).

    لا تُنشئ Work Tab ولا تنفّذ أي workflow حقيقي في هذه المرحلة (P1 §16:
    اختيار خدمة لا يفتح Work — Nouveau/Ouvrir لاحقاً)."""

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
        #  P0.2 §3: محاذاةٌ **مطلقة** يميناً (Qt.AlignRight — لا AlignLeading
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


class WorkspaceHost(QWidget):
    """يجمّع CommandBar + WorkTabBar + ContentStack + WorkStatusBar عمودياً.

    ‏**مصدر الحقيقة عن الأعمال المفتوحة هو** ``self.workspace_manager``
    (‏:class:`~ui2.shell.workspace_manager.WorkspaceManager`) — هذا
    الصنف يستمع لإشاراته ويعكسها على WorkTabBar/ContentStack فقط؛ لا
    يُخزَّن أيّ حالة عملٍ هنا مباشرةً (P1 §4/§14).

    ‏``show_home()``/``show_service_start(descriptor)`` يعرضان محتوى
    ContentStack ويُخبران المدير أن لا عمل نشِطاً حالياً — الأعمال
    المفتوحة **تبقى مفتوحة** (P1 §6/§7/§13). بقيّة الأشرطة لا يتغيّر
    مكانها (P0.2 §8: لا layout jumping). WorkStatusBar أسفل Workspace
    فقط — ليس ابناً لِـ splitter، بل لهذا الودجت وحده."""

    def __init__(self, parent=None):
        super().__init__(parent)
        #  P0.1 §1: splitter الأب صار LTR هندسياً (Explorer|Workspace) —
        #  ذلك الاتجاه يورَّث افتراضياً لهذا الودجت وكل أبنائه. محتوى
        #  Workspace نفسه (عناوين/بطاقات/أزرار عربيّة) يبقى RTL كما كان
        #  دائماً — إعادة ضبطٍ صريحة هنا تفصل اتجاه القراءة الداخليّ عن
        #  القرار الهندسيّ الخارجيّ (STRUCTURAL DIRECTION != TEXT DIRECTION).
        self.setLayoutDirection(Qt.RightToLeft)

        #  P1 §13/§14: "شاشة Shell" (Home/ServiceStartView) معروضة حالياً
        #  أم لا — حالةٌ يملكها Host نفسه، منفصلة عن WorkspaceManager
        #  (الذي لا يعرف سوى "عملٌ نشِط" أو "لا شيء"). تمنع أيضاً حلقة
        #  استدعاءٍ ذاتية بين show_home() و_on_work_activated(None).
        self._showing_shell = True

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.command_bar = CommandBar(self)
        lay.addWidget(self.command_bar)

        self.work_tab_bar = WorkTabBar(self)
        self.work_tab_bar.tabActivateRequested.connect(self._on_tab_activate_requested)
        self.work_tab_bar.tabCloseKeyRequested.connect(self._on_tab_close_requested)
        #  ‏P2 (Drag & Drop): Qt نقل التبويب بصرياً فعلاً قبل إصدار هذه
        #  الإشارة — هنا فقط نزامن WorkspaceManager._order معه.
        self.work_tab_bar.tabMoved.connect(self._on_tab_moved)
        lay.addWidget(self.work_tab_bar)

        self.content_stack = QStackedWidget(self)
        lay.addWidget(self.content_stack, 1)

        self.home_view = HomeView(parent=self)
        self.content_stack.addWidget(self.home_view)

        self.service_start_view = ServiceStartView(self)
        self.content_stack.addWidget(self.service_start_view)

        self.work_status_bar = WorkStatusBar(self)
        lay.addWidget(self.work_status_bar)

        #  P1 §4: مصدر الحقيقة الوحيد لدورة حياة الأعمال المفتوحة.
        self.workspace_manager = WorkspaceManager(self)
        self.workspace_manager.opened.connect(self._on_work_opened)
        self.workspace_manager.activated.connect(self._on_work_activated)
        self.workspace_manager.closed.connect(self._on_work_closed)
        self.workspace_manager.titleChanged.connect(self._on_work_title_or_state_changed)
        self.workspace_manager.dirtyChanged.connect(self._on_work_title_or_state_changed)
        self.workspace_manager.lockedChanged.connect(self._on_work_title_or_state_changed)

        #  ‏P2 §6: CommandManager يُبنى فوق WorkspaceManager — لا يستبدله،
        #  لا يخزّن حالةً موازية. CommandBar عرضٌ بحت يستهلك أوامره فقط.
        self.command_manager = CommandManager(self.workspace_manager, self)
        self.command_bar.set_command_manager(self.command_manager)

        self.show_home()

    # -------------------------------------------------------- شاشات Shell
    def show_home(self) -> None:
        self._showing_shell = True
        self.content_stack.setCurrentWidget(self.home_view)
        self.workspace_manager.deactivate()

    def show_service_start(self, service: ServiceDescriptor) -> None:
        self._showing_shell = True
        self.service_start_view.set_service(service)
        self.content_stack.setCurrentWidget(self.service_start_view)
        self.workspace_manager.deactivate()

    def current_view(self) -> QWidget:
        return self.content_stack.currentWidget()

    # -------------------------------------------- WorkTabBar → WorkspaceManager
    def _on_tab_activate_requested(self, key: WorkKey) -> None:
        self.workspace_manager.activate_work(key)

    def _on_tab_close_requested(self, key: WorkKey) -> None:
        self.workspace_manager.close_work(key)

    def _on_tab_moved(self, from_index: int, to_index: int) -> None:
        """‏P2 (Drag & Drop): Qt نقل التبويب (وtabData معه) بصرياً بالفعل
        — لا نلمس QTabBar هنا، فقط نُبقي WorkspaceManager._order مطابقاً
        (لا يفعِّل شيئاً، لا يغيّر الهويّة/الـwidget، P2 §Drag&Drop)."""
        self.workspace_manager.move_work(from_index, to_index)

    # -------------------------------------------- WorkspaceManager → الواجهة
    def _on_work_opened(self, session) -> None:
        """عملٌ جديد انضمّ (بعد تأكّد المدير من عدم التكرار، P1 §5) —
        Tab واحدة + إضافة widget السطر إلى ContentStack، بلا عرضه بعد
        (التفعيل يصل عبر إشارة ``activated`` منفصلة)."""
        idx = self.work_tab_bar.addTab(session.display_text())
        self.work_tab_bar.setTabData(idx, session.key)
        self.content_stack.addWidget(session.widget)

    def _on_work_activated(self, key) -> None:
        if key is None:
            #  لا عمل نشِطاً — يحدث عند show_home()/show_service_start()
            #  الصريحتين (ContentStack مضبوطةٌ مسبقاً هناك، فلا شيء إضافيّ
            #  هنا) أو عند إغلاق آخر عملٍ نشِط (P1 §10: نعرض Home حينها،
            #  لأن Host لم يكن أصلاً "يعرض شاشة Shell" في تلك اللحظة).
            self.work_tab_bar.set_active(False)
            if not self._showing_shell:
                self._showing_shell = True
                self.content_stack.setCurrentWidget(self.home_view)
            return

        self._showing_shell = False
        idx = self.work_tab_bar.index_for_key(key)
        if idx >= 0:
            self.work_tab_bar.blockSignals(True)
            self.work_tab_bar.setCurrentIndex(idx)
            self.work_tab_bar.blockSignals(False)
            #  ‏P2 Drag & Drop: يُبقي WorkTabBar._last_current_key مطابقاً
            #  للواقع رغم blockSignals — راجع WorkTabBar.mark_current_key.
            self.work_tab_bar.mark_current_key(key)
        self.work_tab_bar.set_active(True)
        session = self.workspace_manager.get(key)
        if session is not None:
            self.content_stack.setCurrentWidget(session.widget)

    def _on_work_closed(self, session) -> None:
        idx = self.work_tab_bar.index_for_key(session.key)
        if idx >= 0:
            self.work_tab_bar.blockSignals(True)
            self.work_tab_bar.removeTab(idx)
            self.work_tab_bar.blockSignals(False)
        self.content_stack.removeWidget(session.widget)
        session.widget.deleteLater()

    def _on_work_title_or_state_changed(self, key, _value) -> None:
        """title/dirty/locked أيّاً تغيّر — إعادة رسم نصّ التبويب فوراً
        (P1 §9)؛ لا تغيير للون التبويب كاملاً بسبب dirty/locked."""
        idx = self.work_tab_bar.index_for_key(key)
        session = self.workspace_manager.get(key)
        if idx >= 0 and session is not None:
            self.work_tab_bar.setTabText(idx, session.display_text())
