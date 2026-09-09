"""اختبار تثبيت لشاشة كشف الراتب PySide6 (``ui2/hr/paie/bulletin_template.py``).

المبدأ: المحرّك (``programme.payroll``) لا يُلمَس؛ الشاشة موصِّلٌ أمين —
نموذج الصفوف الديناميكيّ (Phase A2) → ``entries`` → ``lignes.compute_bulletin``
→ ``BulletinView``؛ ونتيجة المُصيِّر تُشتقّ منها.

التشغيل:
    QT_QPA_PLATFORM=offscreen python -m unittest discover -s ui2/hr/paie/tests
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from datetime import date

try:
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    _HAS_QT = True
except Exception:                                    # noqa: BLE001
    _HAS_QT = False

if _HAS_QT:
    from programme import paths
    from programme.payroll import calc
    from programme.payroll.config_loader import load_params
    import ui2.hr.paie.bulletin_template as mod
    from ui2 import theme
    from ui2.hr.paie.bulletin_template import BulletinTemplateScreen

_HEADER = {
    "emp_raison_sociale": "SARL DATA NEWS", "emp_cnas": "16 412 078 56",
    "mois": "OCTOBRE", "annee": "2026",
    "id_nom": "BENALI", "id_prenom": "Karim", "id_matricule": "MAT-2024-0087",
}


def _expected_input():
    return calc.PaieInput(
        mois="OCTOBRE", annee="2026", jours=30.0, salaire_base=45000.0,
        panier=3000.0, transport=2500.0,
        primes=[calc.Prime(code="LIBRE", libelle="PRIME DE RENDEMENT",
                           montant=8000.0, soumis_cotisation=True, imposable=True)],
        autres_retenues=[])


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class BulletinTemplatePin(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="om_tpl_")
        os.environ[paths._LOCAL_STATE_ENV_OVERRIDE] = self._tmp
        mod.confirm = lambda *_a, **_k: True
        self.scr = BulletinTemplateScreen(conn=None)

    def tearDown(self):
        self.scr.deleteLater()
        os.environ.pop(paths._LOCAL_STATE_ENV_OVERRIDE, None)

    # ---- أدوات ----
    def _row(self, kind, occurrence=-1):
        rs = [r for r in self.scr._rows if r.kind == kind]
        return rs[occurrence] if rs else None

    def _set(self, kind, **cells):
        r = self._row(kind)
        for c, val in cells.items():
            r.widgets[c].setText(str(val))
        return r

    def _fill(self):
        for k, v in _HEADER.items():
            self.scr._widgets[k].setText(v)
        self._set("salaire", gain="45000")
        self._set("panier", gain="3000")
        self._set("transport", gain="2500")
        pr = self._set("prime", libelle="PRIME DE RENDEMENT", gain="8000")
        self.scr._recompute()
        return pr

    # ================= الصفوف الافتراضية =================
    def test_default_row_sequence(self):
        self.assertEqual([r.kind for r in self.scr._visible_body_rows()],
                         ["salaire", "prime", "panier", "transport", "cnas", "irg"])

    def test_one_default_prime(self):
        self.assertEqual(len([r for r in self.scr._rows if r.kind == "prime"]), 1)

    def test_panier_transport_permanent_and_zero_ok(self):
        for kind in ("panier", "transport"):
            r = self._row(kind)
            self.assertFalse(r.can_delete())          # أساسي — لا يُحذف
            self.assertEqual(r.val("gain"), "")       # 0 صالح، ليس incomplete
        self._fill()                                  # مع أجر قاعديّ
        self._set("panier", gain="0")
        self._set("transport", gain="0")
        self.scr._recompute()
        self.assertTrue(self.scr._computed)           # 0 لا يكسر الحساب

    def test_system_rows_not_editable(self):
        for kind in ("cnas", "irg"):
            r = self._row(kind)
            self.assertEqual(r.role, "system")
            self.assertEqual(r.widgets, {})           # لا widgets ⇒ لا Tab stop
        nav = self.scr._nav_order
        self.assertFalse(any(k.startswith("r%d_" % self._row("cnas").rid)
                             for k in nav))

    def test_paints_without_exception(self):
        self._fill()
        self.scr._add_row("avance")
        self.scr._relayout()
        img = QImage(900, 1400, QImage.Format_ARGB32)
        self.scr._canvas.resize(900, 1400)
        self.scr._canvas.render(img)

    # ================= المحرّك / النتيجة =================
    def test_mapping_is_faithful_conduit(self):
        self._fill()
        cfg = load_params(date(2026, 10, 1))
        exp = calc.compute(_expected_input(), cfg)
        got = self.scr._calc_result
        for f in ("net_a_payer", "total_gain", "total_retenue",
                  "base_cnas", "retenue_cnas", "base_irg", "retenue_irg"):
            self.assertEqual(getattr(got, f), getattr(exp, f), f"{f} انحرف")

    def test_engine_view_is_source(self):
        self._fill()
        v, r = self.scr._bulletin_view, self.scr._calc_result
        self.assertIsNotNone(v)
        self.assertEqual((v.a, v.b, v.c, v.d, v.e),
                         (r.base_cnas, r.retenue_cnas, r.base_irg,
                          r.retenue_irg, r.net_a_payer))

    def test_prime_soumis_toggle_changes_base(self):
        self._fill()
        base0 = self.scr._calc_result.base_cnas
        self.scr._set_prime_soumis(False)
        self.assertLess(self.scr._calc_result.base_cnas, base0)

    def test_not_computable_without_base_salary(self):
        self.assertFalse(self.scr._computed)          # يفتح فارغاً
        self._fill()
        self.assertTrue(self.scr._computed)
        self._set("salaire", gain="")
        self.scr._recompute()
        self.assertFalse(self.scr._computed)

    # ================= + Ajouter / حذف / ترتيب =================
    def test_add_optional_row_deterministic_order(self):
        self.scr._add_row("avance")
        self.scr._add_row("autre")
        kinds = [r.kind for r in self.scr._visible_body_rows()]
        # avance/autre بعد CNAS/IRG (§13)
        self.assertLess(kinds.index("cnas"), kinds.index("avance"))
        self.assertLess(kinds.index("irg"), kinds.index("avance"))
        self.assertLess(kinds.index("avance"), kinds.index("autre"))

    def test_geometry_moves_with_row_count(self):
        n0 = self.scr._net_y_mm()
        self.scr._add_row("prime")
        self.assertGreater(self.scr._net_y_mm(), n0)   # NET ينزل مع الصفوف
        r = self._row("prime", -1)
        self.scr._remove_row(r)
        self.assertAlmostEqual(self.scr._net_y_mm(), n0, places=3)

    def test_remove_leaves_no_dead_widgets(self):
        self.scr._add_row("avance")
        r = self._row("avance", -1)
        keys = [r.cell_key(c) for c in r.widgets]
        self.scr._remove_row(r)
        for k in keys:
            self.assertNotIn(k, self.scr._widgets)
            self.assertNotIn(k, self.scr._nav_order)

    def test_filled_optional_row_delete_is_guarded(self):
        r = self.scr._add_row("avance") or self._row("avance", -1)
        r = self._row("avance", -1)
        r.widgets["retenue"].setText("5000")
        mod.confirm = lambda *_a, **_k: False        # المستخدم يرفض
        self.scr._remove_row(r)
        self.assertIn(r, self.scr._rows)             # لم يُحذف
        mod.confirm = lambda *_a, **_k: True

    def test_basic_rows_cannot_be_removed(self):
        for kind in ("salaire", "panier", "transport"):
            r = self._row(kind)
            self.scr._remove_row(r)
            self.assertIn(r, self.scr._rows)

    def test_two_prime_rows(self):
        self._fill()
        self.scr._add_row("prime")
        self._row("prime", -1).widgets["libelle"].setText("PRIME DE RISQUE")
        self._row("prime", -1).widgets["gain"].setText("6000")
        self.scr._recompute()
        libs = [l.libelle for l in self.scr._bulletin_view.lignes]
        self.assertIn("PRIME DE RENDEMENT", libs)
        self.assertIn("PRIME DE RISQUE", libs)

    def test_avance_and_autre_are_z4_retenues(self):
        self._fill()
        net0 = self.scr._calc_result.net_a_payer
        self.scr._add_row("avance")
        self._row("avance", -1).widgets["retenue"].setText("10000")
        self.scr._recompute()
        self.assertEqual(self.scr._calc_result.net_a_payer, net0 - 10000)

    # ================= مسح / مسوّدة =================
    def test_clear_resets_to_defaults(self):
        self._fill()
        self.scr._add_row("avance")
        self.scr._on_clear()
        self.assertEqual([r.kind for r in self.scr._visible_body_rows()],
                         ["salaire", "prime", "panier", "transport", "cnas", "irg"])
        self.assertFalse(self.scr._employee_fullname())

    def test_draft_roundtrip_with_dynamic_rows(self):
        self._fill()
        self.scr._add_row("avance")
        self._row("avance", -1).widgets["retenue"].setText("7000")
        st = self.scr.draft_state()
        other = BulletinTemplateScreen(conn=None)
        other.apply_draft(st)
        self.assertEqual(other._widgets["id_nom"].text(), "BENALI")
        self.assertEqual(other._row("salaire").val("gain") if hasattr(other, "_row")
                         else [r for r in other._rows if r.kind == "salaire"][0].val("gain"),
                         "45000")
        self.assertTrue(any(r.kind == "avance" and r.val("retenue") == "7000"
                            for r in other._rows))
        other.deleteLater()


if __name__ == "__main__":
    unittest.main()
