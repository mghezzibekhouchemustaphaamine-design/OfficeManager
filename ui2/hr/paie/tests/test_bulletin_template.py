"""اختبار تثبيت لشاشة كشف الراتب PySide6 (``ui2/hr/paie/bulletin_template.py``).

نموذج الصفوف الديناميكيّ (Phase A2/A2.3) → ``entries`` →
``lignes.compute_bulletin`` → ``BulletinView``؛ نتيجة المُصيِّر تُشتقّ منها.
المحرّك لا يُلمَس.

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
    from ui2.hr.paie.bulletin_template import BulletinTemplateScreen
    from ui2 import theme

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
    def _row(self, kind, occ=-1):
        rs = [r for r in self.scr._rows if r.kind == kind]
        return rs[occ] if rs else None

    def _set(self, kind, **cells):
        r = self._row(kind)
        for c, val in cells.items():
            r.set_val(c, val)
        return r

    def _add(self, kind, **cells):
        self.scr._add_row(kind)
        r = self._row(kind, -1)
        for c, val in cells.items():
            r.set_val(c, val)
        self.scr._recompute()
        return r

    def _fill(self):
        for k, v in _HEADER.items():
            self.scr._widgets[k].setText(v)
        self.scr._widgets["id_date_embauche"].set_iso("2016-06-14")
        self._set("salaire", gain="45000", nbase="30")
        self._set("panier", gain="3000")
        self._set("transport", gain="2500")
        self._set("prime", libelle="PRIME DE RENDEMENT", gain="8000")
        self.scr._recompute()

    # ================= النواة / A2 =================
    def test_default_row_sequence(self):
        self.assertEqual([r.kind for r in self.scr._visible_body_rows()],
                         ["salaire", "prime", "panier", "transport", "cnas", "irg"])

    def test_panier_transport_permanent_and_zero_ok(self):
        for k in ("panier", "transport", "salaire"):
            self.assertFalse(self._row(k).can_delete())
        self._fill()
        self._set("panier", gain="0")
        self._set("transport", gain="0")
        self.scr._recompute()
        self.assertTrue(self.scr._computed)

    def test_system_rows_not_editable(self):
        for k in ("cnas", "irg"):
            self.assertEqual(self._row(k).widgets, {})
        cnas = self._row("cnas")
        self.assertFalse(any(x.startswith("r%d_" % cnas.rid)
                             for x in self.scr._nav_order))

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
        self.assertEqual((v.a, v.b, v.c, v.d, v.e),
                         (r.base_cnas, r.retenue_cnas, r.base_irg,
                          r.retenue_irg, r.net_a_payer))

    def test_not_computable_without_base_salary(self):
        self.assertFalse(self.scr._computed)
        self._fill()
        self.assertTrue(self.scr._computed)
        self._set("salaire", gain="")
        self.scr._recompute()
        self.assertFalse(self.scr._computed)

    def test_paints_without_exception(self):
        self._fill()
        for k in ("iep", "hs", "absence", "retard", "avance", "autre"):
            self.scr._add_row(k)
        self.scr._recompute()
        self.scr._relayout()
        img = QImage(1000, 1600, QImage.Format_ARGB32)
        self.scr._canvas.resize(1000, 1600)
        self.scr._canvas.render(img)

    # ================= + Ajouter / حذف / ترتيب =================
    def test_semantic_order_with_adaptive_types(self):
        for k in ("autre", "retard", "iep", "absence", "hs", "avance"):
            self.scr._add_row(k)
        kinds = [r.kind for r in self.scr._visible_body_rows()]
        self.assertEqual(kinds, ["salaire", "iep", "prime", "hs", "absence",
                                 "retard", "panier", "transport", "cnas",
                                 "irg", "avance", "autre"])

    def test_geometry_moves_with_row_count(self):
        n0 = self.scr._net_y_mm()
        self.scr._add_row("iep")
        self.assertGreater(self.scr._net_y_mm(), n0)
        self.scr._remove_row(self._row("iep", -1))
        self.assertAlmostEqual(self.scr._net_y_mm(), n0, places=3)

    def test_remove_leaves_no_dead_widgets(self):
        r = self._add("hs", qty="5")
        keys = [r.cell_key(c) for c in r.widgets]
        self.scr._remove_row(r)
        for k in keys:
            self.assertNotIn(k, self.scr._widgets)
            self.assertNotIn(k, self.scr._nav_order)

    def test_filled_optional_row_delete_is_guarded(self):
        r = self._add("avance", montant="5000")
        mod.confirm = lambda *_a, **_k: False
        self.scr._remove_row(r)
        self.assertIn(r, self.scr._rows)
        mod.confirm = lambda *_a, **_k: True

    def test_basic_rows_cannot_be_removed(self):
        for k in ("salaire", "panier", "transport", "cnas", "irg"):
            r = self._row(k)
            self.scr._remove_row(r)
            self.assertIn(r, self.scr._rows)

    # ================= الأنواع المتكيّفة (A2.3) =================
    def test_iep_suggestion_applied(self):
        self._fill()
        r = self._add("iep")
        self.assertTrue(r.val("taux"))            # نسبة مقترَحة موضوعة
        self.assertIsNotNone(r._amount)           # مبلغ محسوب

    def test_iep_manual_override_not_crushed(self):
        self._fill()
        r = self._add("iep")
        r.set_val("taux", "0.25")                 # textChanged → _on_row_edit
        self.assertTrue(r._iep_manual)
        self.scr._widgets["id_date_embauche"].set_iso("2005-01-01")
        self.scr._on_slot_write("id_date_embauche")
        self.assertEqual(r.val("taux"), "0.25")   # لم يُسحق
        r.set_val("taux", "")                     # تفريغ → عودة للاقتراح
        self.assertFalse(r._iep_manual)
        self.assertTrue(r.val("taux"))            # أُعيدت النسبة المقترَحة

    def test_iep_reacts_to_date_when_not_overridden(self):
        self._fill()
        r = self._add("iep")
        self.scr._widgets["id_date_embauche"].set_iso("2000-01-01")
        self.scr._on_slot_write("id_date_embauche")
        t_old = r.val("taux")
        self.scr._widgets["id_date_embauche"].set_iso("2024-01-01")
        self.scr._on_slot_write("id_date_embauche")
        self.assertNotEqual(r.val("taux"), t_old)

    def test_absence_jours_and_heures_mapping(self):
        self._fill()
        r = self._add("absence", qty="3")
        r.set_val("mode", "Absence (jours)")
        self.assertEqual(r.entry()["type"], "abs_jours")
        self.scr._recompute()
        amt_j = r._amount
        r.set_val("mode", "Absence (heures)")     # نفس السطر
        self.assertEqual(r.entry()["type"], "abs_heures")
        self.scr._recompute()
        self.assertNotEqual(r._amount, amt_j)
        self.assertIsNotNone(r._amount)

    def test_retard_calculated_retenue(self):
        self._fill()
        r = self._add("retard", qty="4")
        self.assertIsNotNone(r._amount)
        self.assertNotIn("retenue", r.widgets)    # المبلغ ليس widget

    def test_hs_50_and_100(self):
        self._fill()
        h50 = self._add("hs", qty="10")
        h50.set_val("coef", "50%")
        self.scr._recompute()
        a50 = h50._amount
        h50.set_val("coef", "100%")
        self.scr._recompute()
        self.assertGreater(h50._amount, a50)

    def test_two_hs_rows_50_and_100(self):
        self._fill()
        a = self._add("hs", qty="10")
        a.set_val("coef", "50%")
        b = self._add("hs", qty="6")
        b.set_val("coef", "100%")
        self.scr._recompute()
        self.assertIsNotNone(a._amount)
        self.assertIsNotNone(b._amount)
        self.assertNotEqual(a._amount, b._amount)

    def test_calculated_amount_cells_are_not_widgets_or_tabstops(self):
        self._fill()
        for k in ("iep", "hs", "absence", "retard"):
            r = self._add(k)
            comp_col = mod._ROW_SPECS[k]["computed"]
            self.assertNotIn(comp_col, r.widgets)
            self.assertNotIn(r.cell_key(comp_col), self.scr._nav_order)

    def test_computed_amount_not_shown_when_not_computable(self):
        r = self._add("retard", qty="3")          # لا أجر قاعديّ
        self.assertFalse(self.scr._computed)
        self.assertIsNone(r._amount)              # لا 0,00 كاذب

    def test_autre_gain_and_retenue(self):
        self._fill()
        r = self._add("autre", libelle="X", montant="1000")
        r.set_val("sens", "Retenue")
        self.scr._recompute()
        net_ret = self.scr._calc_result.net_a_payer
        r.set_val("sens", "Gain")
        r.set_val("classe", "Net (ni CNAS ni IRG)")
        self.scr._recompute()
        net_gain = self.scr._calc_result.net_a_payer
        self.assertEqual(net_gain - net_ret, 2000)   # -1000 retenue +1000 gain

    def test_autre_no_silent_classification(self):
        r = self._row("autre") or self._add("autre")
        r = self._add("autre")
        self.assertIn("sens", r.widgets)             # اختيار صريح
        self.assertEqual(r.entry()["values"]["est_retenue"], "نعم")  # افتراض معلَن
        r.set_val("sens", "Gain")
        self.assertEqual(r.entry()["values"]["est_retenue"], "لا")

    def test_prime_per_row_soumis(self):
        self._fill()
        base0 = self.scr._calc_result.base_cnas
        self._row("prime").set_val("soumis", "Net (ni CNAS ni IRG)")
        self.scr._recompute()
        self.assertLess(self.scr._calc_result.base_cnas, base0)

    def test_nav_rebuild_after_add_remove(self):
        n0 = len(self.scr._nav_order)
        r = self._add("hs", qty="1")
        self.assertGreater(len(self.scr._nav_order), n0)
        self.scr._remove_row(r)
        self.assertEqual(len(self.scr._nav_order), n0)

    # ================= مسح / مسوّدة =================
    def test_clear_resets_to_defaults(self):
        self._fill()
        self.scr._add_row("iep")
        self.scr._on_clear()
        self.assertEqual([r.kind for r in self.scr._visible_body_rows()],
                         ["salaire", "prime", "panier", "transport", "cnas", "irg"])

    def test_draft_roundtrip_with_adaptive_rows(self):
        self._fill()
        self._add("hs", qty="8")
        self._row("hs", -1).set_val("coef", "100%")
        self._add("autre", libelle="Z", montant="1200")
        self._row("autre", -1).set_val("sens", "Gain")
        st = self.scr.draft_state()
        other = BulletinTemplateScreen(conn=None)
        other.apply_draft(st)
        self.assertEqual(other._widgets["id_nom"].text(), "BENALI")
        h = [r for r in other._rows if r.kind == "hs"]
        self.assertTrue(h and h[-1].val("coef") == "100%" and h[-1].val("qty") == "8")
        a = [r for r in other._rows if r.kind == "autre"]
        self.assertTrue(a and a[-1].val("sens") == "Gain")
        other.deleteLater()


if __name__ == "__main__":
    unittest.main()
