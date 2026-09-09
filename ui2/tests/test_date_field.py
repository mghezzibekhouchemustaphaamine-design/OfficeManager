"""اختبارات :class:`ui2.form.DateField` — الحقل الموحّد للتواريخ.

يغطّي: الحالات الأربع، تطبيع الفواصل، اللصق، ISO مقابل العرض،
التاريخ المستقبلي، وقاعدة ``date_naissance < date_entree``.

التشغيل:
    QT_QPA_PLATFORM=offscreen python -m unittest discover -s ui2/tests
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from datetime import date, timedelta

try:
    from PySide6.QtWidgets import QApplication
    _HAS_QT = True
except Exception:                                    # noqa: BLE001
    _HAS_QT = False

if _HAS_QT:
    from ui2.form import DateField, _DateEdit


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class DateFieldTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _f(self, **kw):
        w = DateField(display_format="dd/MM/yyyy", **kw)
        return w

    def _type(self, w, raw):
        w._edit.setText(raw)
        w._on_text_edited("")

    # ---------------- الحالات الأربع ----------------
    def test_empty_is_neutral(self):
        w = self._f()
        self.assertEqual(w.state(), DateField.NEUTRAL)
        self.assertEqual(w.iso(), "")

    def test_partial_is_incomplete(self):
        w = self._f()
        self._type(w, "1506")
        self.assertEqual(w.state(), DateField.INCOMPLETE)
        self.assertEqual(w.iso(), "")

    def test_full_valid(self):
        w = self._f()
        self._type(w, "15061990")
        self.assertEqual(w._edit.text(), "15/06/1990")
        self.assertEqual(w.state(), DateField.VALID)
        self.assertEqual(w.iso(), "1990-06-15")

    def test_impossible_is_error(self):
        w = self._f()
        self._type(w, "31021990")
        self.assertEqual(w.state(), DateField.ERROR)
        self.assertEqual(w.iso(), "")
        self.assertTrue(w.error_text())

    def test_letters_ignored_silently(self):
        w = self._f()
        self._type(w, "1a5b0c6d1990")
        self.assertEqual(w._edit.text(), "15/06/1990")

    # ---------------- تطبيع الفواصل ----------------
    def test_separator_normalization(self):
        for raw in ("15-06-1990", "15.06.1990", "15 06 1990", "15/06/1990"):
            w = self._f()
            self._type(w, raw)
            self.assertEqual(w._edit.text(), "15/06/1990", raw)
            self.assertEqual(w.iso(), "1990-06-15", raw)

    # ---------------- اللصق ----------------
    def test_paste_valid_any_separator_normalized(self):
        for txt in ("1990-06-15", "15/06/1990", "15-06-1990", "15.06.1990"):
            w = self._f()
            self.assertTrue(w._try_paste(txt), txt)
            self.assertEqual(w.iso(), "1990-06-15", txt)

    def test_paste_invalid_rejected(self):
        w = self._f()
        self.assertFalse(w._try_paste("bonjour"))
        self.assertFalse(w._try_paste("99/99/9999"))
        self.assertEqual(w.iso(), "")

    # ---------------- Ctrl+A / Delete ----------------
    def test_select_all_then_delete_clears(self):
        w = self._f()
        self._type(w, "15061990")
        w._edit.selectAll()
        w._edit.del_()
        w._on_text_edited("")
        self.assertEqual(w._edit.text(), "")
        self.assertEqual(w.state(), DateField.NEUTRAL)

    # ---------------- iso() / set_iso() و فصل العرض عن التخزين ----------------
    def test_set_iso_accepts_iso_only(self):
        w = self._f()
        w.set_iso("13/01/2016")                       # ليست ISO
        self.assertEqual(w.iso(), "")
        w.set_iso("2016-01-13")
        self.assertEqual(w.iso(), "2016-01-13")

    def test_display_vs_storage_separation(self):
        w = self._f()                                 # عرض dd/MM/yyyy
        w.set_iso("1990-06-15")
        self.assertEqual(w._edit.text(), "15/06/1990")   # العرض
        self.assertEqual(w.iso(), "1990-06-15")           # التخزين
        w2 = DateField(display_format="yyyy-MM-dd")
        w2.set_iso("1990-06-15")
        self.assertEqual(w2._edit.text(), "1990-06-15")
        self.assertEqual(w2.iso(), "1990-06-15")

    def test_month_kind(self):
        m = DateField(display_format="yyyy-MM")
        self._type(m, "202609")
        self.assertEqual(m._edit.text(), "2026-09")
        self.assertEqual(m.iso(), "2026-09")

    def test_alias_is_same_class(self):
        self.assertIs(_DateEdit, DateField)

    # ---------------- تاريخ مستقبلي ----------------
    def test_future_date_blocked_when_max_today(self):
        w = self._f(max_date=date.today())
        future = date.today() + timedelta(days=2)
        self._type(w, future.strftime("%d%m%Y"))
        self.assertEqual(w.state(), DateField.ERROR)
        self.assertEqual(w.iso(), "")

    def test_today_is_allowed_when_max_today(self):
        w = self._f(max_date=date.today())
        self._type(w, date.today().strftime("%d%m%Y"))
        self.assertEqual(w.state(), DateField.VALID)

    # ---------------- naissance < entree ----------------
    def test_entree_must_be_after_naissance(self):
        naissance = self._f(max_date=date.today())
        entree = self._f(max_date=date.today())

        def check(d):
            iso = naissance.iso()
            if iso and d <= date.fromisoformat(iso):
                return "بعد الميلاد"
            return None

        entree.set_extra_check(check)
        naissance.set_iso("1990-06-15")
        entree.set_iso("1990-06-15")                  # مساوٍ → خطأ
        self.assertEqual(entree.state(), DateField.ERROR)
        entree.set_iso("2015-09-01")                  # بعده → صالح
        self.assertEqual(entree.state(), DateField.VALID)

    def test_changing_naissance_revalidates_entree(self):
        naissance = self._f(max_date=date.today())
        entree = self._f(max_date=date.today())
        entree.set_extra_check(
            lambda d: "بعد الميلاد" if (naissance.iso()
                      and d <= date.fromisoformat(naissance.iso())) else None)
        naissance.set_iso("1990-01-01")
        entree.set_iso("1995-01-01")
        self.assertEqual(entree.state(), DateField.VALID)
        naissance.set_iso("2000-01-01")              # صار بعد الدخول
        entree.revalidate()
        self.assertEqual(entree.state(), DateField.ERROR)


if __name__ == "__main__":
    unittest.main()
