"""اختبارات الإدخال الذكي المشترك (Phase 55) — دوال ``ui2.form`` النقيّة
+ :class:`GroupedNumberEdit` + إكمال مقاطع :class:`DateField`.

المبدأ المُختبَر: «مكتمل حين لا امتداد أطول صالح» — لا ``length == N``.

التشغيل:
    QT_QPA_PLATFORM=offscreen python -m unittest discover -s ui2/tests
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
    from ui2 import form as F

_MOIS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
         "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class SmartInputPrimitives(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    # ---------------- day / month-num completion ----------------
    def test_day_complete(self):
        for d in ("4", "5", "6", "7", "8", "9", "01", "31"):
            self.assertTrue(F.day_complete(d), d)
        for d in ("1", "2", "3", ""):
            self.assertFalse(F.day_complete(d), d)

    def test_month_num_complete(self):
        for m in ("2", "3", "9", "01", "12"):
            self.assertTrue(F.month_num_complete(m), m)
        for m in ("1", ""):
            self.assertFalse(F.month_num_complete(m), m)

    # ---------------- resolve_month ----------------
    def test_month_numeric(self):
        self.assertEqual(F.resolve_month("9", _MOIS), (8, True))     # Septembre
        self.assertEqual(F.resolve_month("2", _MOIS), (1, True))     # Février
        self.assertEqual(F.resolve_month("1", _MOIS), (None, False))  # ملتبس
        self.assertEqual(F.resolve_month("10", _MOIS), (9, True))
        self.assertEqual(F.resolve_month("12", _MOIS), (11, True))
        self.assertEqual(F.resolve_month("13", _MOIS), (None, False))

    def test_month_prefix_ambiguity(self):
        for amb in ("j", "ju", "a", "m", "ma"):
            self.assertEqual(F.resolve_month(amb, _MOIS), (None, False), amb)
        self.assertEqual(F.resolve_month("jun", _MOIS), (5, True))    # Juin
        self.assertEqual(F.resolve_month("jui", _MOIS), (6, True))    # Juillet
        self.assertEqual(F.resolve_month("av", _MOIS), (3, True))     # Avril
        self.assertEqual(F.resolve_month("ao", _MOIS), (7, True))     # Août
        self.assertEqual(F.resolve_month("mar", _MOIS), (2, True))
        self.assertEqual(F.resolve_month("mai", _MOIS), (4, True))
        self.assertEqual(F.resolve_month("s", _MOIS), (8, True))      # وحيد → Septembre

    def test_month_case_and_accents(self):
        self.assertEqual(F.resolve_month("SEP", _MOIS), (8, True))
        self.assertEqual(F.resolve_month("Sep", _MOIS), (8, True))
        self.assertEqual(F.resolve_month("déc", _MOIS), (11, True))
        self.assertEqual(F.resolve_month("dec", _MOIS), (11, True))
        self.assertEqual(F.resolve_month("aoû", _MOIS), (7, True))
        self.assertEqual(F.resolve_month("aou", _MOIS), (7, True))
        self.assertEqual(F.resolve_month("fév", _MOIS), (1, True))
        self.assertEqual(F.resolve_month("fev", _MOIS), (1, True))

    # ---------------- group_digits ----------------
    def test_group_digits(self):
        self.assertEqual(F.group_digits("1234567890", [2, 3, 3, 2]),
                         "12 345 678 90")
        self.assertEqual(F.group_digits("1234", [2, 3, 3, 2]), "12 34")
        self.assertEqual(F.group_digits("12ab34", [2, 2, 4], "/"), "12/34")
        self.assertEqual(F.group_digits("", [2, 2, 4]), "")

    # ---------------- GroupedNumberEdit ----------------
    def test_grouped_edit_typing_and_complete(self):
        seen = []
        g = F.GroupedNumberEdit([2, 3, 3, 2])
        g.completed.connect(lambda: seen.append(True))
        g.setText("123456789")
        g._reformat("")
        self.assertEqual(g.text(), "12 345 678 9")
        self.assertFalse(g.is_complete())
        g.setText("1234567890")
        g._reformat("")
        self.assertEqual(g.text(), "12 345 678 90")
        self.assertEqual(g.value(), "1234567890")
        self.assertTrue(g.is_complete())
        self.assertTrue(seen)

    def test_grouped_edit_paste_raw_and_formatted(self):
        for raw in ("1234567890", "12 345 678 90", "12-345-678-90"):
            g = F.GroupedNumberEdit([2, 3, 3, 2])
            from PySide6.QtCore import QMimeData
            md = QMimeData()
            md.setText(raw)
            g.insertFromMimeData(md)
            self.assertEqual(g.value(), "1234567890", raw)
            self.assertEqual(g.text(), "12 345 678 90", raw)

    def test_grouped_edit_letters_ignored(self):
        g = F.GroupedNumberEdit([2, 3, 3, 2])
        g.setText("1a2b3c")
        g._reformat("")
        self.assertEqual(g.value(), "123")

    # ---------------- N° SS: مفتاح «/XX» اختياري ----------------
    def test_ssn_without_key(self):
        g = F.GroupedNumberEdit([2, 4, 4, 2], key_sep="/")
        g.setText("185030512345")
        g._reformat("")
        self.assertEqual(g.text(), "18 5030 5123 45")
        self.assertTrue(g.is_complete())

    def test_ssn_with_key_separator(self):
        g = F.GroupedNumberEdit([2, 4, 4, 2], key_sep="/")
        g.setText("1850305123/45")
        g._reformat("")
        self.assertEqual(g.text(), "18 5030 5123 /45")
        self.assertEqual(g.value(), "1850305123/45")
        self.assertTrue(g.is_complete())

    def test_ssn_paste_both_forms(self):
        for raw, disp in (("185030512345", "18 5030 5123 45"),
                          ("18 5030 5123 /45", "18 5030 5123 /45"),
                          ("1850305123/45", "18 5030 5123 /45")):
            g = F.GroupedNumberEdit([2, 4, 4, 2], key_sep="/")
            from PySide6.QtCore import QMimeData
            md = QMimeData(); md.setText(raw)
            g.insertFromMimeData(md)
            self.assertEqual(g.text(), disp, raw)

    def test_ssn_letters_rejected(self):
        import re
        g = F.GroupedNumberEdit([2, 4, 4, 2], key_sep="/")
        g.setText("18ab5030")
        g._reformat("")
        self.assertEqual(re.sub(r"\D", "", g.text()), "185030")

    # ---------------- DateField smart day-pad + completed ----------------
    def test_datefield_day_pad(self):
        d = F.DateField("dd/MM/yyyy")
        d._edit.setText("9")
        d._on_text_edited("")
        self.assertEqual(d._edit.text(), "09")          # 9 لا امتداد → 09
        d2 = F.DateField("dd/MM/yyyy")
        d2._edit.setText("1")
        d2._on_text_edited("")
        self.assertEqual(d2._edit.text(), "1")           # 1 قد يمتدّ → ينتظر

    def test_datefield_completed_signal(self):
        d = F.DateField("dd/MM/yyyy")
        fired = []
        d.completed.connect(lambda: fired.append(True))
        for ch in "15061990":
            d._edit.setText(d._edit.text() + ch)
            d._edit.setCursorPosition(len(d._edit.text()))
            d._on_text_edited("")
        self.assertEqual(d.iso(), "1990-06-15")
        self.assertTrue(fired)


if __name__ == "__main__":
    unittest.main()
