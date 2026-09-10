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
    import re as _re
    from programme import database, paths
    from programme.payroll import calc
    from programme.payroll.config_loader import load_params
    import ui.hr.paie.template_simple as T
    import ui2.hr.paie.bulletin_template as mod
    from ui2.hr.paie.bulletin_template import BulletinTemplateScreen
    from ui2 import theme

    def _money(s):
        s = _re.sub(r"[^\d,\-]", "", str(s or "")).replace(",", ".")
        return float(s) if s not in ("", "-", ".") else 0.0

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


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class BulletinTemplateValidation(unittest.TestCase):
    """Phase B — تحقّق مرن + ⚠️ غير مكتمل."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="om_val_")
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

    def _fill_final(self):
        """يملأ كلّ ما يلزم كي يصير الكشف جاهزاً للإصدار النهائي."""
        w = self.scr._widgets
        for k, v in _HEADER.items():
            w[k].setText(v)
        w["emp_adresse"].setText("12 RUE DES FRERES, ALGER")
        w["id_lieu_naissance"].setText("ALGER")
        w["id_fonction"].setText("COMPTABLE")
        w["id_date_naissance"].set_iso("1990-05-10")
        w["id_date_embauche"].set_iso("2016-06-14")
        self._set("salaire", gain="45000", nbase="30")
        self._set("panier", gain="3000")
        self._set("transport", gain="2500")
        self._set("prime", libelle="PRIME DE RENDEMENT", gain="8000")
        self.scr._recompute()

    def _v(self):
        return self.scr.validate()

    # ================= الحقول الإلزامية =================
    def test_all_required_fields_recognized(self):
        v = self._v()
        missing = {p.key for p in v.missing_required}
        self.assertEqual(
            missing,
            {"emp_raison_sociale", "emp_adresse", "emp_cnas", "mois", "annee",
             "id_nom", "id_prenom", "id_date_naissance", "id_lieu_naissance",
             "id_date_embauche", "id_fonction"})

    def test_fill_final_is_ready(self):
        self._fill_final()
        v = self._v()
        self.assertTrue(v.ready_for_final, v.summary_lines())
        self.assertFalse(v.is_incomplete)

    def test_matricule_optional(self):
        self._fill_final()
        self.scr._widgets["id_matricule"].setText("")
        self.assertTrue(self._v().ready_for_final)

    def test_num_ss_optional(self):
        self._fill_final()
        self.scr._widgets["id_num_ss"].set_value("")
        self.assertTrue(self._v().ready_for_final)

    def test_situation_familiale_optional_and_not_mutated(self):
        self._fill_final()
        self.assertEqual(self.scr._widgets["id_situation_familiale"].text(), "")
        self.assertTrue(self._v().ready_for_final)
        self.scr.show_required_warnings()          # محاولة إصدار
        self.assertEqual(self.scr._widgets["id_situation_familiale"].text(), "")

    # ================= الأجر / السلة / النقل =================
    def test_panier_zero_valid(self):
        self._fill_final()
        self._set("panier", gain="0")
        self.scr._recompute()
        self.assertTrue(self._v().ready_for_final)

    def test_transport_zero_valid(self):
        self._fill_final()
        self._set("transport", gain="0")
        self.scr._recompute()
        self.assertTrue(self._v().ready_for_final)

    def test_salaire_missing_invalid_or_zero_blocks_final(self):
        self._fill_final()
        for bad in ("", "0", "-5"):
            self._set("salaire", gain=bad)
            self.scr._recompute()
            v = self._v()
            self.assertFalse(v.ready_for_final, bad)
            self.assertTrue(any(p.kind == "payroll" for p in v.payroll_errors))

    # ================= اكتمال الـ Rubriques =================
    def test_blank_default_prime_not_incomplete(self):
        self._fill_final()
        self._set("prime", libelle="", gain="", code="")
        self.scr._recompute()
        v = self._v()
        self.assertEqual(v.incomplete_rows, [])
        self.assertTrue(v.ready_for_final)

    def test_partially_filled_prime_is_incomplete(self):
        self._fill_final()
        self._set("prime", libelle="PRIME EXCEPTIONNELLE", gain="")
        self.scr._recompute()
        v = self._v()
        self.assertTrue(v.incomplete_rows)
        self.assertFalse(v.ready_for_final)

    def test_incomplete_absence(self):
        self._fill_final()
        self._add("absence", qty="0")
        self.assertTrue(any(p.kind == "row" for p in self._v().incomplete_rows))

    def test_incomplete_hs(self):
        self._fill_final()
        self._add("hs", qty="0")
        self.assertFalse(self._v().ready_for_final)

    def test_incomplete_retard(self):
        self._fill_final()
        self._add("retard", qty="0")
        self.assertFalse(self._v().ready_for_final)

    def test_incomplete_iep(self):
        self._fill_final()
        r = self._add("iep")
        r.set_val("taux", "abc")                   # نسبة غير رقميّة ⇒ يدويّ + ناقص
        self.scr._recompute()
        self.assertTrue(r._iep_manual)
        v = self._v()
        self.assertTrue(any(p.kind == "row" for p in v.incomplete_rows))
        self.assertFalse(v.ready_for_final)

    def test_incomplete_avance(self):
        self._fill_final()
        self._add("avance", montant="5000")        # بلا libellé
        self.assertFalse(self._v().ready_for_final)

    def test_incomplete_autre(self):
        self._fill_final()
        self._add("autre", montant="1000")         # بلا libellé
        self.assertFalse(self._v().ready_for_final)

    def test_complete_adaptive_rows_are_ready(self):
        self._fill_final()
        self._add("hs", qty="10")
        self._add("retard", qty="2")
        self._add("avance", libelle="AVANCE", montant="10000")
        self.scr._recompute()
        self.assertTrue(self._v().ready_for_final, self._v().summary_lines())

    # ================= التاريخ =================
    def test_invalid_birth_start_relation(self):
        self._fill_final()
        w = self.scr._widgets
        w["id_date_naissance"].set_iso("1990-05-10")
        w["id_date_embauche"].set_iso("1985-01-01")   # قبل الميلاد
        self.scr._recompute()
        v = self._v()
        self.assertTrue(any(p.key == "id_date_embauche"
                            for p in v.invalid_fields))
        self.assertFalse(v.ready_for_final)

    # ================= السلوك البصريّ =================
    def test_no_required_warnings_on_fresh_blank_screen(self):
        self.assertFalse(self.scr._warnings_active)
        self.assertFalse(self.scr._warns("id_nom"))
        self.assertTrue(self.scr._incomplete_lbl.isHidden())

    def test_show_required_warnings_marks_missing(self):
        ready = self.scr.show_required_warnings()
        self.assertFalse(ready)
        self.assertTrue(self.scr._warnings_active)
        self.assertTrue(self.scr._warns("emp_raison_sociale"))
        self.assertFalse(self.scr._incomplete_lbl.isHidden())

    def test_fixing_field_clears_its_warning_immediately(self):
        self.scr.show_required_warnings()
        self.assertTrue(self.scr._warns("id_nom"))
        self.scr._widgets["id_nom"].setText("BENALI")   # textChanged → recompute
        self.assertFalse(self.scr._warns("id_nom"))
        self.assertTrue(self.scr._warns("emp_adresse"))  # البقيّة ما زالت

    def test_all_fixed_clears_all_warnings(self):
        self.scr.show_required_warnings()
        self.assertTrue(self.scr._warnings_active)
        self._fill_final()
        self.assertFalse(self.scr._warnings_active)
        self.assertTrue(self.scr._incomplete_lbl.isHidden())

    def test_focus_goes_to_first_problem_in_nav_order(self):
        self.scr.show_required_warnings()
        first = self.scr._validation.first_key(self.scr._nav_order)
        self.assertEqual(first, "emp_raison_sociale")

    def test_validation_reports_all_problems_in_one_pass(self):
        v = self._v()
        self.assertTrue(v.missing_required)
        self.assertTrue(v.payroll_errors)
        self.assertGreaterEqual(len(v.problems), 10)

    def test_finalize_blocked_when_incomplete_emits_one_notice(self):
        import ui2.alerts as alerts
        calls = []
        orig = alerts.warn
        alerts.warn = lambda *a, **k: calls.append(a)
        try:
            self.scr._on_finalize()
        finally:
            alerts.warn = orig
        self.assertEqual(len(calls), 1)
        self.assertTrue(self.scr._warnings_active)

    # ================= المسوّدة / الاستعادة =================
    def test_dynamic_rows_restore_keeps_validation_state(self):
        self._fill_final()
        self._set("prime", libelle="PRIME X", gain="")     # ناقصة
        self._add("hs", qty="8")
        self._row("hs", -1).set_val("coef", "100%")
        self.scr._recompute()
        st = self.scr.draft_state()
        self.assertTrue(st["incomplete"])
        other = BulletinTemplateScreen(conn=None)
        other.apply_draft(st)
        self.assertFalse(other._warnings_active)           # لا تحذير تلقائيّ (§14)
        self.assertTrue(other._restored_incomplete)
        v = other.validate()
        self.assertTrue(v.incomplete_rows)
        h = [r for r in other._rows if r.kind == "hs"]
        self.assertTrue(h and h[-1].val("coef") == "100%")
        other.deleteLater()

    def test_clear_resets_warnings(self):
        self.scr.show_required_warnings()
        self.assertTrue(self.scr._warnings_active)
        self.scr._on_clear()
        self.assertFalse(self.scr._warnings_active)
        self.assertFalse(self.scr._restored_incomplete)


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class BulletinTemplateWorkC1(unittest.TestCase):
    """Phase C1 — عمل دائم: Save incomplete · معرّف مستقرّ · reopen ·
    ثبات الصفوف الديناميكية · auto-draft ≠ عمل محفوظ."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="om_c1_")
        os.environ[paths._LOCAL_STATE_ENV_OVERRIDE] = self._tmp
        os.environ[paths._DATA_DIR_ENV_OVERRIDE] = self._tmp
        database.init_db()
        mod.confirm = lambda *_a, **_k: True
        self.scr = BulletinTemplateScreen(conn=None)

    def tearDown(self):
        self.scr.deleteLater()
        os.environ.pop(paths._LOCAL_STATE_ENV_OVERRIDE, None)
        os.environ.pop(paths._DATA_DIR_ENV_OVERRIDE, None)

    # ---- أدوات ----
    def _row(self, kind, occ=-1):
        rs = [r for r in self.scr._rows if r.kind == kind]
        return rs[occ] if rs else None

    def _fill_min(self):
        w = self.scr._widgets
        w["id_nom"].setText("BENALI")
        w["id_prenom"].setText("Karim")
        w["mois"].setText("OCTOBRE")
        w["annee"].setText("2026")
        self._row("salaire").set_val("gain", "45000")
        self.scr._recompute()

    def _reopen(self):
        rid = self.scr._work_id
        other = BulletinTemplateScreen(conn=None)
        other.load_work(database.get_hr_document(rid))
        return other

    # ---- الاختبارات ----
    def test_save_incomplete_creates_work(self):
        self._fill_min()                              # ناقص (لا شركة/عنوان…)
        self.scr._on_save()
        self.assertIsNotNone(self.scr._work_id)
        self.assertEqual(self.scr._work_state, "incomplete")
        row = database.get_hr_document(self.scr._work_id)
        self.assertEqual(row["state"], "incomplete")
        self.assertEqual(row["file_path"], "")        # لا مستند نهائيّ
        self.assertEqual(row["screen_key"], "hr_bulletin_paie")

    def test_save_never_blocked_by_incomplete(self):
        # شاشة شبه فارغة — الحفظ يمرّ رغم النقص
        self.scr._on_save()
        self.assertIsNotNone(self.scr._work_id)

    def test_stable_work_id_on_resave(self):
        self._fill_min()
        self.scr._on_save()
        wid = self.scr._work_id
        self.scr._widgets["id_prenom"].setText("Kamel")
        self.scr._on_save()
        self.assertEqual(self.scr._work_id, wid)      # نفس المعرّف
        rows = database.list_hr_documents(screen_key="hr_bulletin_paie")
        self.assertEqual(len([r for r in rows if r["id"] == wid]), 1)
        self.assertEqual(database.get_hr_document(wid)["employee_name"],
                         "BENALI Kamel")

    def test_reopen_incomplete_restores_and_warns(self):
        self._fill_min()
        self.scr._add_row("hs")
        self._row("hs", -1).set_val("qty", "8")
        self._row("hs", -1).set_val("coef", "100%")
        self.scr._recompute()
        self.scr._on_save()
        other = self._reopen()
        self.assertEqual(other._widgets["id_nom"].text(), "BENALI")
        self.assertEqual(other._work_state, "incomplete")
        self.assertTrue(other._warnings_active)       # ⚠️ عند إعادة الفتح (§5)
        h = [r for r in other._rows if r.kind == "hs"]
        self.assertTrue(h and h[-1].val("qty") == "8" and h[-1].val("coef") == "100%")
        other.deleteLater()

    def test_classifications_persist(self):
        self._fill_min()
        self._row("prime").set_val("soumis", "Net (ni CNAS ni IRG)")
        self.scr._add_row("autre")
        self._row("autre", -1).set_val("sens", "Gain")
        self._row("autre", -1).set_val("libelle", "BONUS")
        self._row("autre", -1).set_val("montant", "1000")
        self.scr._add_row("iep")
        self._row("iep", -1).set_val("taux", "0.19")   # يدويّ
        self.scr._recompute()
        self.scr._on_save()
        other = self._reopen()
        self.assertEqual([r for r in other._rows if r.kind == "prime"][0]
                         .val("soumis"), "Net (ni CNAS ni IRG)")
        a = [r for r in other._rows if r.kind == "autre"][-1]
        self.assertEqual(a.val("sens"), "Gain")
        ie = [r for r in other._rows if r.kind == "iep"][-1]
        self.assertTrue(ie._iep_manual and ie.val("taux") == "0.19")
        other.deleteLater()

    def test_autodraft_is_not_saved_work(self):
        self._fill_min()
        self.scr.mark_dirty()
        self.scr.flush_draft()
        self.assertIsNotNone(self.scr.load_draft())   # مسوّدة تلقائية موجودة
        self.scr._on_save()
        self.assertIsNone(self.scr.load_draft())      # الحفظ يَجُبّها
        self.assertIsNotNone(self.scr._work_id)
        fresh = BulletinTemplateScreen(conn=None)
        self.assertIsNone(fresh._work_id)             # شاشة جديدة = بلا هويّة
        fresh.deleteLater()

    def test_dirty_flag_clean_after_load(self):
        self._fill_min()
        self.scr._on_save()
        other = self._reopen()
        self.assertFalse(other.has_unsaved_changes())  # محمَّل وغير ملموس
        other._widgets["id_prenom"].setText("Z")
        self.assertTrue(other.has_unsaved_changes())
        other.deleteLater()

    def test_clear_drops_work_identity(self):
        self._fill_min()
        self.scr._on_save()
        self.assertIsNotNone(self.scr._work_id)
        self.scr._on_clear()
        self.assertIsNone(self.scr._work_id)
        self.assertIsNone(self.scr._work_state)

    def test_backward_compatible_with_legacy_log_rows(self):
        # صفّ قديم عبر log_hr_document (بلا state) يبقى مقروءاً
        rid = database.log_hr_document(
            {"screen_key": "hr_bulletin_paie", "doc_label": "Bulletin de paie",
             "employee_name": "OLD X", "file_path": "/x/old.docx"},
            full_data={"legacy": True})
        row = database.get_hr_document(rid)
        self.assertIsNotNone(row)
        self.assertIsNone(row["state"])
        self.assertEqual(mod.BulletinTemplateScreen._WORK_BADGE.get(row["state"], ""), "")

    def test_work_badge(self):
        self.assertEqual(self.scr.work_badge(), self.scr.incomplete_badge())
        self._fill_min()
        self.scr._on_save()
        self.assertEqual(self.scr.work_badge(), "⚠️")


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class RendererFromViewC2(unittest.TestCase):
    """Phase C2 — المُصيِّر من BulletinView (مصدر الحقيقة) + إصلاح
    Absence/Retard + اتزان العمودين + Panier/Transport بصفر + «/»."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="om_c2_")
        os.environ[paths._LOCAL_STATE_ENV_OVERRIDE] = self._tmp
        mod.confirm = lambda *_a, **_k: True
        self.scr = BulletinTemplateScreen(conn=None)

    def tearDown(self):
        self.scr.deleteLater()
        os.environ.pop(paths._LOCAL_STATE_ENV_OVERRIDE, None)

    def _row(self, kind, occ=-1):
        rs = [r for r in self.scr._rows if r.kind == kind]
        return rs[occ] if rs else None

    def _full(self, **kw):
        w = self.scr._widgets
        w["id_nom"].setText("BENALI"); w["id_prenom"].setText("Karim")
        w["mois"].setText("OCTOBRE"); w["annee"].setText("2026")
        w["id_date_embauche"].set_iso("2016-06-14")
        self._row("salaire").set_val("gain", "45000")
        self._row("salaire").set_val("nbase", "26")
        self._row("panier").set_val("gain", "3000")
        self._row("transport").set_val("gain", "2500")
        self._row("prime").set_val("libelle", "PRIME DE RENDEMENT")
        self._row("prime").set_val("gain", "8000")
        for kind, cells in kw.items():
            self.scr._add_row(kind)
            for c, v in cells.items():
                self._row(kind, -1).set_val(c, v)
        self.scr._recompute()

    def _rows(self):
        return T._bulletin_rows_from_view(
            self.scr._bulletin_view, self.scr._employee_data(),
            jours=self.scr._calc_input.jours)

    # ---- الاختبارات ----
    def test_all_dynamic_rubriques_rendered(self):
        self._full(iep={}, hs={"qty": "10", "coef": "100%"},
                   absence={"qty": "2", "mode": "Absence (jours)"},
                   retard={"qty": "3"},
                   avance={"libelle": "AVANCE", "montant": "10000"},
                   autre={"sens": "Gain", "libelle": "BONUS", "montant": "1500"})
        libs = " ".join(r["libelle"] for r in self._rows())
        for token in ("SALAIRE DE BASE", "PRIME DE RENDEMENT", "PANIER",
                      "TRANSPORT", "RETENUE SÉCU", "RETENUE IRG", "AVANCE",
                      "BONUS", "EXPÉRIENCE", "HEURES SUPP", "ABSENCE",
                      "RETARD"):
            self.assertIn(token, libs, token)

    def test_absence_retard_are_negative_gain_not_retenue(self):
        self._full(absence={"qty": "2", "mode": "Absence (jours)"},
                   retard={"qty": "3"})
        for r in self._rows():
            lib = r["libelle"]
            if "ABSENCE" in lib or "TÂCHE" in lib or "GHIAB" in lib \
                    or r["code"] == "4000" or r["code"] == "4010" \
                    or r["code"] == "4020":
                self.assertTrue(r["gain"].strip().startswith("-"), r)
                self.assertEqual(r["retenue"].strip(), "", r)

    def test_columns_balance_to_net(self):
        self._full(iep={}, hs={"qty": "10", "coef": "50%"},
                   absence={"qty": "1", "mode": "Absence (jours)"},
                   retard={"qty": "2"},
                   avance={"libelle": "AV", "montant": "5000"})
        rows = self._rows()
        g = sum(_money(r["gain"]) for r in rows)
        rr = sum(_money(r["retenue"]) for r in rows)
        res = self.scr._bulletin_view.result
        self.assertAlmostEqual(g, float(res.total_gains), places=1)
        self.assertAlmostEqual(rr, float(res.total_retenues), places=1)
        self.assertAlmostEqual(g - rr, float(self.scr._bulletin_view.e), places=1)

    def test_totals_net_from_engine(self):
        self._full()
        cfg = load_params(date(2026, 10, 1))
        exp = calc.compute(calc.PaieInput(
            mois="OCTOBRE", annee="2026", jours=26.0, salaire_base=45000.0,
            panier=3000.0, transport=2500.0,
            primes=[calc.Prime(code="LIBRE", libelle="PRIME DE RENDEMENT",
                               montant=8000.0, soumis_cotisation=True,
                               imposable=True)]), cfg)
        self.assertEqual(self.scr._bulletin_view.e, exp.net_a_payer)

    def test_cnas_irg_rows_from_view(self):
        self._full()
        rows = {r["code"]: r for r in self._rows()}
        v = self.scr._bulletin_view
        cnas = rows[mod._C["cnas"]]
        self.assertEqual(cnas["taux"], "9,00")
        self.assertEqual(_money(cnas["retenue"]), float(v.b))
        irg = rows[mod._C["irg"]]
        self.assertEqual(_money(irg["retenue"]), float(v.d))

    def test_panier_transport_zero_still_rendered(self):
        self._full()
        self._row("panier").set_val("gain", "0")
        self._row("transport").set_val("gain", "0")
        self.scr._recompute()
        libs = [r["libelle"] for r in self._rows()]
        self.assertIn("PANIER", libs)
        self.assertTrue(any("TRANSPORT" in x for x in libs))

    def test_situation_familiale_slash_render_only(self):
        pairs = dict(T._ident_pairs({"situation_familiale": ""}))
        self.assertEqual(pairs["SIT. FAMILIALE"], "/")
        pairs2 = dict(T._ident_pairs({"situation_familiale": "M"}))
        self.assertEqual(pairs2["SIT. FAMILIALE"], "M")
        # القيمة الداخلية لا تُمسّ
        self.assertEqual(self.scr._widgets["id_situation_familiale"].text(), "")

    def test_docx_pdf_build_from_view(self):
        self._full(absence={"qty": "2", "mode": "Absence (jours)"},
                   hs={"qty": "6", "coef": "100%"})
        tpl = T.get_renderer("simple")
        for ext, builder in ((".docx", tpl.build_docx), (".pdf", tpl.build_pdf)):
            p = os.path.join(self._tmp, "b" + ext)
            try:
                builder(p, self.scr._calc_input, self.scr._calc_result,
                        self.scr._employer_data(), self.scr._employee_data(),
                        view=self.scr._bulletin_view)
            except Exception as exc:                       # noqa: BLE001
                if "غير مثبّتة" in str(exc):
                    self.skipTest(str(exc))
                raise
            self.assertTrue(os.path.exists(p) and os.path.getsize(p) > 0)

    def test_docx_content_matches_view(self):
        try:
            from docx import Document
        except ImportError:
            self.skipTest("python-docx غير مثبّتة")
        self._full(avance={"libelle": "AVANCE", "montant": "10000"})
        p = os.path.join(self._tmp, "c.docx")
        T.get_renderer("simple").build_docx(
            p, self.scr._calc_input, self.scr._calc_result,
            self.scr._employer_data(), self.scr._employee_data(),
            view=self.scr._bulletin_view)
        cells = [c.text for tbl in Document(p).tables for row in tbl.rows
                 for c in row.cells]
        blob = " ".join(cells)
        self.assertIn("AVANCE", blob)
        self.assertIn("NET À PAYER", blob)
        self.assertIn(calc.fmt_montant(self.scr._bulletin_view.e), blob)


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class FinalizeLockC3(unittest.TestCase):
    """Phase C3 — Finalize شبه معامليّ + 🔒 قفل + فتح القفل + استبدال آمن."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="om_c3_")
        os.environ[paths._LOCAL_STATE_ENV_OVERRIDE] = self._tmp
        os.environ[paths._DATA_DIR_ENV_OVERRIDE] = self._tmp
        os.environ[paths._TRAVAIL_ENV_OVERRIDE] = os.path.join(self._tmp, "travail")
        database.init_db()
        mod.confirm = lambda *_a, **_k: False        # لا تفتح الملفّ
        import ui2.alerts as _al
        self._al, self._al_warn = _al, _al.warn
        _al.warn = lambda *_a, **_k: None            # لا صناديق حوار حاجبة
        self.scr = BulletinTemplateScreen(conn=None)

    def tearDown(self):
        self._al.warn = self._al_warn
        self.scr.deleteLater()
        for k in (paths._LOCAL_STATE_ENV_OVERRIDE, paths._DATA_DIR_ENV_OVERRIDE,
                  paths._TRAVAIL_ENV_OVERRIDE):
            os.environ.pop(k, None)

    def _row(self, kind, occ=-1):
        rs = [r for r in self.scr._rows if r.kind == kind]
        return rs[occ] if rs else None

    def _fill_final(self, s=None):
        s = s or self.scr
        w = s._widgets
        for k, v in {"emp_raison_sociale": "SARL X",
                     "emp_adresse": "12 RUE, ALGER", "emp_cnas": "16 412 078 56",
                     "mois": "OCTOBRE", "annee": "2026", "id_nom": "BENALI",
                     "id_prenom": "Karim", "id_lieu_naissance": "ALGER",
                     "id_fonction": "COMPTABLE"}.items():
            w[k].setText(v)
        w["id_date_naissance"].set_iso("1990-05-10")
        w["id_date_embauche"].set_iso("2016-06-14")
        sr = [r for r in s._rows if r.kind == "salaire"][0]
        sr.set_val("gain", "45000"); sr.set_val("nbase", "26")
        [r for r in s._rows if r.kind == "prime"][0].set_val("gain", "8000")
        [r for r in s._rows if r.kind == "prime"][0].set_val("libelle", "RENDEMENT")
        s._recompute()

    # ---- الاختبارات ----
    def test_finalize_blocked_when_invalid(self):
        self.scr._widgets["id_nom"].setText("X")      # ناقص كثير
        self.scr._on_finalize()
        self.assertNotEqual(self.scr._work_state, "final")
        self.assertFalse(self.scr._locked)
        self.assertTrue(self.scr._warnings_active)

    def test_successful_finalize_creates_docx_pdf_and_locks(self):
        self._fill_final()
        self.scr._on_finalize()
        self.assertEqual(self.scr._work_state, "final")
        self.assertTrue(self.scr._locked)
        self.assertTrue(os.path.exists(self.scr._final_docx))
        self.assertTrue(os.path.exists(self.scr._final_pdf))
        row = database.get_hr_document(self.scr._work_id)
        self.assertEqual(row["state"], "final")
        self.assertEqual(row["file_path"], self.scr._final_docx)
        self.assertEqual(row["pdf_path"], self.scr._final_pdf)
        self.assertEqual(self.scr.work_badge(), "🔒")

    def test_failed_pdf_does_not_lock_and_cleans_partials(self):
        self._fill_final()
        tpl = mod.T.get_renderer("simple")
        orig = tpl.build_pdf

        def boom(*a, **k):
            raise RuntimeError("انفجار PDF")
        tpl.build_pdf = staticmethod(boom)
        try:
            self.scr._on_finalize()
        finally:
            tpl.build_pdf = staticmethod(orig)
        self.assertNotEqual(self.scr._work_state, "final")
        self.assertFalse(self.scr._locked)
        base = os.path.join(self._tmp, "travail", "Bulletins de paie")
        leftovers = [f for f in (os.listdir(base) if os.path.isdir(base) else [])
                     if f.endswith(".part")]
        self.assertEqual(leftovers, [])

    def test_db_save_failure_reverts_and_does_not_lock(self):
        self._fill_final()
        orig = database.save_hr_work
        database.save_hr_work = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("DB down"))
        try:
            self.scr._on_finalize()
        finally:
            database.save_hr_work = orig
        self.assertIsNone(self.scr._work_state)
        self.assertFalse(self.scr._locked)

    def test_lock_covers_all_inputs_zoom_still_works(self):
        self._fill_final()
        self.scr._add_row("hs")
        self._row("hs", -1).set_val("qty", "6")
        self.scr._recompute()
        self.scr._on_finalize()
        # كلّ مدخلات الترويسة والصفوف للقراءة فقط
        for k, w in self.scr._widgets.items():
            if hasattr(w, "isReadOnly"):
                self.assertTrue(w.isReadOnly(), k)
        self.assertFalse(self.scr._add_btn.isEnabled())
        # الزوم يبقى يعمل فوق العمل المقفول
        self.scr._set_zoom(45)
        self.assertEqual(self.scr.zoom, 45)
        # + Ajouter / حذف صفّ محروسان
        n = len(self.scr._rows)
        self.scr._add_row("avance")
        self.assertEqual(len(self.scr._rows), n)

    def test_unlock_restores_editability(self):
        self._fill_final()
        self.scr._on_finalize()
        mod.confirm = lambda *_a, **_k: True
        self.scr._on_unlock()
        self.assertFalse(self.scr._locked)
        self.assertFalse(self.scr._widgets["id_nom"].isReadOnly())
        self.assertTrue(self.scr._add_btn.isEnabled())
        self.assertEqual(self.scr._work_state, "final")   # ما زال 🔒 داخلياً

    def test_edit_after_unlock_save_does_not_touch_final_files(self):
        self._fill_final()
        self.scr._on_finalize()
        pdf = self.scr._final_pdf
        before = os.path.getmtime(pdf), os.path.getsize(pdf)
        mod.confirm = lambda *_a, **_k: True
        self.scr._on_unlock()
        self.scr._widgets["id_prenom"].setText("Kamel")
        self.scr._on_save()
        self.assertEqual((os.path.getmtime(pdf), os.path.getsize(pdf)), before)
        self.assertEqual(self.scr._work_state, "incomplete")
        self.assertEqual(self.scr.work_badge(), "⚠️")
        row = database.get_hr_document(self.scr._work_id)
        self.assertEqual(row["state"], "incomplete")
        self.assertEqual(row["pdf_path"], pdf)            # مرجع «آخر ما صدر»

    def test_refinalize_same_work_replaces_artifacts(self):
        self._fill_final()
        self.scr._on_finalize()
        wid, pdf = self.scr._work_id, self.scr._final_pdf
        mod.confirm = lambda *_a, **_k: True
        self.scr._on_unlock()
        self.scr._widgets["id_prenom"].setText("Kamel")
        self.scr._recompute()
        mod.confirm = lambda *_a, **_k: False
        self.scr._on_finalize()
        self.assertEqual(self.scr._work_id, wid)
        self.assertEqual(self.scr._final_pdf, pdf)        # نفس المسار
        self.assertEqual(self.scr._work_state, "final")
        rows = [r for r in database.list_hr_documents(
            screen_key="hr_bulletin_paie") if r["id"] == wid]
        self.assertEqual(len(rows), 1)

    def test_reopen_final_work_is_locked(self):
        self._fill_final()
        self.scr._on_finalize()
        wid = self.scr._work_id
        other = BulletinTemplateScreen(conn=None)
        other.load_work(database.get_hr_document(wid))
        self.assertEqual(other._work_state, "final")
        self.assertTrue(other._locked)
        self.assertTrue(other._widgets["id_nom"].isReadOnly())
        other.deleteLater()


if __name__ == "__main__":
    unittest.main()
