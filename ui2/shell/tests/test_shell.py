"""اختبارات بنية Shell (Prototype) — معمارية لا شكل بصري.

التشغيل:
    python -m unittest discover -s ui2/shell/tests
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QStatusBar
    _HAS_QT = True
except Exception:                                    # noqa: BLE001
    _HAS_QT = False

if _HAS_QT:
    from PySide6.QtWidgets import QLabel
    from ui2 import theme
    from ui2.shell.command_manager import CommandManager
    from ui2.shell.commands import CommandId
    from ui2.shell.home import HomeView, ServiceCard
    from ui2.shell.main_window import OfficeMainWindow
    from ui2.shell.services import ServiceDescriptor, default_services
    from ui2.shell.work import WorkKey, WorkSession
    from ui2.shell.workspace import ServiceStartView, WorkTabBar
    from ui2.shell.workspace_manager import WorkspaceManager


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class ShellStructureTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self.win = OfficeMainWindow()

    def tearDown(self):
        self.win.deleteLater()

    # --------------------------------------------------------- Home أوّلاً
    def test_home_is_initial_view(self):
        self.assertIs(self.win.workspace.current_view(), self.win.workspace.home_view)

    # ------------------------------------------------- الانتقال إلى خدمة
    def test_service_request_switches_to_service_start_view(self):
        svc = default_services()[0]
        self.win.open_service_start(svc)
        self.assertIs(
            self.win.workspace.current_view(), self.win.workspace.service_start_view
        )

    def test_clicking_card_switches_content_stack(self):
        card = self.win.workspace.home_view._cards["cd"]
        card.clicked.emit("cd")
        self.assertIs(
            self.win.workspace.current_view(), self.win.workspace.service_start_view
        )

    # --------------------------------------------------------- زرّ Home
    def test_home_action_returns_to_home(self):
        self.win.open_service_start(default_services()[0])
        self.win.go_home()
        self.assertIs(self.win.workspace.current_view(), self.win.workspace.home_view)

    def test_top_bar_home_button_returns_home(self):
        self.win.open_service_start(default_services()[0])
        self.win.top_bar.btn_home.click()
        self.assertIs(self.win.workspace.current_view(), self.win.workspace.home_view)

    # -------------------------------------------------- Cards من Registry
    def test_home_cards_built_from_registry(self):
        home = HomeView()
        expected_keys = {s.key for s in default_services() if s.enabled}
        self.assertEqual(set(home._cards.keys()), expected_keys)
        for card in home._cards.values():
            self.assertIsInstance(card, ServiceCard)

    def test_disabled_service_has_no_card(self):
        services = [
            ServiceDescriptor(key="a", title="أ", description="", enabled=True),
            ServiceDescriptor(key="b", title="ب", description="", enabled=False),
        ]
        home = HomeView(services=services)
        self.assertEqual(set(home._cards.keys()), {"a"})

    # --------------------------------------------- WorkTabBar منفصل عن Stack
    def test_work_tab_bar_independent_of_content_stack(self):
        self.assertIsInstance(self.win.workspace.work_tab_bar, WorkTabBar)
        self.win.workspace.work_tab_bar._debug_add_tab("عمل تجريبي")
        # إضافة تبويب لا تغيّر محتوى ContentStack (يبقى Home)
        self.assertIs(self.win.workspace.current_view(), self.win.workspace.home_view)
        self.assertEqual(self.win.workspace.work_tab_bar.count(), 1)

    def test_switching_view_does_not_create_work_tab(self):
        before = self.win.workspace.work_tab_bar.count()
        self.win.open_service_start(default_services()[0])
        self.win.go_home()
        self.assertEqual(self.win.workspace.work_tab_bar.count(), before)

    # --------------------------------------------------- ثبات ارتفاع الشريط
    def test_command_bar_and_tab_bar_keep_fixed_height_on_home(self):
        cb_height = self.win.workspace.command_bar.height()
        tb_height = self.win.workspace.work_tab_bar.height()
        self.win.open_service_start(default_services()[0])
        self.assertEqual(self.win.workspace.command_bar.height(), cb_height)
        self.assertEqual(self.win.workspace.work_tab_bar.height(), tb_height)

    # ------------------------------------------------ Service Start View
    def test_service_start_view_shows_service_title(self):
        svc = default_services()[1]
        self.win.open_service_start(svc)
        self.assertEqual(self.win.workspace.service_start_view._title.text(), svc.title)

    # ============== P0.1 §1/§2: اتجاه هندسيّ ثابت لِـExplorer|Workspace ==============
    def test_explorer_is_before_workspace_in_splitter(self):
        """موضعٌ منطقيّ: Explorer أوّل عنصرٍ في splitter، Workspace ثانياً —
        هذا الترتيب + LayoutDirection.LeftToRight الصريح يضمنان Explorer
        يساراً هندسياً دائماً (لا اختبار بكسل، فقط ترتيب/فهرس)."""
        self.assertEqual(
            self.win.splitter.indexOf(self.win.explorer_placeholder), 0)
        self.assertEqual(self.win.splitter.indexOf(self.win.workspace), 1)

    def test_explorer_x_is_left_of_workspace_x_after_layout(self):
        self.win.resize(1180, 720)
        self.win.show()
        self.assertLess(
            self.win.explorer_placeholder.x(), self.win.workspace.x())

    def test_splitter_structural_direction_is_explicit_ltr(self):
        """STRUCTURAL DIRECTION != TEXT DIRECTION: الحاوي المسؤول عن موضع
        Explorer/Workspace يحمل LTR صريحاً — لا اعتماداً على apply_theme
        العامّ (الذي يبقى RTL لبقيّة التطبيق)."""
        self.assertEqual(self.win.splitter.layoutDirection(), Qt.LeftToRight)

    def test_global_rtl_change_does_not_flip_explorer_workspace_order(self):
        """تغيير اتجاه التطبيق العامّ لاحقاً (لأيّ سببٍ آخر) لا يقلب مكان
        Explorer — الاتجاه البنيويّ مضبوطٌ صراحةً على splitter نفسه، لا
        موروثاً من QApplication."""
        original = self.app.layoutDirection()
        try:
            for direction in (Qt.LeftToRight, Qt.RightToLeft):
                self.app.setLayoutDirection(direction)
                self.assertEqual(
                    self.win.splitter.layoutDirection(), Qt.LeftToRight)
                self.assertEqual(
                    self.win.splitter.indexOf(self.win.explorer_placeholder), 0)
        finally:
            self.app.setLayoutDirection(original)

    def test_workspace_and_explorer_keep_rtl_text_direction(self):
        """الاتجاه الهندسيّ (splitter=LTR) لا يُسرَّب إلى محتوى Explorer/
        Workspace النصّيّ — كلٌّ منهما يعيد ضبط اتجاهه الخاصّ RTL صراحةً
        (فصل STRUCTURAL عن TEXT direction، بند 1 في المهمّة)."""
        self.assertEqual(self.win.workspace.layoutDirection(), Qt.RightToLeft)
        self.assertEqual(
            self.win.explorer_placeholder.layoutDirection(), Qt.RightToLeft)

    def test_top_bar_direction_is_explicit_not_accidental(self):
        """P0.2 §1 يبني على قرار P0.1: TopBar صار منطقتين بنيويّتين ثابتتي
        الموضع (Brand يساراً فوق Explorer، Nav يميناً فوق Workspace) —
        فاتجاهه الأعلى صار LTR صراحةً (نفس مبدأ splitter)، لا RTL كما
        كان في P0.1 حين كان محتوًى واحداً بلا تقسيمٍ بنيويّ."""
        self.assertEqual(self.win.top_bar.layoutDirection(), Qt.LeftToRight)

    # ============== P0.1 §3/§4: CommandBar/WorkTabBar يبقيان مكانهما ==============
    def test_command_bar_and_tab_bar_same_widgets_and_position_across_views(self):
        self.win.resize(1180, 720)
        self.win.show()
        cb, tb = self.win.workspace.command_bar, self.win.workspace.work_tab_bar
        cb_pos, tb_pos = cb.pos(), tb.pos()

        self.win.open_service_start(default_services()[0])
        self.assertIs(self.win.workspace.command_bar, cb)
        self.assertIs(self.win.workspace.work_tab_bar, tb)
        self.assertEqual(cb.pos(), cb_pos)
        self.assertEqual(tb.pos(), tb_pos)

        self.win.go_home()
        self.assertIs(self.win.workspace.command_bar, cb)
        self.assertIs(self.win.workspace.work_tab_bar, tb)
        self.assertEqual(cb.pos(), cb_pos)
        self.assertEqual(tb.pos(), tb_pos)

    # ==================== P0.2 §6: WorkStatusBar ====================
    def test_work_status_bar_exists_inside_workspace_below_content_stack(self):
        from ui2.shell.work_status_bar import WorkStatusBar
        wsb = self.win.workspace.work_status_bar
        self.assertIsInstance(wsb, WorkStatusBar)
        #  ابنٌ لِـWorkspaceHost نفسه (لا splitter) — لا يمتدّ تحت Explorer.
        self.assertIs(wsb.parent(), self.win.workspace)
        self.assertIs(
            self.win.explorer_placeholder.parent(), self.win.splitter)
        #  ترتيبٌ عموديّ: أسفل ContentStack (فهرسٌ أكبر في تخطيط Workspace).
        lay = self.win.workspace.layout()
        idx_stack = lay.indexOf(self.win.workspace.content_stack)
        idx_status = lay.indexOf(wsb)
        self.assertGreater(idx_status, idx_stack)

    def test_work_status_bar_keeps_position_across_views(self):
        self.win.resize(1180, 720)
        self.win.show()
        wsb = self.win.workspace.work_status_bar
        pos0 = wsb.pos()
        self.win.open_service_start(default_services()[0])
        self.assertIs(self.win.workspace.work_status_bar, wsb)
        self.assertEqual(wsb.pos(), pos0)
        self.win.go_home()
        self.assertEqual(wsb.pos(), pos0)

    # ==================== P0.2 §1: حالة Home النشِطة ====================
    def test_home_button_active_state_toggles_with_view(self):
        self.assertTrue(self.win.top_bar.btn_home.isChecked())   # Home ابتدائياً
        self.win.open_service_start(default_services()[0])
        self.assertFalse(self.win.top_bar.btn_home.isChecked())
        self.win.go_home()
        self.assertTrue(self.win.top_bar.btn_home.isChecked())

    # ============ P0.2 §11: تسلسل Home→CD→Home→Attestation كامل ============
    def test_home_cd_home_attestation_sequence_keeps_bars_fixed_no_work_tab(self):
        self.win.resize(1180, 720)
        self.win.show()
        top_pos = self.win.top_bar.pos()
        expl_pos = self.win.explorer_placeholder.pos()
        cb_pos = self.win.workspace.command_bar.pos()
        tb_pos = self.win.workspace.work_tab_bar.pos()
        tabs_before = self.win.workspace.work_tab_bar.count()

        services_by_key = {s.key: s for s in default_services()}
        for key in ("cd", None, "hr_attestation_travail"):
            if key is None:
                self.win.go_home()
                self.assertIs(
                    self.win.workspace.current_view(), self.win.workspace.home_view)
            else:
                self.win.open_service_start(services_by_key[key])
                self.assertIs(
                    self.win.workspace.current_view(),
                    self.win.workspace.service_start_view)
            self.assertEqual(self.win.top_bar.pos(), top_pos)
            self.assertEqual(self.win.explorer_placeholder.pos(), expl_pos)
            self.assertEqual(self.win.workspace.command_bar.pos(), cb_pos)
            self.assertEqual(self.win.workspace.work_tab_bar.pos(), tb_pos)
            self.assertEqual(
                self.win.workspace.work_tab_bar.count(), tabs_before)

    # ==================== P0.2 §3: محاذاة ServiceStartView ====================
    def test_service_title_pinned_right_regardless_of_latin_content(self):
        from PySide6.QtCore import Qt as _Qt
        services_by_key = {s.key: s for s in default_services()}
        self.win.open_service_start(services_by_key["cd"])          # "CD" لاتينيّ
        latin_align = self.win.workspace.service_start_view._title.alignment()
        self.win.open_service_start(services_by_key["hr_attestation_travail"])
        arabic_align = self.win.workspace.service_start_view._title.alignment()
        self.assertEqual(latin_align, arabic_align)
        self.assertTrue(latin_align & _Qt.AlignRight)

    # ==================== P0.3 §1: حدود عرض Explorer/Workspace ====================
    def test_explorer_has_min_and_max_width_guardrails(self):
        #  ‏P2.2 §3: الحدّ الأقصى صار *ديناميكياً* (min(المطلق، عرض
        #  النافذة × النسبة)) — لم يعد يساوي EXPLORER_MAX_WIDTH (المطلق)
        #  حرفياً إلا في نوافذ واسعة بما يكفي؛ يبقى سقفاً أعلى صحيحاً
        #  دائماً (راجع ExplorerDynamicMaxTest للقاعدة الدقيقة).
        from ui2.shell.main_window import EXPLORER_MAX_WIDTH, EXPLORER_MIN_WIDTH
        self.assertEqual(
            self.win.explorer_placeholder.minimumWidth(), EXPLORER_MIN_WIDTH)
        self.assertLessEqual(
            self.win.explorer_placeholder.maximumWidth(), EXPLORER_MAX_WIDTH)

    def test_dragging_splitter_far_cannot_collapse_workspace(self):
        """سحب الفاصل نحو أقصى اليمين (محاولة ابتلاع Workspace) يتوقّف
        عند حدّي Explorer الأقصى وWorkspace الأدنى معاً — لا سحقاً شبه
        صفريّ لِـWorkspace."""
        from ui2.shell.main_window import EXPLORER_MAX_WIDTH, WORKSPACE_MIN_WIDTH
        self.win.resize(1180, 720)
        self.win.show()
        self.win.splitter.moveSplitter(5000, 1)   # محاولة سحبٍ متطرّف
        self.assertLessEqual(self.win.explorer_placeholder.width(), EXPLORER_MAX_WIDTH)
        self.assertGreaterEqual(self.win.workspace.width(), WORKSPACE_MIN_WIDTH)

    def test_dragging_splitter_to_zero_respects_explorer_minimum(self):
        from ui2.shell.main_window import EXPLORER_MIN_WIDTH
        self.win.resize(1180, 720)
        self.win.show()
        self.win.splitter.moveSplitter(0, 1)
        self.assertGreaterEqual(
            self.win.explorer_placeholder.width(), EXPLORER_MIN_WIDTH)

    def test_window_stays_usable_below_natural_minimum_size(self):
        """نافذةٌ أصغر من مجموع الحدود الدنيا الطبيعيّة — Qt يرفض
        الانكماش أكثر (لا layout مكسور، لا استثناء)."""
        self.win.show()
        self.win.resize(300, 300)
        self.assertGreaterEqual(self.win.explorer_placeholder.width(), 1)
        self.assertGreaterEqual(self.win.workspace.width(), 1)

    # ==================== P0.3 §2: حدّ أقصى لِـBrand Zone ====================
    def test_brand_width_never_exceeds_max_even_with_huge_explorer(self):
        from ui2.shell.top_bar import MAX_BRAND_WIDTH
        self.win.resize(1180, 720)
        self.win.show()
        self.win.splitter.moveSplitter(5000, 1)
        self.assertLessEqual(self.win.top_bar._brand_zone.width(), MAX_BRAND_WIDTH)

    def test_brand_width_respects_min_when_explorer_shrunk(self):
        from ui2.shell.top_bar import MIN_BRAND_WIDTH
        self.win.resize(1180, 720)
        self.win.show()
        self.win.splitter.moveSplitter(0, 1)
        self.assertGreaterEqual(self.win.top_bar._brand_zone.width(), MIN_BRAND_WIDTH)

    # ==================== P0.3 §3: اتجاه WorkStatusBar البنيويّ ====================
    def test_work_status_bar_zones_in_structural_ltr_order(self):
        """ترتيب المناطق يجب أن يكون رسالة ← صفحات ← ... ← تكبير من
        اليسار لليمين في تخطيط الودجت نفسه — بصرف النظر عن RTL العامّ."""
        wsb = self.win.workspace.work_status_bar
        lay = wsb.layout()
        idx_msg = lay.indexOf(wsb.lbl_message)
        idx_prev = lay.indexOf(wsb.btn_prev_page)
        idx_fit_page = lay.indexOf(wsb.btn_fit_page)
        idx_zoom_out = lay.indexOf(wsb.btn_zoom_out)
        idx_fullscreen = lay.indexOf(wsb.btn_fullscreen)
        self.assertLess(idx_msg, idx_prev)
        self.assertLess(idx_prev, idx_fit_page)
        self.assertLess(idx_fit_page, idx_zoom_out)
        #  ترتيب التكبير نفسه: minus → slider → plus → percentage → fullscreen
        self.assertLess(lay.indexOf(wsb.btn_zoom_out), lay.indexOf(wsb.zoom_slider))
        self.assertLess(lay.indexOf(wsb.zoom_slider), lay.indexOf(wsb.btn_zoom_in))
        self.assertLess(lay.indexOf(wsb.btn_zoom_in), lay.indexOf(wsb.lbl_zoom))
        self.assertLess(lay.indexOf(wsb.lbl_zoom), idx_fullscreen)

    def test_work_status_bar_structural_direction_is_explicit_ltr(self):
        self.assertEqual(
            self.win.workspace.work_status_bar.layoutDirection(), Qt.LeftToRight)

    def test_global_rtl_does_not_flip_bottom_bar_order(self):
        original = self.app.layoutDirection()
        try:
            for direction in (Qt.LeftToRight, Qt.RightToLeft):
                self.app.setLayoutDirection(direction)
                self.assertEqual(
                    self.win.workspace.work_status_bar.layoutDirection(),
                    Qt.LeftToRight)
        finally:
            self.app.setLayoutDirection(original)

    # ==================== P0.3 §4: شريط حالة واحد فقط ====================
    def test_only_one_status_bar_visible_in_shell(self):
        """لا شريط QMainWindow.statusBar() الأصليّ مضبوطاً فعلياً على
        النافذة — Shell الجديد لا يستدعي ``setStatusBar``/``statusBar()``
        إطلاقاً (البنية الأصليّة تبقى متاحة في Qt، غير مُستخدَمة فقط)؛
        الرسالة الوحيدة الظاهرة تصل عبر WorkStatusBar داخل Workspace."""
        self.assertIsNone(self.win.findChild(QStatusBar))
        self.win.go_home()
        self.assertEqual(
            self.win.workspace.work_status_bar.lbl_message.text(), "الرئيسية")

    # ==================== P0.3 §5: بطاقات Home بلا Fixed height ====================
    def test_home_cards_do_not_use_fixed_height_size_policy(self):
        from PySide6.QtWidgets import QSizePolicy
        home = HomeView()
        for card in home._cards.values():
            self.assertNotEqual(
                card.sizePolicy().verticalPolicy(), QSizePolicy.Fixed)

    def test_home_card_grows_for_long_description(self):
        """بطاقةٌ بوصفٍ طويل عند عرضٍ ضيّق (Fixed لا Minimum كانت تقصّه) —
        ارتفاعها المحسوب عند ذلك العرض أكبر من بطاقةٍ بوصفٍ قصير لنفس
        العرض؛ إثباتٌ بنيويّ أنّ الارتفاع ينمو مع المحتوى، لا مقصوصاً."""
        short = HomeView(services=[
            ServiceDescriptor(key="x", title="خدمة", description="قصير")])
        long_ = HomeView(services=[ServiceDescriptor(
            key="x", title="خدمة", description="وصفٌ طويلٌ جداً " * 12)])
        short_card, long_card = short._cards["x"], long_._cards["x"]
        short_card.setFixedWidth(180)
        long_card.setFixedWidth(180)
        self.assertGreater(
            long_card.sizeHint().height(), short_card.sizeHint().height())

    # ==================== P1 §11: Demo Works عبر WorkspaceManager الحقيقيّ ====================
    def test_demo_tabs_not_created_in_normal_mode(self):
        self.assertEqual(self.win.workspace.work_tab_bar.count(), 0)
        self.assertEqual(self.win.workspace.workspace_manager.open_works(), [])

    def test_demo_mode_uses_real_workspace_manager(self):
        from ui2.shell.demo_tabs import DEMO_WORK_SPECS
        self.win.enable_demo_tabs()
        mgr = self.win.workspace.workspace_manager
        self.assertEqual(len(mgr.open_works()), len(DEMO_WORK_SPECS))
        self.assertEqual(self.win.workspace.work_tab_bar.count(), len(DEMO_WORK_SPECS))
        for spec in DEMO_WORK_SPECS:
            self.assertTrue(mgr.is_open(spec.key))

    def test_demo_mode_ends_on_home_without_closing_works(self):
        self.win.enable_demo_tabs()
        self.assertIs(self.win.workspace.current_view(), self.win.workspace.home_view)
        self.assertEqual(len(self.win.workspace.workspace_manager.open_works()), 3)

    def test_home_does_not_make_demo_work_look_active(self):
        self.win.enable_demo_tabs()
        # التفعيل نفسه ينتهي على Home — لا نمط Active ظاهر.
        self.assertEqual(self.win.workspace.work_tab_bar.property("workActive"), False)
        # اختيار تبويب فعلياً يفعّله... (Qt يضبط currentIndex=0 آلياً عند
        # أوّل addTab بلا إصدار currentChanged؛ tabBarClicked يحاكي نقرة
        # المستخدم الحقيقية فيُفعِّل حتى التبويب الأوّل هذا).
        self.win.workspace.work_tab_bar.tabBarClicked.emit(0)
        self.assertEqual(self.win.workspace.work_tab_bar.property("workActive"), True)
        # ...والعودة لِـHome يُخفي النمط النشِط مجدَّداً (بلا إغلاق العمل).
        self.win.go_home()
        self.assertEqual(self.win.workspace.work_tab_bar.property("workActive"), False)
        self.assertEqual(len(self.win.workspace.workspace_manager.open_works()), 3)

    def test_demo_work_activation_does_not_change_shell_geometry(self):
        self.win.resize(1180, 720)
        self.win.show()
        self.win.enable_demo_tabs()
        top_pos = self.win.top_bar.pos()
        expl_pos = self.win.explorer_placeholder.pos()
        cb_pos = self.win.workspace.command_bar.pos()
        tb_pos = self.win.workspace.work_tab_bar.pos()
        wsb_pos = self.win.workspace.work_status_bar.pos()
        win_size = self.win.size()

        mgr = self.win.workspace.workspace_manager
        self.win.workspace.work_tab_bar.setCurrentIndex(1)
        self.assertIs(self.win.workspace.current_view(), mgr.active_work().widget)
        self.assertEqual(self.win.top_bar.pos(), top_pos)
        self.assertEqual(self.win.explorer_placeholder.pos(), expl_pos)
        self.assertEqual(self.win.workspace.command_bar.pos(), cb_pos)
        self.assertEqual(self.win.workspace.work_tab_bar.pos(), tb_pos)
        self.assertEqual(self.win.workspace.work_status_bar.pos(), wsb_pos)
        self.assertEqual(self.win.size(), win_size)

    def test_demo_work_activation_marks_home_inactive(self):
        self.win.enable_demo_tabs()
        self.win.workspace.work_tab_bar.tabBarClicked.emit(0)   # نقرة حقيقية محاكاة
        self.assertFalse(self.win.top_bar.btn_home.isChecked())

    # ========= P1 §9/§13: Home→Service→Home→DemoWork→Home→DemoWork آخر =========
    def test_full_navigation_sequence_with_demo_work_no_jumping(self):
        self.win.resize(1180, 720)
        self.win.show()
        self.win.enable_demo_tabs()
        mgr = self.win.workspace.workspace_manager
        top_pos = self.win.top_bar.pos()
        expl_pos = self.win.explorer_placeholder.pos()
        cb_pos = self.win.workspace.command_bar.pos()
        tb_pos = self.win.workspace.work_tab_bar.pos()
        wsb_pos = self.win.workspace.work_status_bar.pos()

        def _assert_fixed():
            self.assertEqual(self.win.top_bar.pos(), top_pos)
            self.assertEqual(self.win.explorer_placeholder.pos(), expl_pos)
            self.assertEqual(self.win.workspace.command_bar.pos(), cb_pos)
            self.assertEqual(self.win.workspace.work_tab_bar.pos(), tb_pos)
            self.assertEqual(self.win.workspace.work_status_bar.pos(), wsb_pos)

        self.win.open_service_start(default_services()[0])
        _assert_fixed()
        self.win.go_home()
        _assert_fixed()
        self.win.workspace.work_tab_bar.tabBarClicked.emit(0)   # نقرة محاكاة
        self.assertIs(self.win.workspace.current_view(), mgr.active_work().widget)
        _assert_fixed()
        self.win.go_home()
        _assert_fixed()
        self.win.workspace.work_tab_bar.setCurrentIndex(1)
        self.assertIs(self.win.workspace.current_view(), mgr.active_work().widget)
        _assert_fixed()

    # ==================== P1 §16: ServiceStartView لا تفتح Work ====================
    def test_service_start_view_does_not_open_work(self):
        self.win.open_service_start(default_services()[0])
        self.assertEqual(self.win.workspace.workspace_manager.open_works(), [])
        self.assertEqual(self.win.workspace.work_tab_bar.count(), 0)


def _session(service_key, work_id, title=None, **kw):
    key = WorkKey(service_key, work_id)
    return WorkSession(key, title or f"{service_key}-{work_id}", QLabel(""), **kw)


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class WorkspaceManagerLogicTest(unittest.TestCase):
    """اختبارات منطقٍ خالصة (P1 §17) — لا تحتاج OfficeMainWindow الكاملة:
    WorkspaceManager هو مصدر الحقيقة عن الأعمال المفتوحة (P1 §4)."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self.mgr = WorkspaceManager()

    # -------------------------------------------------------- فتح/تكرار
    def test_open_work_adds_one_session(self):
        s = _session("paie", "918")
        self.mgr.open_work(s)
        self.assertEqual(self.mgr.open_works(), [s])
        self.assertTrue(self.mgr.is_open(s.key))

    def test_open_same_key_twice_does_not_duplicate(self):
        a1 = _session("paie", "918", title="A1")
        a2 = _session("paie", "918", title="A2")     # نفس WorkKey، جلسة أخرى
        self.mgr.open_work(a1)
        self.mgr.open_work(a2)
        self.assertEqual(len(self.mgr.open_works()), 1)
        self.assertIs(self.mgr.get(a1.key), a1)       # a1 الأصلية بقيت، لا a2
        self.assertIsNot(self.mgr.get(a1.key), a2)

    def test_duplicate_open_activates_existing(self):
        a1 = _session("paie", "918")
        other = _session("cd", "1")
        self.mgr.open_work(a1)
        self.mgr.open_work(other)
        self.assertEqual(self.mgr.active_key(), other.key)
        self.mgr.open_work(_session("paie", "918", title="a-again"))
        self.assertEqual(self.mgr.active_key(), a1.key)   # نُشِّطت a1 الأصلية

    def test_identity_does_not_depend_on_title(self):
        a = _session("paie", "918", title="عنوانٌ أوّل")
        self.mgr.open_work(a)
        a.set_title("عنوانٌ مختلفٌ كليّاً")
        self.assertTrue(self.mgr.is_open(WorkKey("paie", "918")))
        self.assertIs(self.mgr.get(WorkKey("paie", "918")), a)

    # ------------------------------------------------------------ التفعيل
    def test_activate_work_sets_active(self):
        a, b = _session("paie", "1"), _session("cd", "2")
        self.mgr.open_work(a)
        self.mgr.open_work(b)
        self.mgr.activate_work(a.key)
        self.assertIs(self.mgr.active_work(), a)

    def test_deactivate_clears_active_without_closing(self):
        a = _session("paie", "1")
        self.mgr.open_work(a)
        self.mgr.deactivate()
        self.assertIsNone(self.mgr.active_work())
        self.assertTrue(self.mgr.is_open(a.key))

    # ------------------------------------------------------------- الإغلاق
    def test_close_work_removes_only_that_work(self):
        a, b, c = _session("paie", "1"), _session("cd", "2"), _session("x", "3")
        for s in (a, b, c):
            self.mgr.open_work(s)
        self.mgr.close_work(b.key)
        self.assertFalse(self.mgr.is_open(b.key))
        self.assertTrue(self.mgr.is_open(a.key))
        self.assertTrue(self.mgr.is_open(c.key))
        self.assertEqual([s.key for s in self.mgr.open_works()], [a.key, c.key])

    def test_close_active_work_activates_neighbor(self):
        a, b, c = _session("a", "1"), _session("b", "2"), _session("c", "3")
        for s in (a, b, c):
            self.mgr.open_work(s)
        self.mgr.activate_work(b.key)
        self.mgr.close_work(b.key)
        self.assertIsNotNone(self.mgr.active_work())
        self.assertIn(self.mgr.active_key(), (a.key, c.key))

    def test_close_last_active_work_leaves_no_active_work(self):
        a = _session("paie", "1")
        self.mgr.open_work(a)
        self.mgr.close_work(a.key)
        self.assertIsNone(self.mgr.active_work())
        self.assertEqual(self.mgr.open_works(), [])

    def test_close_inactive_work_does_not_change_active(self):
        a, b = _session("paie", "1"), _session("cd", "2")
        self.mgr.open_work(a)
        self.mgr.open_work(b)
        self.mgr.activate_work(a.key)
        self.mgr.close_work(b.key)
        self.assertEqual(self.mgr.active_key(), a.key)

    # ---------------------------------------------------------- الإشارات
    def test_title_dirty_locked_changes_emit_manager_signals(self):
        a = _session("paie", "1")
        self.mgr.open_work(a)
        seen = {}
        self.mgr.titleChanged.connect(lambda k, t: seen.setdefault("title", (k, t)))
        self.mgr.dirtyChanged.connect(lambda k, d: seen.setdefault("dirty", (k, d)))
        self.mgr.lockedChanged.connect(lambda k, l: seen.setdefault("locked", (k, l)))
        a.set_title("جديد")
        a.set_dirty(True)
        a.set_locked(True)
        self.assertEqual(seen["title"], (a.key, "جديد"))
        self.assertEqual(seen["dirty"], (a.key, True))
        self.assertEqual(seen["locked"], (a.key, True))

    def test_display_text_shows_dirty_and_locked_indicators(self):
        a = _session("paie", "1", title="Bulletin Ahmed", dirty=True)
        b = _session("cd", "2", title="CD 1584", locked=True)
        c = _session("x", "3", title="Attestation Nadia")
        self.assertEqual(a.display_text(), "Bulletin Ahmed ●")
        self.assertEqual(b.display_text(), "CD 1584 🔒")
        self.assertEqual(c.display_text(), "Attestation Nadia")


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class WorkTabBarIntegrationTest(unittest.TestCase):
    """اختبارات WorkspaceHost + WorkTabBar + WorkspaceManager معاً — عرضٌ
    فعليّ لا منطقٌ مجرَّد فقط (P1 §17)."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self.win = OfficeMainWindow()
        self.win.resize(1180, 720)
        self.win.show()
        self.mgr = self.win.workspace.workspace_manager
        self.tabs = self.win.workspace.work_tab_bar

    def tearDown(self):
        self.win.deleteLater()

    def _open(self, service_key, work_id, **kw):
        s = _session(service_key, work_id, **kw)
        self.mgr.open_work(s)
        return s

    # ------------------------------------------------ ترتيب Tabs LEFT→RIGHT
    def test_three_works_appear_left_to_right_in_open_order(self):
        a, b, c = self._open("a", "1"), self._open("b", "2"), self._open("c", "3")
        xs = [self.tabs.tabRect(self.tabs.index_for_key(s.key)).x()
              for s in (a, b, c)]
        self.assertEqual(xs, sorted(xs))       # a قبل b قبل c هندسياً

    def test_global_rtl_does_not_reverse_work_tabs_order(self):
        a, b, c = self._open("a", "1"), self._open("b", "2"), self._open("c", "3")
        original = self.app.layoutDirection()
        try:
            self.app.setLayoutDirection(Qt.RightToLeft)
            xs = [self.tabs.tabRect(self.tabs.index_for_key(s.key)).x()
                  for s in (a, b, c)]
            self.assertEqual(xs, sorted(xs))
        finally:
            self.app.setLayoutDirection(original)

    def test_work_tab_bar_direction_is_explicit_ltr(self):
        self.assertEqual(self.tabs.layoutDirection(), Qt.LeftToRight)

    # --------------------------------------------------------- التفعيل/العرض
    def test_clicking_tab_activates_correct_work_and_shows_its_widget(self):
        a, b = self._open("a", "1"), self._open("b", "2")
        self.tabs.tabBarClicked.emit(self.tabs.index_for_key(a.key))
        self.assertIs(self.mgr.active_work(), a)
        self.assertIs(self.win.workspace.current_view(), a.widget)
        self.tabs.tabBarClicked.emit(self.tabs.index_for_key(b.key))
        self.assertIs(self.mgr.active_work(), b)
        self.assertIs(self.win.workspace.current_view(), b.widget)

    def test_home_does_not_close_open_works(self):
        a = self._open("a", "1")
        self.win.go_home()
        self.assertTrue(self.mgr.is_open(a.key))
        self.assertEqual(self.tabs.count(), 1)

    def test_returning_from_home_to_work_reuses_same_widget(self):
        a = self._open("a", "1")
        widget_before = a.widget
        self.win.go_home()
        self.tabs.tabBarClicked.emit(self.tabs.index_for_key(a.key))
        self.assertIs(self.win.workspace.current_view(), widget_before)
        self.assertIs(self.mgr.get(a.key).widget, widget_before)

    # ---------------------------------------------------------------- الإغلاق
    def test_closing_work_removes_correct_tab_and_widget(self):
        a, b = self._open("a", "1"), self._open("b", "2")
        idx_a = self.tabs.index_for_key(a.key)
        self.tabs.tabCloseRequested.emit(idx_a)
        self.assertFalse(self.mgr.is_open(a.key))
        self.assertTrue(self.mgr.is_open(b.key))
        self.assertEqual(self.tabs.count(), 1)
        self.assertEqual(self.tabs.index_for_key(b.key), 0)

    def test_closing_work_does_not_affect_others(self):
        a, b, c = self._open("a", "1"), self._open("b", "2"), self._open("c", "3")
        self.tabs.tabCloseRequested.emit(self.tabs.index_for_key(b.key))
        self.assertTrue(self.mgr.is_open(a.key))
        self.assertTrue(self.mgr.is_open(c.key))
        self.assertIs(self.win.workspace.content_stack.indexOf(a.widget) >= 0, True)
        self.assertIs(self.win.workspace.content_stack.indexOf(c.widget) >= 0, True)

    # ----------------------------------------------------- تحديث Tab الحيّ
    def test_title_change_updates_tab_text_immediately(self):
        a = self._open("a", "1", title="قبل")
        idx = self.tabs.index_for_key(a.key)
        a.set_title("بعد")
        self.assertEqual(self.tabs.tabText(idx), "بعد")

    def test_dirty_change_shows_dot_indicator_immediately(self):
        a = self._open("a", "1", title="عمل")
        idx = self.tabs.index_for_key(a.key)
        a.set_dirty(True)
        self.assertEqual(self.tabs.tabText(idx), "عمل ●")
        a.set_dirty(False)
        self.assertEqual(self.tabs.tabText(idx), "عمل")

    def test_locked_change_shows_lock_indicator_immediately(self):
        a = self._open("a", "1", title="عمل")
        idx = self.tabs.index_for_key(a.key)
        a.set_locked(True)
        self.assertEqual(self.tabs.tabText(idx), "عمل 🔒")

    # ================================ P2: Drag & Drop Reordering ================================
    def test_work_tab_bar_is_movable(self):
        self.assertTrue(self.tabs.isMovable())

    def test_moving_tab_updates_workspace_manager_order(self):
        a, b, c = self._open("a", "1"), self._open("b", "2"), self._open("c", "3")
        self.tabs.moveTab(self.tabs.index_for_key(c.key), 0)
        self.assertEqual([s.key for s in self.mgr.open_works()], [c.key, a.key, b.key])

    def test_active_work_unchanged_after_reorder(self):
        a, b, c = self._open("a", "1"), self._open("b", "2"), self._open("c", "3")
        self.mgr.activate_work(b.key)
        self.tabs.moveTab(self.tabs.index_for_key(c.key), 0)
        self.assertEqual(self.mgr.active_key(), b.key)

    def test_widget_and_key_unchanged_after_reorder(self):
        a = self._open("a", "1")
        widget_before, key_before = a.widget, a.key
        b = self._open("b", "2")
        self.tabs.moveTab(self.tabs.index_for_key(a.key), 1)
        self.assertIs(self.mgr.get(key_before).widget, widget_before)
        self.assertEqual(self.mgr.get(key_before).key, key_before)

    def test_dirty_locked_indicators_stay_with_correct_work_after_reorder(self):
        a = self._open("a", "1", title="A", dirty=True)
        b = self._open("b", "2", title="B", locked=True)
        self.tabs.moveTab(self.tabs.index_for_key(b.key), 0)
        self.assertEqual(self.tabs.tabText(self.tabs.index_for_key(a.key)), "A ●")
        self.assertEqual(self.tabs.tabText(self.tabs.index_for_key(b.key)), "B 🔒")

    def test_reorder_while_home_does_not_activate_work(self):
        a, b = self._open("a", "1"), self._open("b", "2")
        self.win.go_home()
        self.tabs.moveTab(self.tabs.index_for_key(b.key), 0)
        self.assertIsNone(self.mgr.active_key())
        self.assertIs(self.win.workspace.current_view(), self.win.workspace.home_view)

    def test_clicking_tab_after_reorder_opens_correct_work(self):
        a, b, c = self._open("a", "1"), self._open("b", "2"), self._open("c", "3")
        self.tabs.moveTab(self.tabs.index_for_key(c.key), 0)
        self.tabs.tabBarClicked.emit(self.tabs.index_for_key(a.key))
        self.assertIs(self.mgr.active_work(), a)
        self.assertIs(self.win.workspace.current_view(), a.widget)

    def test_closing_after_reorder_closes_correct_work(self):
        a, b, c = self._open("a", "1"), self._open("b", "2"), self._open("c", "3")
        self.tabs.moveTab(self.tabs.index_for_key(c.key), 0)   # [c, a, b]
        #  ‏فهرس 0 كان c قبل الإغلاق — الآن يمثّل c فعلياً بعد النقل، لا
        #  a التي كانت هناك قبل إعادة الترتيب.
        self.tabs.tabCloseRequested.emit(0)
        self.assertFalse(self.mgr.is_open(c.key))
        self.assertTrue(self.mgr.is_open(a.key))
        self.assertTrue(self.mgr.is_open(b.key))


def _bind(session, command_id, handler=None, enabled=True):
    session.set_command(command_id, handler or (lambda: None), enabled=enabled)


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class CommandManagerLogicTest(unittest.TestCase):
    """اختبارات CommandManager بمعزلٍ عن CommandBar/OfficeMainWindow
    الكاملة (P2 §17) — QAction واحدة لكلّ Command، حالتها تعكس العمل
    النشِط فقط في WorkspaceManager."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self.mgr = WorkspaceManager()
        self.owner = QLabel()          # ودجت مضيفة للـQActions (بديل خفيف لِـHost)
        self.cm = CommandManager(self.mgr, self.owner)

    def tearDown(self):
        self.owner.deleteLater()

    def test_one_action_per_command(self):
        from ui2.shell.commands import COMMAND_REGISTRY
        for spec in COMMAND_REGISTRY:
            self.assertIsNotNone(self.cm.action(spec.id))
        # نفس الكائن عبر استدعاءات متكرّرة — لا إنشاء مكرّر.
        self.assertIs(self.cm.action(CommandId.SAVE), self.cm.action(CommandId.SAVE))

    def test_no_active_work_hides_all_commands(self):
        for _spec, action in self.cm.actions_in_order():
            self.assertFalse(action.isVisible())
            self.assertFalse(action.isEnabled())

    def test_unsupported_command_is_hidden(self):
        a = _session("paie", "1")
        _bind(a, CommandId.SAVE, enabled=True)
        self.mgr.open_work(a)
        self.assertTrue(self.cm.action(CommandId.SAVE).isVisible())
        self.assertFalse(self.cm.action(CommandId.PRINT).isVisible())

    def test_supported_but_disabled_command_stays_visible(self):
        a = _session("cd", "1", locked=True)
        _bind(a, CommandId.SAVE, enabled=False)
        self.mgr.open_work(a)
        action = self.cm.action(CommandId.SAVE)
        self.assertTrue(action.isVisible())
        self.assertFalse(action.isEnabled())

    def test_switching_active_work_updates_actions(self):
        a, b = _session("paie", "1"), _session("cd", "2")
        _bind(a, CommandId.SAVE, enabled=True)
        _bind(b, CommandId.UNDO, enabled=False)
        self.mgr.open_work(a)
        self.mgr.open_work(b)          # b نشِط الآن
        self.assertFalse(self.cm.action(CommandId.SAVE).isVisible())
        self.assertTrue(self.cm.action(CommandId.UNDO).isVisible())
        self.mgr.activate_work(a.key)
        self.assertTrue(self.cm.action(CommandId.SAVE).isVisible())
        self.assertFalse(self.cm.action(CommandId.UNDO).isVisible())

    def test_home_disables_and_hides_work_commands(self):
        a = _session("paie", "1")
        _bind(a, CommandId.SAVE, enabled=True)
        self.mgr.open_work(a)
        self.mgr.deactivate()          # يعادل الذهاب لِـHome
        self.assertFalse(self.cm.action(CommandId.SAVE).isVisible())
        self.assertFalse(self.cm.action(CommandId.SAVE).isEnabled())

    def test_triggering_save_calls_handler_of_active_work_only(self):
        calls = []
        a = _session("paie", "1")
        b = _session("cd", "2")
        _bind(a, CommandId.SAVE, handler=lambda: calls.append("a"), enabled=True)
        _bind(b, CommandId.SAVE, handler=lambda: calls.append("b"), enabled=True)
        self.mgr.open_work(a)
        self.mgr.open_work(b)          # b نشِط
        self.cm.action(CommandId.SAVE).trigger()
        self.assertEqual(calls, ["b"])
        self.mgr.activate_work(a.key)
        self.cm.action(CommandId.SAVE).trigger()
        self.assertEqual(calls, ["b", "a"])

    def test_ctrl_s_does_not_fire_on_disabled_action(self):
        calls = []
        a = _session("cd", "1", locked=True)
        _bind(a, CommandId.SAVE, handler=lambda: calls.append("a"), enabled=False)
        self.mgr.open_work(a)
        #  حتى لو استُدعي trigger() برمجياً (يتجاوز رمادية الزرّ الفعلية)،
        #  CommandManager._trigger يعيد التحقّق من binding.is_enabled()
        #  بنفسه قبل استدعاء handler — دفاعٌ مستقلّ عن حالة QAction.
        self.cm.action(CommandId.SAVE).trigger()
        self.assertEqual(calls, [])

    def test_duplicate_open_does_not_create_new_bindings_or_actions(self):
        from ui2.shell.commands import COMMAND_REGISTRY
        a1 = _session("paie", "1")
        _bind(a1, CommandId.SAVE, enabled=True)
        self.mgr.open_work(a1)
        actions_before = {spec.id: self.cm.action(spec.id) for spec in COMMAND_REGISTRY}
        a2 = _session("paie", "1")
        _bind(a2, CommandId.SAVE, enabled=False)
        self.mgr.open_work(a2)             # نفس المفتاح — a1 تبقى النشِطة
        for spec in COMMAND_REGISTRY:
            self.assertIs(self.cm.action(spec.id), actions_before[spec.id])
        self.assertTrue(self.cm.action(CommandId.SAVE).isEnabled())   # a1، لا a2

    def test_demo_bulletin_save_clears_dirty_state(self):
        from ui2.shell.demo_tabs import DEMO_WORK_SPECS, build_demo_session
        spec = next(s for s in DEMO_WORK_SPECS if s.key.service_key == "paie")
        session = build_demo_session(spec)
        self.mgr.open_work(session)
        self.assertTrue(session.dirty)
        self.assertTrue(self.cm.action(CommandId.SAVE).isEnabled())
        self.cm.action(CommandId.SAVE).trigger()
        self.assertFalse(session.dirty)
        self.assertFalse(self.cm.action(CommandId.SAVE).isEnabled())

    def test_dirty_change_updates_save_enabled_state(self):
        a = _session("paie", "1", dirty=False)
        _bind(a, CommandId.SAVE, enabled=lambda: a.dirty)
        self.mgr.open_work(a)
        self.assertFalse(self.cm.action(CommandId.SAVE).isEnabled())
        a.set_dirty(True)
        self.assertTrue(self.cm.action(CommandId.SAVE).isEnabled())

    def test_commands_changed_hook_refreshes_actions(self):
        a = _session("paie", "1")
        flag = {"on": False}
        _bind(a, CommandId.SAVE, enabled=lambda: flag["on"])
        self.mgr.open_work(a)
        self.assertFalse(self.cm.action(CommandId.SAVE).isEnabled())
        flag["on"] = True
        a.notify_commands_changed()
        self.assertTrue(self.cm.action(CommandId.SAVE).isEnabled())

    def test_actions_in_order_matches_registry_order(self):
        from ui2.shell.commands import COMMAND_REGISTRY
        ids = [spec.id for spec, _action in self.cm.actions_in_order()]
        self.assertEqual(ids, [spec.id for spec in COMMAND_REGISTRY])


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class CommandBarIntegrationTest(unittest.TestCase):
    """CommandBar الحقيقيّ داخل Shell كاملة — ترتيب/فواصل/تبديل عمل
    نشِط وHome (P2 §17)."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self.win = OfficeMainWindow()
        self.mgr = self.win.workspace.workspace_manager
        self.cm = self.win.workspace.command_manager
        self.bar = self.win.workspace.command_bar

    def tearDown(self):
        self.win.deleteLater()

    def _visible_buttons(self):
        from PySide6.QtWidgets import QToolButton
        return [w for w in self.bar.findChildren(QToolButton)]

    def test_home_shows_no_command_buttons(self):
        self.assertEqual(self._visible_buttons(), [])

    def test_switching_works_updates_command_bar_buttons(self):
        a = _session("paie", "1")
        _bind(a, CommandId.SAVE, enabled=True)
        _bind(a, CommandId.PRINT, enabled=True)
        b = _session("cd", "2", locked=True)
        _bind(b, CommandId.PRINT, enabled=True)

        self.mgr.open_work(a)
        labels_a = sorted(btn.text() for btn in self._visible_buttons())
        self.assertEqual(labels_a, sorted(["حفظ", "طباعة"]))

        self.mgr.open_work(b)
        labels_b = sorted(btn.text() for btn in self._visible_buttons())
        self.assertEqual(labels_b, ["طباعة"])

        self.win.go_home()
        self.assertEqual(self._visible_buttons(), [])

    def test_command_bar_ordering_is_fixed_by_registry(self):
        a = _session("paie", "1")
        _bind(a, CommandId.PRINT, enabled=True)   # يُسجَّل PRINT قبل SAVE عمداً
        _bind(a, CommandId.SAVE, enabled=True)
        _bind(a, CommandId.FINALIZE, enabled=True)
        self.mgr.open_work(a)
        labels = [btn.text() for btn in self._visible_buttons()]
        self.assertEqual(labels, ["حفظ", "طباعة", "إنهاء"])   # ترتيب Registry، لا dict

    def test_no_empty_separators(self):
        from PySide6.QtWidgets import QFrame
        a = _session("paie", "1")
        _bind(a, CommandId.SAVE, enabled=True)     # FILE فقط — لا EDIT ولا WORKFLOW
        self.mgr.open_work(a)
        separators = [w for w in self.bar.findChildren(QFrame)
                      if w.frameShape() == QFrame.VLine]
        self.assertEqual(len(separators), 0)

    def test_separator_appears_between_two_non_empty_groups(self):
        from PySide6.QtWidgets import QFrame
        a = _session("paie", "1")
        _bind(a, CommandId.SAVE, enabled=True)     # FILE
        _bind(a, CommandId.UNDO, enabled=True)     # EDIT
        self.mgr.open_work(a)
        separators = [w for w in self.bar.findChildren(QFrame)
                      if w.frameShape() == QFrame.VLine]
        self.assertEqual(len(separators), 1)

    # ==================== P2.1 §9/§10/§11: أيقونات + tooltip + shortcut ====================
    def test_command_bar_uses_same_qactions_as_command_manager(self):
        a = _session("paie", "1")
        _bind(a, CommandId.SAVE, enabled=True)
        self.mgr.open_work(a)
        from PySide6.QtWidgets import QToolButton
        btn = self._visible_buttons()[0]
        self.assertIs(btn.defaultAction(), self.cm.action(CommandId.SAVE))

    def test_tooltip_contains_shortcut_from_registry(self):
        from ui2.shell.commands import COMMAND_REGISTRY
        for spec in COMMAND_REGISTRY:
            action = self.cm.action(spec.id)
            if spec.shortcut:
                self.assertIn(spec.shortcut, action.toolTip())
            else:
                self.assertNotIn("(", action.toolTip())

    def test_disabled_action_shows_disabled_in_bar(self):
        a = _session("cd", "1", locked=True)
        _bind(a, CommandId.SAVE, enabled=False)
        self.mgr.open_work(a)
        btn = self._visible_buttons()[0]
        self.assertFalse(btn.isEnabled())

    def test_unsupported_action_not_in_bar(self):
        a = _session("paie", "1")
        _bind(a, CommandId.SAVE, enabled=True)     # PRINT غير مدعوم
        self.mgr.open_work(a)
        labels = [btn.text() for btn in self._visible_buttons()]
        self.assertNotIn("طباعة", labels)


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class WorkTabUXTest(unittest.TestCase):
    """اختبارات P2.1: عرضٌ موحَّد + ellipsis/tooltip + overflow + All
    Open Works menu + Close/Close Others/Close All."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self.win = OfficeMainWindow()
        self.win.resize(900, 700)
        self.win.show()
        self.mgr = self.win.workspace.workspace_manager
        self.tabs = self.win.workspace.work_tab_bar

    def tearDown(self):
        self.win.deleteLater()

    def _open(self, service_key, work_id, **kw):
        s = _session(service_key, work_id, **kw)
        self.mgr.open_work(s)
        return s

    # -------------------------------------------------------- عرضٌ موحَّد
    def test_all_tabs_have_uniform_width(self):
        from ui2.shell.workspace import WORK_TAB_WIDTH
        a = self._open("a", "1", title="قصير")
        b = self._open("b", "2", title="عنوانٌ طويلٌ جداً جداً جداً للاختبار")
        self.assertEqual(self.tabs.tabSizeHint(self.tabs.index_for_key(a.key)).width(),
                          WORK_TAB_WIDTH)
        self.assertEqual(self.tabs.tabSizeHint(self.tabs.index_for_key(b.key)).width(),
                          WORK_TAB_WIDTH)

    def test_long_title_does_not_widen_tab(self):
        from ui2.shell.workspace import WORK_TAB_WIDTH
        a = self._open("a", "1", title="ع" * 60)
        self.assertEqual(self.tabs.tabRect(self.tabs.index_for_key(a.key)).width(),
                          WORK_TAB_WIDTH)

    def test_tooltip_contains_full_title(self):
        a = self._open("a", "1", title="Bulletin BENALI Karim OCTOBRE 2026")
        idx = self.tabs.index_for_key(a.key)
        self.assertIn("Bulletin BENALI Karim OCTOBRE 2026", self.tabs.tabToolTip(idx))

    def test_tooltip_updates_with_dirty_locked(self):
        a = self._open("a", "1", title="عمل")
        idx = self.tabs.index_for_key(a.key)
        a.set_dirty(True)
        self.assertIn("عمل", self.tabs.tabToolTip(idx))
        self.assertIn("محفوظة", self.tabs.tabToolTip(idx))
        a.set_locked(True)
        self.assertIn("مقفل", self.tabs.tabToolTip(idx))

    # -------------------------------------------------------- Active/Inactive
    def test_active_inactive_property_toggles_correctly(self):
        a, b = self._open("a", "1"), self._open("b", "2")
        self.tabs.tabBarClicked.emit(self.tabs.index_for_key(a.key))
        self.assertEqual(self.tabs.property("workActive"), True)
        self.win.go_home()
        self.assertEqual(self.tabs.property("workActive"), False)

    # -------------------------------------------------------------- LTR/DnD
    def test_ltr_still_enforced(self):
        self.assertEqual(self.tabs.layoutDirection(), Qt.LeftToRight)

    def test_movable_still_enabled(self):
        self.assertTrue(self.tabs.isMovable())

    def test_reorder_reflected_in_all_open_works_menu(self):
        a, b, c = self._open("a", "1"), self._open("b", "2"), self._open("c", "3")
        self.tabs.moveTab(self.tabs.index_for_key(c.key), 0)
        menu = self.win.workspace._build_all_works_menu()
        titles = [act.text() for act in menu.actions()
                  if act.isCheckable()]
        self.assertEqual(titles, [c.display_text(), a.display_text(), b.display_text()])

    # ------------------------------------------------------------ Overflow
    def test_scroll_buttons_enabled_for_overflow(self):
        self.assertTrue(self.tabs.usesScrollButtons())
        for i in range(15):
            self._open("x", str(i), title=f"عمل رقم {i}")
        from ui2.shell.workspace import WORK_TAB_WIDTH
        self.assertGreater(15 * WORK_TAB_WIDTH, self.tabs.width())
        # كلّ تبويب يبقى بعرضه الموحَّد رغم الكثرة — لا سحقٌ للعرض.
        for i in range(15):
            idx = self.tabs.index_for_key(WorkKey("x", str(i)))
            self.assertEqual(self.tabs.tabRect(idx).width(), WORK_TAB_WIDTH)

    # ------------------------------------------- All Open Works menu (P2.1 §6)
    def test_all_open_works_menu_lists_all_in_order(self):
        a, b, c = self._open("a", "1"), self._open("b", "2"), self._open("c", "3")
        menu = self.win.workspace._build_all_works_menu()
        entries = [act.text() for act in menu.actions() if act.isCheckable()]
        self.assertEqual(entries, [a.display_text(), b.display_text(), c.display_text()])

    def test_all_open_works_menu_checks_active_work(self):
        a, b = self._open("a", "1"), self._open("b", "2")
        self.mgr.activate_work(a.key)
        menu = self.win.workspace._build_all_works_menu()
        checked = {act.text(): act.isChecked() for act in menu.actions() if act.isCheckable()}
        self.assertTrue(checked[a.display_text()])
        self.assertFalse(checked[b.display_text()])

    def test_selecting_menu_entry_activates_correct_work(self):
        a, b = self._open("a", "1"), self._open("b", "2")
        menu = self.win.workspace._build_all_works_menu()
        entry_a = next(act for act in menu.actions() if act.text() == a.display_text())
        entry_a.trigger()
        self.assertEqual(self.mgr.active_key(), a.key)

    def test_menu_uses_workkey_not_tab_index(self):
        a, b, c = self._open("a", "1"), self._open("b", "2"), self._open("c", "3")
        self.tabs.moveTab(self.tabs.index_for_key(c.key), 0)   # [c, a, b]
        menu = self.win.workspace._build_all_works_menu()
        entry_b = next(act for act in menu.actions() if act.text() == b.display_text())
        entry_b.trigger()
        self.assertEqual(self.mgr.active_key(), b.key)   # لا index 1 (a بعد النقل)

    # ------------------------------------------- Close / Close Others / Close All
    def test_close_active_action_closes_correct_work(self):
        a, b = self._open("a", "1"), self._open("b", "2")
        self.mgr.activate_work(a.key)
        menu = self.win.workspace._build_all_works_menu()
        act_close = next(act for act in menu.actions() if act.text() == "إغلاق العمل النشِط")
        act_close.trigger()
        self.assertFalse(self.mgr.is_open(a.key))
        self.assertTrue(self.mgr.is_open(b.key))

    def test_close_others_excludes_selected(self):
        a, b, c = self._open("a", "1"), self._open("b", "2"), self._open("c", "3")
        self.mgr.activate_work(b.key)
        menu = self.win.workspace._build_all_works_menu()
        act = next(act for act in menu.actions() if act.text() == "إغلاق البقية")
        act.trigger()
        self.assertTrue(self.mgr.is_open(b.key))
        self.assertFalse(self.mgr.is_open(a.key))
        self.assertFalse(self.mgr.is_open(c.key))
        self.assertEqual(self.mgr.active_key(), b.key)

    def test_close_all_closes_everything(self):
        self._open("a", "1"), self._open("b", "2"), self._open("c", "3")
        menu = self.win.workspace._build_all_works_menu()
        act = next(act for act in menu.actions() if act.text() == "إغلاق الكلّ")
        act.trigger()
        self.assertEqual(self.mgr.open_works(), [])
        self.assertIsNone(self.mgr.active_key())

    def test_context_menu_close_others_signal(self):
        a, b = self._open("a", "1"), self._open("b", "2")
        self.tabs.closeOthersRequested.emit(a.key)
        self.assertTrue(self.mgr.is_open(a.key))
        self.assertFalse(self.mgr.is_open(b.key))

    def test_context_menu_close_all_signal(self):
        self._open("a", "1"), self._open("b", "2")
        self.tabs.closeAllRequested.emit()
        self.assertEqual(self.mgr.open_works(), [])

    # -------------------------------------------------------- Home behaviour
    def test_home_shows_no_active_work_but_keeps_menu_entries(self):
        self._open("a", "1")
        self.win.go_home()
        self.assertEqual(self.tabs.property("workActive"), False)
        menu = self.win.workspace._build_all_works_menu()
        self.assertEqual(len([a for a in menu.actions() if a.isCheckable()]), 1)


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class SearchSlotTest(unittest.TestCase):
    """‏P2.1 §13: مكانٌ بصريّ محجوز فقط — بلا منطق."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self.win = OfficeMainWindow()

    def tearDown(self):
        self.win.deleteLater()

    def test_search_box_exists_in_top_bar(self):
        from PySide6.QtWidgets import QLineEdit
        self.assertIsInstance(self.win.top_bar.search_box, QLineEdit)

    def test_search_box_has_no_wired_logic(self):
        #  لا receivers على textChanged/returnPressed — placeholder بحت.
        from PySide6.QtCore import SIGNAL
        box = self.win.top_bar.search_box
        self.assertEqual(box.receivers(SIGNAL("returnPressed()")), 0)
        self.assertEqual(box.receivers(SIGNAL("textChanged(QString)")), 0)

    # ==================== P2.2 §11: غير قابل للتحرير حالياً ====================
    def test_search_box_is_read_only_and_not_focusable(self):
        box = self.win.top_bar.search_box
        self.assertTrue(box.isReadOnly())
        self.assertEqual(box.focusPolicy(), Qt.NoFocus)

    def test_typing_into_search_box_does_not_change_text(self):
        from PySide6.QtTest import QTest
        box = self.win.top_bar.search_box
        box.setFocusPolicy(Qt.StrongFocus)   # مؤقّتاً لإيصال الكتابة فعلياً لهذا الاختبار
        box.setFocus()
        before = box.text()
        QTest.keyClicks(box, "abc")   # read-only يمنع أيّ إدراج فعليّ من لوحة المفاتيح
        self.assertEqual(box.text(), before)
        box.setFocusPolicy(Qt.NoFocus)


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class ShellMetricsCentralizationTest(unittest.TestCase):
    """‏P2.2 §1: القيَم البنيوية تأتي من ``ui2.shell.metrics`` فعلياً —
    لا نسخة محلية مختلفة مبعثرة في كلّ ملف."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def test_top_bar_reexports_match_metrics(self):
        from ui2.shell import metrics, top_bar
        self.assertEqual(top_bar.MIN_BRAND_WIDTH, metrics.BRAND_MIN_WIDTH)
        self.assertEqual(top_bar.MAX_BRAND_WIDTH, metrics.BRAND_MAX_WIDTH)
        self.assertEqual(top_bar.HEIGHT, metrics.TOP_BAR_HEIGHT)

    def test_main_window_reexports_match_metrics(self):
        from ui2.shell import main_window, metrics
        self.assertEqual(main_window.EXPLORER_MIN_WIDTH, metrics.EXPLORER_MIN_WIDTH)
        self.assertEqual(main_window.EXPLORER_MAX_WIDTH, metrics.EXPLORER_ABSOLUTE_MAX_WIDTH)
        self.assertEqual(main_window.WORKSPACE_MIN_WIDTH, metrics.WORKSPACE_MIN_WIDTH)

    def test_workspace_reexports_match_metrics(self):
        from ui2.shell import metrics, workspace
        self.assertEqual(workspace.WORK_TAB_WIDTH, metrics.WORK_TAB_WIDTH)
        self.assertEqual(workspace.WORK_TAB_BAR_HEIGHT, metrics.WORK_TAB_HEIGHT)

    def test_work_status_bar_reexports_match_metrics(self):
        from ui2.shell import metrics, work_status_bar
        self.assertEqual(work_status_bar.HEIGHT, metrics.WORK_STATUS_BAR_HEIGHT)


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class WindowAndExplorerResponsiveTest(unittest.TestCase):
    """‏P2.2 §2/§3/§4: حدّ أدنى للنافذة + حدّ أقصى ديناميكيّ لِـExplorer."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self.win = OfficeMainWindow()

    def tearDown(self):
        self.win.deleteLater()

    def test_window_minimum_size_matches_metrics(self):
        from ui2.shell import metrics
        self.assertEqual(self.win.minimumWidth(), metrics.WINDOW_MIN_WIDTH)
        self.assertEqual(self.win.minimumHeight(), metrics.WINDOW_MIN_HEIGHT)

    def test_explorer_effective_max_never_exceeds_absolute_max(self):
        from ui2.shell import metrics
        self.win.resize(3000, 900)
        self.win.show()
        self.assertLessEqual(
            self.win.explorer_placeholder.maximumWidth(),
            metrics.EXPLORER_ABSOLUTE_MAX_WIDTH)

    def test_explorer_effective_max_follows_ratio_on_narrow_window(self):
        from ui2.shell import metrics
        self.win.resize(metrics.WINDOW_MIN_WIDTH, 700)
        self.win.show()
        expected = max(
            metrics.EXPLORER_MIN_WIDTH,
            min(metrics.EXPLORER_ABSOLUTE_MAX_WIDTH,
                int(self.win.width() * metrics.EXPLORER_MAX_RATIO)),
        )
        self.assertEqual(self.win.explorer_placeholder.maximumWidth(), expected)

    def test_workspace_never_collapses_below_minimum(self):
        from ui2.shell import metrics
        self.win.resize(metrics.WINDOW_MIN_WIDTH, 700)
        self.win.show()
        self.assertGreaterEqual(self.win.workspace.width(), 1)
        self.win.splitter.moveSplitter(5000, 1)
        self.assertGreaterEqual(self.win.workspace.width(), metrics.WORKSPACE_MIN_WIDTH - 5)

    def test_user_chosen_explorer_width_preserved_within_new_bounds(self):
        """توسيع النافذة ثمّ تضييقها قليلاً لا يُعيد ضبط عرض Explorer
        الذي اختاره المستخدم ما دام لا يزال صالحاً (P2.2 §3: بلا
        resize متقلقل)."""
        self.win.resize(1600, 800)
        self.win.show()
        self.win.splitter.setSizes([300, 1200])
        self.win.resize(1400, 800)
        self.assertEqual(self.win.splitter.sizes()[0], 300)

    def test_brand_width_still_clamped_via_metrics(self):
        from ui2.shell import metrics
        self.win.resize(1600, 800)
        self.win.show()
        self.win.splitter.moveSplitter(5000, 1)
        self.assertLessEqual(self.win.top_bar._brand_zone.width(), metrics.BRAND_MAX_WIDTH)


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class HomeResponsiveGridTest(unittest.TestCase):
    """‏P2.2 §6/§7/§8/§18: أعمدة Home، توحيد البطاقات، تمرير عموديّ،
    وتفعيل لوحة المفاتيح."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def _cols_for_width(self, width: int) -> int:
        home = HomeView()
        home.resize(width, 600)
        home.show()
        return home._cols

    def test_wide_width_uses_three_columns(self):
        from ui2.shell import metrics
        self.assertEqual(self._cols_for_width(metrics.BREAKPOINT_WIDE + 200), 3)

    def test_medium_width_uses_two_columns(self):
        from ui2.shell import metrics
        mid = (metrics.BREAKPOINT_MEDIUM + metrics.BREAKPOINT_WIDE) // 2
        self.assertEqual(self._cols_for_width(mid), 2)

    def test_compact_width_uses_one_column(self):
        from ui2.shell import metrics
        self.assertEqual(self._cols_for_width(metrics.BREAKPOINT_MEDIUM - 100), 1)

    def test_cards_share_same_minimum_sizing_metrics(self):
        home = HomeView()
        from ui2.shell import metrics
        for card in home._cards.values():
            self.assertEqual(card.minimumWidth(), metrics.SERVICE_CARD_MIN_WIDTH)
            self.assertEqual(card.minimumHeight(), metrics.SERVICE_CARD_MIN_HEIGHT)

    def test_long_description_does_not_clip_short_card(self):
        short = HomeView(services=[
            ServiceDescriptor(key="x", title="خدمة", description="قصير")])
        long_ = HomeView(services=[ServiceDescriptor(
            key="x", title="خدمة", description="وصفٌ طويلٌ جداً " * 12)])
        short_card, long_card = short._cards["x"], long_._cards["x"]
        short_card.setFixedWidth(180)
        long_card.setFixedWidth(180)
        self.assertGreaterEqual(
            long_card.sizeHint().height(), short_card.sizeHint().height())

    def test_home_content_is_inside_scroll_area(self):
        from PySide6.QtWidgets import QScrollArea
        home = HomeView()
        self.assertTrue(home.findChildren(QScrollArea))

    def test_service_card_keyboard_activation(self):
        home = HomeView()
        card = next(iter(home._cards.values()))
        received = []
        card.clicked.connect(received.append)
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent
        event = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
        card.keyPressEvent(event)
        self.assertEqual(received, [card.service.key])

    def test_service_card_accepts_focus(self):
        home = HomeView()
        card = next(iter(home._cards.values()))
        self.assertNotEqual(card.focusPolicy(), Qt.NoFocus)


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class WorkStatusBarPriorityTest(unittest.TestCase):
    """‏P2.2 §15/§16: الرسالة تتنازل، Pages/Zoom لا يُدفَعان خارج الشاشة."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self.win = OfficeMainWindow()

    def tearDown(self):
        self.win.deleteLater()

    def test_zoom_controls_stay_visible_at_minimum_window(self):
        from ui2.shell import metrics
        self.win.resize(metrics.WINDOW_MIN_WIDTH, metrics.WINDOW_MIN_HEIGHT)
        self.win.show()
        wsb = self.win.workspace.work_status_bar
        self.assertTrue(wsb.btn_zoom_in.isVisible())
        self.assertTrue(wsb.zoom_slider.isVisible())
        self.assertTrue(wsb.lbl_zoom.isVisible())
        self.assertLessEqual(wsb.btn_fullscreen.geometry().right(), wsb.width())

    def test_long_status_message_gets_elided(self):
        #  ‏WorkStatusBar مستقلّة (بلا أب مُدار بتخطيط) كي يبقى resize()
        #  اليدويّ فعلياً — داخل WorkspaceHost الحيّة يتحكّم التخطيط
        #  الأب بعرضها الفعليّ بصرف النظر عن أيّ resize() مباشر عليها.
        from ui2.shell.work_status_bar import WorkStatusBar
        wsb = WorkStatusBar()
        wsb.resize(300, 30)
        wsb.show()
        self.app.processEvents()
        long_text = "رسالة طويلة جداً جداً جداً " * 10
        wsb.set_message(long_text)
        self.assertNotEqual(wsb.lbl_message.text(), long_text)
        self.assertIn("…", wsb.lbl_message.text())
        wsb.deleteLater()

    def test_full_message_available_via_tooltip(self):
        from ui2.shell.work_status_bar import WorkStatusBar
        wsb = WorkStatusBar()
        wsb.resize(200, 30)
        wsb.show()
        self.app.processEvents()
        long_text = "رسالة طويلة جداً جداً جداً " * 10
        wsb.set_message(long_text)
        self.assertEqual(wsb.lbl_message.toolTip(), long_text)
        wsb.deleteLater()

    def test_bottom_bar_structural_order_preserved(self):
        wsb = self.win.workspace.work_status_bar
        lay = wsb.layout()
        self.assertLess(lay.indexOf(wsb.lbl_message), lay.indexOf(wsb.btn_prev_page))
        self.assertLess(lay.indexOf(wsb.btn_prev_page), lay.indexOf(wsb.btn_fit_page))
        self.assertLess(lay.indexOf(wsb.btn_fit_page), lay.indexOf(wsb.btn_zoom_out))


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class WorkTabsAtVariousSizesTest(unittest.TestCase):
    """‏P2.2 §12/§13: Work Tabs/All-Works button تبقى سليمة على full/
    medium/minimum window — لا تكسير لمنطق P2.1."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self.win = OfficeMainWindow()

    def tearDown(self):
        self.win.deleteLater()

    def _check_at(self, width, height):
        from ui2.shell import metrics
        self.win.resize(width, height)
        self.win.show()
        self.win.enable_demo_many_tabs(12)
        tabs = self.win.workspace.work_tab_bar
        for i in range(tabs.count()):
            self.assertEqual(tabs.tabRect(i).width(), metrics.WORK_TAB_WIDTH)
        self.assertTrue(self.win.workspace.btn_all_works.isVisible())
        self.assertGreater(self.win.workspace.btn_all_works.width(), 0)

    def test_tabs_stable_at_full_width(self):
        self._check_at(1920, 1080)

    def test_tabs_stable_at_medium_width(self):
        self._check_at(1100, 700)

    def test_tabs_stable_at_minimum_width(self):
        from ui2.shell import metrics
        self._check_at(metrics.WINDOW_MIN_WIDTH, metrics.WINDOW_MIN_HEIGHT)


if __name__ == "__main__":
    unittest.main()
