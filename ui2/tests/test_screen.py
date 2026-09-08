"""اختبارات :class:`ui2.screen.Screen` — القاعدة التي سترث منها شاشات
HR و CD. تغطّي دورة حياة الاختصارات، تتبّع التغييرات غير المحفوظة،
وحفظ/استرجاع المسوّدة مع رقم الإصدار.

التشغيل:
    python -m unittest discover -s ui2/tests
"""
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shutil
import tempfile
import unittest

try:
    from PySide6.QtWidgets import QApplication, QLabel
    _HAS_QT = True
except Exception:                                    # noqa: BLE001
    _HAS_QT = False

if _HAS_QT:
    from programme import paths
    from ui2 import theme
    from ui2.screen import Screen

    class _FakeScreen(Screen):
        TITLE = "وهمية"
        DRAFT_NAME = "faketest"
        DRAFT_VERSION = 2

        def __init__(self, parent=None):
            super().__init__(parent)
            self.payload = {"x": "1"}
            self.empty = False
            self.applied = None
            self.closed = 0
            self.build_ui()

        def build_body(self):
            return QLabel("body")

        def shortcuts(self):
            return {"Ctrl+S": lambda: None, "Ctrl+W": lambda: None}

        def draft_state(self):
            return dict(self.payload)

        def apply_draft(self, data):
            self.applied = data

        def is_empty(self):
            return self.empty

        def on_close(self):
            self.closed += 1


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class ScreenBaseTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="om_screen_")
        os.environ[paths._LOCAL_STATE_ENV_OVERRIDE] = self._tmp
        self.scr = _FakeScreen()

    def tearDown(self):
        os.environ.pop(paths._LOCAL_STATE_ENV_OVERRIDE, None)
        self.scr.deleteLater()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _draft_file(self):
        return os.path.join(self._tmp, "faketest_draft.json")

    # ---------------------------------------------- التغييرات غير المحفوظة
    def test_dirty_tracking_independent_of_is_empty(self):
        self.assertFalse(self.scr.has_unsaved_changes())
        self.scr.empty = True                     # «فارغة» للمسوّدة
        self.scr.mark_dirty()
        # فارغة لكن فيها تغيير معلّق → has_unsaved_changes مستقلّ عن is_empty
        self.assertTrue(self.scr.has_unsaved_changes())
        self.scr.mark_clean()
        self.assertFalse(self.scr.has_unsaved_changes())

    # ------------------------------------------------------ حفظ/قراءة المسوّدة
    def test_draft_roundtrip(self):
        self.scr.payload = {"header": {"nom": "طه"}, "lines": []}
        self.scr.flush_draft()                     # كتابة فورية
        self.assertTrue(os.path.exists(self._draft_file()))
        with open(self._draft_file(), encoding="utf-8") as fh:
            blob = json.load(fh)
        self.assertEqual(blob["draft_version"], 2)
        self.assertEqual(blob["state"], {"header": {"nom": "طه"}, "lines": []})
        self.assertEqual(self.scr.load_draft(),
                         {"header": {"nom": "طه"}, "lines": []})

    def test_is_empty_clears_instead_of_writing(self):
        self.scr.flush_draft()
        self.assertTrue(os.path.exists(self._draft_file()))
        self.scr.empty = True
        self.scr.flush_draft()
        self.assertFalse(os.path.exists(self._draft_file()))

    def test_version_mismatch_ignored_silently_and_removed(self):
        with open(self._draft_file(), "w", encoding="utf-8") as fh:
            json.dump({"draft_version": 1, "state": {"old": "shape"}}, fh)
        self.assertIsNone(self.scr.load_draft())            # إصدار مختلف
        self.assertFalse(os.path.exists(self._draft_file()))  # يُمسَح

    def test_corrupt_draft_ignored_and_removed(self):
        with open(self._draft_file(), "w", encoding="utf-8") as fh:
            fh.write("{ليس JSON صالح")
        self.assertIsNone(self.scr.load_draft())
        self.assertFalse(os.path.exists(self._draft_file()))

    def test_maybe_restore_draft_apply_and_decline(self):
        self.scr.payload = {"v": "keep"}
        self.scr.flush_draft()
        # يوافق → apply_draft يُستدعى
        restored = self.scr.maybe_restore_draft(ask=lambda: True)
        self.assertTrue(restored)
        self.assertEqual(self.scr.applied, {"v": "keep"})
        self.assertTrue(self.scr.has_unsaved_changes())

        # مسوّدة جديدة ثم رفض → تُمسَح ولا تُطبَّق
        self.scr.applied = None
        self.scr.mark_clean()
        self.scr.payload = {"v": "drop"}
        self.scr.flush_draft()
        self.assertFalse(self.scr.maybe_restore_draft(ask=lambda: False))
        self.assertIsNone(self.scr.applied)
        self.assertFalse(os.path.exists(self._draft_file()))

    def test_no_draft_name_no_file(self):
        class _NoDraft(_FakeScreen):
            DRAFT_NAME = ""
        s = _NoDraft()
        s.mark_dirty()
        s.flush_draft()
        self.assertEqual(os.listdir(self._tmp), [])
        s.deleteLater()

    # ------------------------------------------------ دورة حياة الاختصارات
    def test_shortcut_lifecycle(self):
        self.assertIsNone(self.scr._sc)
        self.scr.on_activate()
        self.assertEqual(len(self.scr._sc), 2)             # Ctrl+S + Ctrl+W
        self.scr.on_activate()                             # idempotent
        self.assertEqual(len(self.scr._sc), 2)
        self.scr.on_deactivate()
        self.assertIsNone(self.scr._sc)

    def test_close_screen_calls_on_close_before_deactivate(self):
        self.scr.on_activate()
        self.scr.close_screen()
        self.assertEqual(self.scr.closed, 1)
        self.assertIsNone(self.scr._sc)                    # on_deactivate جرى

    # -------------------------------------------------------- سياق الزبون
    def test_set_company_emits_signal(self):
        seen = []
        self.scr.companySelected.connect(seen.append)
        self.scr.set_company(7)
        self.assertEqual(seen, [7])
        self.assertEqual(self.scr.client_id, 7)


if __name__ == "__main__":
    unittest.main()
