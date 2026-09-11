"""اختبارات بنية Shell (Prototype) — معمارية لا شكل بصري.

التشغيل:
    python -m unittest discover -s ui2/shell/tests
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

try:
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


if __name__ == "__main__":
    unittest.main()
