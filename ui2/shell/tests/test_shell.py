"""اختبارات بنية Shell (Prototype) — معمارية لا شكل بصري.

التشغيل:
    python -m unittest discover -s ui2/shell/tests
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
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
        self.assertEqual(self.win.top_bar.layoutDirection(), Qt.RightToLeft)

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


if __name__ == "__main__":
    unittest.main()
