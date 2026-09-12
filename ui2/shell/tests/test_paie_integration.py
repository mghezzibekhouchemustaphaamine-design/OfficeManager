"""اختبارات P3 Phase 1 — استضافة BulletinTemplateScreen داخل Shell.

    QT_QPA_PLATFORM=offscreen python -m unittest discover -s ui2/shell/tests

يعزل قاعدة البيانات/المسوّدات في مجلّدٍ مؤقّت لكلّ اختبار (نفس نمط
``ui2/hr/paie/tests/test_bulletin_template.py::_isolate_db``) — لا كتابة
على بيانات المستخدم الحقيقية."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shutil
import tempfile
import unittest

try:
    from PySide6.QtWidgets import QApplication
    _HAS_QT = True
except Exception:                                    # noqa: BLE001
    _HAS_QT = False

if _HAS_QT:
    from programme import database, paths
    from ui2 import theme
    from ui2.hr.paie.bulletin_template import BulletinTemplateScreen
    from ui2.shell.close_controller import CloseCoordinator
    from ui2.shell.close_types import CloseDecision, SaveResult
    from ui2.shell.commands import CommandId
    from ui2.shell.integrations import paie as paie_integration
    from ui2.shell.integrations.paie import PaieWorkAdapter, SERVICE_KEY
    from ui2.shell.main_window import OfficeMainWindow
    from ui2.shell.work import WorkKey
    from ui2.shell.workspace_manager import WorkspaceManager


def _isolate_db(tmp):
    os.environ[paths._DATA_DIR_ENV_OVERRIDE] = tmp
    os.environ[paths._LOCAL_STATE_ENV_OVERRIDE] = tmp
    open(os.path.join(tmp, "office_system.db"), "a").close()
    database.init_db()


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class PaieWorkAdapterTest(unittest.TestCase):
    """‏P3 §22: Adapter بمعزلٍ عن Shell الكاملة."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="om_p3_")
        _isolate_db(self._tmp)
        #  ‏_on_save يعرض QMessageBox.warning حقيقية (حاجبة) حين يُرفَض
        #  الحفظ (مثلاً عملٌ 🔒) — نُعطِّلها هنا (نفس نمط اختبارات Paie
        #  الأصلية لِـ_al.warn) كي لا تُعلَّق الاختبارات.
        import ui2.alerts as _al
        self._al, self._al_warn = _al, _al.warn
        _al.warn = lambda *_a, **_k: None

    def tearDown(self):
        self._al.warn = self._al_warn
        os.environ.pop(paths._DATA_DIR_ENV_OVERRIDE, None)
        os.environ.pop(paths._LOCAL_STATE_ENV_OVERRIDE, None)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_creates_real_bulletin_template_screen(self):
        session = PaieWorkAdapter.create_new()
        self.assertIsInstance(session.widget, BulletinTemplateScreen)

    def test_creates_unique_work_key_per_call(self):
        a = PaieWorkAdapter.create_new()
        b = PaieWorkAdapter.create_new()
        self.assertNotEqual(a.key, b.key)
        self.assertEqual(a.key.service_key, SERVICE_KEY)
        self.assertEqual(b.key.service_key, SERVICE_KEY)

    def test_widget_is_same_screen_instance_as_adapter(self):
        session = PaieWorkAdapter.create_new()
        adapter = session.widget._work_adapter
        self.assertIs(adapter.screen, session.widget)
        self.assertIs(adapter.session, session)

    def test_save_command_calls_real_paie_save(self):
        session = PaieWorkAdapter.create_new()
        screen = session.widget
        screen._widgets["emp_raison_sociale"].setText("SARL X")
        screen._widgets["mois"].setText("OCTOBRE")
        screen._widgets["annee"].setText("2026")
        self.assertTrue(session.dirty)
        result = session.save()
        self.assertEqual(result, SaveResult.SUCCESS)
        self.assertIsNotNone(screen._work_id)   # كُتب فعلياً في hr_documents

    def test_successful_save_clears_dirty(self):
        session = PaieWorkAdapter.create_new()
        session.widget.mark_dirty()
        self.assertTrue(session.dirty)
        session.save()
        self.assertFalse(session.dirty)

    def test_failed_save_keeps_dirty(self):
        """‏P3 §10/§22: محاكاة فشل — عملٌ 🔒 يرفضه ``_on_save`` نفسه
        (False من التعديل الصغير المُضاف)، فيبقى dirty ولا يُغلَق."""
        session = PaieWorkAdapter.create_new()
        session.widget.mark_dirty()
        session.widget._set_locked(True)
        result = session.save()
        self.assertEqual(result, SaveResult.FAILED)
        self.assertTrue(session.dirty)

    def test_dirty_state_propagates_from_paie_to_worksession(self):
        session = PaieWorkAdapter.create_new()
        self.assertFalse(session.dirty)
        session.widget.mark_dirty()
        self.assertTrue(session.dirty)
        session.widget.mark_clean()
        self.assertFalse(session.dirty)

    def test_locked_state_propagates_from_paie_to_worksession(self):
        session = PaieWorkAdapter.create_new()
        self.assertFalse(session.locked)
        session.widget._set_locked(True)
        self.assertTrue(session.locked)
        session.widget._set_locked(False)
        self.assertFalse(session.locked)

    def test_can_save_false_when_locked(self):
        session = PaieWorkAdapter.create_new()
        session.widget.mark_dirty()
        self.assertTrue(session.can_save())
        session.widget._set_locked(True)
        self.assertFalse(session.can_save())

    def test_print_command_supported_but_not_triggered_in_test(self):
        """‏PRINT مربوطة فعلياً (P3 §12) — لا نُنفِّذها هنا: ``_on_preview``
        الحقيقية تفتح ``QMessageBox.warning`` حاجبة إن لم توجد نسخة
        نهائية بعد؛ الاختبار يتحقّق من الربط فقط (نفس تحفّظ P2.1/P2.5
        من استدعاء handlers تفتح Dialogs حقيقية)."""
        session = PaieWorkAdapter.create_new()
        binding = session.command_binding(CommandId.PRINT)
        self.assertIsNotNone(binding)
        self.assertTrue(binding.is_enabled())

    def test_finalize_not_bound_in_phase1(self):
        session = PaieWorkAdapter.create_new()
        self.assertIsNone(session.command_binding(CommandId.FINALIZE))

    def test_no_shell_imports_inside_paie_module(self):
        """‏P3 §2/§28: bulletin_template.py يبقى مستقلاًّ عن Shell."""
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "hr", "paie", "bulletin_template.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        for forbidden in ("ui2.shell", "WorkspaceManager", "OfficeMainWindow",
                          "WorkTabBar", "CommandManager", "CloseCoordinator"):
            self.assertNotIn(forbidden, src)


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class PaieShellIntegrationTest(unittest.TestCase):
    """‏P3 §23: المسار الكامل Home→خدمة→Nouveau→Work Tab حقيقيّة."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)
        paie_integration.register()

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="om_p3_shell_")
        _isolate_db(self._tmp)
        import ui2.alerts as _al
        self._al, self._al_warn = _al, _al.warn
        _al.warn = lambda *_a, **_k: None
        self.win = OfficeMainWindow()

    def tearDown(self):
        self._al.warn = self._al_warn
        self.win.deleteLater()
        os.environ.pop(paths._DATA_DIR_ENV_OVERRIDE, None)
        os.environ.pop(paths._LOCAL_STATE_ENV_OVERRIDE, None)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _open_paie_service_start(self):
        service = next(s for s in self.win.workspace.home_view.services()
                       if s.key == SERVICE_KEY)
        self.win.open_service_start(service)
        return service

    def test_nouveau_opens_real_work_tab(self):
        self._open_paie_service_start()
        mgr = self.win.workspace.workspace_manager
        self.assertEqual(mgr.open_works(), [])
        self.win.workspace.service_start_view.btn_nouveau.click()
        works = mgr.open_works()
        self.assertEqual(len(works), 1)
        self.assertEqual(works[0].key.service_key, SERVICE_KEY)
        self.assertIsInstance(works[0].widget, BulletinTemplateScreen)

    def test_work_tab_title_is_correct(self):
        self._open_paie_service_start()
        self.win.workspace.service_start_view.btn_nouveau.click()
        session = self.win.workspace.workspace_manager.active_work()
        self.assertEqual(session.title, "Bulletin de paie — Nouveau")

    def test_nouveau_twice_creates_two_different_works(self):
        self._open_paie_service_start()
        btn = self.win.workspace.service_start_view.btn_nouveau
        btn.click()
        first = self.win.workspace.workspace_manager.active_key()
        btn.click()
        second = self.win.workspace.workspace_manager.active_key()
        self.assertNotEqual(first, second)
        self.assertEqual(len(self.win.workspace.workspace_manager.open_works()), 2)

    def test_home_does_not_destroy_paie_work(self):
        self._open_paie_service_start()
        self.win.workspace.service_start_view.btn_nouveau.click()
        key = self.win.workspace.workspace_manager.active_key()
        widget_before = self.win.workspace.workspace_manager.get(key).widget
        self.win.go_home()
        self.assertTrue(self.win.workspace.workspace_manager.is_open(key))
        self.assertIs(self.win.workspace.workspace_manager.get(key).widget, widget_before)

    def test_returning_to_tab_reuses_same_screen_instance(self):
        self._open_paie_service_start()
        self.win.workspace.service_start_view.btn_nouveau.click()
        key = self.win.workspace.workspace_manager.active_key()
        widget_before = self.win.workspace.workspace_manager.get(key).widget
        self.win.go_home()
        self.win.workspace.work_tab_bar.tabBarClicked.emit(
            self.win.workspace.work_tab_bar.index_for_key(key))
        self.assertIs(self.win.workspace.current_view(), widget_before)

    def test_editing_paie_field_makes_tab_dirty(self):
        self._open_paie_service_start()
        self.win.workspace.service_start_view.btn_nouveau.click()
        key = self.win.workspace.workspace_manager.active_key()
        session = self.win.workspace.workspace_manager.get(key)
        self.assertFalse(session.dirty)
        session.widget._widgets["emp_raison_sociale"].setText("SARL TEST")
        session.widget.mark_dirty()
        self.assertTrue(session.dirty)
        idx = self.win.workspace.work_tab_bar.index_for_key(key)
        self.assertIn("●", self.win.workspace.work_tab_bar.tabText(idx))

    def test_save_command_removes_dirty(self):
        self._open_paie_service_start()
        self.win.workspace.service_start_view.btn_nouveau.click()
        key = self.win.workspace.workspace_manager.active_key()
        session = self.win.workspace.workspace_manager.get(key)
        session.widget._widgets["mois"].setText("OCTOBRE")
        session.widget.mark_dirty()
        self.win.workspace.command_manager.action(CommandId.SAVE).trigger()
        self.assertFalse(session.dirty)

    def test_dirty_close_cancel_keeps_work(self):
        self._open_paie_service_start()
        self.win.workspace.service_start_view.btn_nouveau.click()
        key = self.win.workspace.workspace_manager.active_key()
        session = self.win.workspace.workspace_manager.get(key)
        session.widget.mark_dirty()
        self.win.workspace.close_coordinator = CloseCoordinator(
            self.win.workspace.workspace_manager, self.win,
            decision_provider=lambda s: CloseDecision.CANCEL,
        )
        idx = self.win.workspace.work_tab_bar.index_for_key(key)
        self.win.workspace.work_tab_bar.tabCloseRequested.emit(idx)
        self.assertTrue(self.win.workspace.workspace_manager.is_open(key))

    def test_dirty_close_save_saves_and_closes(self):
        self._open_paie_service_start()
        self.win.workspace.service_start_view.btn_nouveau.click()
        key = self.win.workspace.workspace_manager.active_key()
        session = self.win.workspace.workspace_manager.get(key)
        session.widget._widgets["mois"].setText("OCTOBRE")
        session.widget.mark_dirty()
        self.win.workspace.close_coordinator = CloseCoordinator(
            self.win.workspace.workspace_manager, self.win,
            decision_provider=lambda s: CloseDecision.SAVE,
        )
        idx = self.win.workspace.work_tab_bar.index_for_key(key)
        self.win.workspace.work_tab_bar.tabCloseRequested.emit(idx)
        self.assertFalse(self.win.workspace.workspace_manager.is_open(key))

    def test_clean_close_closes_directly_no_dialog(self):
        self._open_paie_service_start()
        self.win.workspace.service_start_view.btn_nouveau.click()
        key = self.win.workspace.workspace_manager.active_key()
        called = {"n": 0}
        self.win.workspace.close_coordinator = CloseCoordinator(
            self.win.workspace.workspace_manager, self.win,
            decision_provider=lambda s: called.__setitem__("n", called["n"] + 1),
        )
        idx = self.win.workspace.work_tab_bar.index_for_key(key)
        self.win.workspace.work_tab_bar.tabCloseRequested.emit(idx)
        self.assertFalse(self.win.workspace.workspace_manager.is_open(key))
        self.assertEqual(called["n"], 0)

    def test_other_services_remain_placeholders(self):
        service = next(s for s in self.win.workspace.home_view.services()
                       if s.key == "cd")
        self.assertIsNone(service.new_work_factory)

    def test_ctrl_s_action_routes_to_paie_save_once(self):
        """‏P3 §17/§24: مسار QAction SAVE يصل حفظ Paie الحقيقيّ مرّةً
        واحدة فقط — Ctrl+S فعليّ عبر OS غير قابل للاختبار في offscreen
        (نفس القيد الموثَّق في P2)، لكن مسار QAction هو ما يستقبله
        Ctrl+S فعلياً في بيئة حقيقية، ونفس QAction تماماً تستعملها
        CommandBar."""
        self._open_paie_service_start()
        self.win.workspace.service_start_view.btn_nouveau.click()
        key = self.win.workspace.workspace_manager.active_key()
        session = self.win.workspace.workspace_manager.get(key)
        session.widget.mark_dirty()
        calls = []
        real_save = session.widget._on_save
        session.widget._on_save = lambda: (calls.append(1), real_save())[1]
        self.win.workspace.command_manager.action(CommandId.SAVE).trigger()
        self.assertEqual(calls, [1])   # مرّةً واحدة فقط


if __name__ == "__main__":
    unittest.main()
