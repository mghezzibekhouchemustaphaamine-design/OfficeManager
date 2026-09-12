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
    from ui2 import theme
    from ui2.shell.home import HomeView, ServiceCard
    from ui2.shell.main_window import OfficeMainWindow
    from ui2.shell.services import ServiceDescriptor, default_services
    from ui2.shell.workspace import ServiceStartView, WorkTabBar


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

    # ==================== P0.3 §6: Demo Work Tabs (معزولة) ====================
    def test_demo_tabs_not_created_in_normal_mode(self):
        self.assertEqual(self.win.workspace.work_tab_bar.count(), 0)

    def test_demo_tabs_appear_only_after_explicit_enable(self):
        from ui2.shell.demo_tabs import DEMO_WORK_TABS
        self.win.enable_demo_tabs()
        self.assertEqual(self.win.workspace.work_tab_bar.count(), len(DEMO_WORK_TABS))

    def test_home_does_not_make_demo_work_look_active(self):
        self.win.enable_demo_tabs()
        # التفعيل نفسه يبدأ على Home — لا نمط Active ظاهر.
        self.assertEqual(self.win.workspace.work_tab_bar.property("workActive"), False)
        # اختيار تبويب فعلياً يفعّله... (Qt يضبط currentIndex=0 آلياً عند
        # أوّل addTab بلا إصدار currentChanged؛ tabBarClicked يحاكي نقرة
        # المستخدم الحقيقية فيُفعِّل حتى التبويب الأوّل هذا).
        self.win.workspace.work_tab_bar.tabBarClicked.emit(0)
        self.assertEqual(self.win.workspace.work_tab_bar.property("workActive"), True)
        # ...والعودة لِـHome يُخفي النمط النشِط مجدَّداً.
        self.win.go_home()
        self.assertEqual(self.win.workspace.work_tab_bar.property("workActive"), False)

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

        self.win.workspace.work_tab_bar.setCurrentIndex(1)
        self.assertIs(
            self.win.workspace.current_view(), self.win.workspace.demo_work_view)
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

    # ========= P0.3 §9: Home→Service→Home→DemoWork→Home→DemoWork آخر =========
    def test_full_navigation_sequence_with_demo_work_no_jumping(self):
        self.win.resize(1180, 720)
        self.win.show()
        self.win.enable_demo_tabs()
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
        self.assertIs(
            self.win.workspace.current_view(), self.win.workspace.demo_work_view)
        _assert_fixed()
        self.win.go_home()
        _assert_fixed()
        self.win.workspace.work_tab_bar.setCurrentIndex(1)
        self.assertIs(
            self.win.workspace.current_view(), self.win.workspace.demo_work_view)
        _assert_fixed()


if __name__ == "__main__":
    unittest.main()
