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
        from ui2.shell.main_window import EXPLORER_MAX_WIDTH, EXPLORER_MIN_WIDTH
        self.assertEqual(
            self.win.explorer_placeholder.minimumWidth(), EXPLORER_MIN_WIDTH)
        self.assertEqual(
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


if __name__ == "__main__":
    unittest.main()
