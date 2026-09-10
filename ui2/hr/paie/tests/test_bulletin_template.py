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
    from PySide6.QtCore import QPoint
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

    def _isolate_db(tmp):
        """يعزل قاعدة البيانات في ``tmp``: ``OFFICEMANAGER_DATA_DIR`` وحده
        لا يكفي — ``get_db_path`` يتدرّج إلى نسخة جذر المشروع إن لم يوجد
        ملفّ في المكان الجديد. نُنشئ ملفّاً فارغاً أوّلاً ثمّ ``init_db``."""
        os.environ[paths._DATA_DIR_ENV_OVERRIDE] = tmp
        open(os.path.join(tmp, "office_system.db"), "a").close()
        database.init_db()

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
        self._add("prime", libelle="PRIME DE RENDEMENT", gain="8000")
        self.scr._recompute()

    # ================= النواة / A2 =================
    def test_default_row_sequence(self):
        #  R1: النواة الثابتة فقط — لا سطر Prime افتراضيّ؛ الترتيب §3:
        #  الأجر → CNAS → السلة → النقل → IRG.
        self.assertEqual([r.kind for r in self.scr._visible_body_rows()],
                         ["salaire", "cnas", "panier", "transport", "irg"])

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
    def test_zone_bucketed_order(self):
        #  R1: الترتيب حسب المناطق (§3) لا حسب النوع. الاختيارية داخل حزمة
        #  منطقتها بترتيب الإضافة. iep/hs/absence/retard/prime ⇒ Zone A
        #  (فوق CNAS)؛ avance/autre ⇒ Zone C (تحت IRG).
        self._add("prime", gain="1")
        for k in ("autre", "retard", "iep", "absence", "hs", "avance"):
            self.scr._add_row(k)
        kinds = [r.kind for r in self.scr._visible_body_rows()]
        self.assertEqual(kinds, ["salaire", "prime", "retard", "iep", "absence",
                                 "hs", "cnas", "panier", "transport",
                                 "irg", "autre", "avance"])

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
                         ["salaire", "cnas", "panier", "transport", "irg"])

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
class BulletinTemplateZoneModelR1(unittest.TestCase):
    """UX Redesign R1 — نموذج المناطق A/B/C + هندسة أسفل ثابتة + توافق خلفيّ."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="om_r1_")
        os.environ[paths._LOCAL_STATE_ENV_OVERRIDE] = self._tmp
        mod.confirm = lambda *_a, **_k: True
        self.scr = BulletinTemplateScreen(conn=None)

    def tearDown(self):
        self.scr.deleteLater()
        os.environ.pop(paths._LOCAL_STATE_ENV_OVERRIDE, None)

    def _last(self, kind):
        return [r for r in self.scr._rows if r.kind == kind][-1]

    # ---------- المناطق ----------
    def test_default_zone_mapping(self):
        for kind, zone in (("iep", "A"), ("hs", "A"), ("absence", "A"),
                           ("retard", "A"), ("prime", "A"),
                           ("avance", "C"), ("autre", "C")):
            self.scr._add_row(kind)
            self.assertEqual(self._last(kind).zone, zone, kind)

    def test_fixed_core_only_no_default_prime(self):
        kinds = [r.kind for r in self.scr._visible_body_rows()]
        self.assertEqual(kinds, ["salaire", "cnas", "panier", "transport", "irg"])

    def test_panier_transport_between_cnas_and_irg(self):
        rows = [r.kind for r in self.scr._visible_body_rows()]
        self.assertLess(rows.index("cnas"), rows.index("panier"))
        self.assertLess(rows.index("panier"), rows.index("transport"))
        self.assertLess(rows.index("transport"), rows.index("irg"))
        for k in ("panier", "transport", "cnas", "irg", "salaire"):
            r = [x for x in self.scr._rows if x.kind == k][0]
            self.scr._remove_row(r)
            self.assertIn(r, self.scr._rows)          # ثابتة — لا تُحذَف

    def test_zone_a_rows_sit_above_cnas(self):
        self.scr._add_row("iep")
        self.scr._add_row("hs")
        rows = [r.kind for r in self.scr._visible_body_rows()]
        self.assertLess(rows.index("iep"), rows.index("cnas"))
        self.assertLess(rows.index("hs"), rows.index("cnas"))

    def test_zone_c_rows_sit_below_irg(self):
        self.scr._add_row("avance")
        rows = [r.kind for r in self.scr._visible_body_rows()]
        self.assertGreater(rows.index("avance"), rows.index("irg"))

    # ---------- هندسة أسفل ثابتة (§4/§31) ----------
    def test_continuous_bottom_no_floating_gap(self):
        self.assertAlmostEqual(self.scr._total_y_mm(), self.scr._body_bottom_mm())
        self.assertAlmostEqual(self.scr._net_y_mm(),
                               self.scr._total_y_mm() + T.ROW_H)

    def test_min_body_slots_hold_net_position(self):
        net0 = self.scr._net_y_mm()
        for _ in range(self.scr.MIN_BODY_SLOTS):           # 5 صفوف Zone C
            self.scr._add_row("avance")
            self.assertAlmostEqual(self.scr._net_y_mm(), net0)
        self.scr._add_row("avance")                        # السادس يُنزِل NET
        self.assertGreater(self.scr._net_y_mm(), net0)

    def test_zone_a_row_always_grows_document(self):
        net0 = self.scr._net_y_mm()
        self.scr._add_row("iep")
        self.assertGreater(self.scr._net_y_mm(), net0)

    def test_total_net_geometry_independent_of_computable(self):
        n_uncomputed = (self.scr._total_y_mm(), self.scr._net_y_mm())
        w = self.scr._widgets
        [r for r in self.scr._rows if r.kind == "salaire"][0].set_val("gain", "45000")
        w["mois"].setText("OCTOBRE"); w["annee"].setText("2026")
        self.scr._recompute()
        self.assertTrue(self.scr._computed)
        self.assertEqual(n_uncomputed,
                         (self.scr._total_y_mm(), self.scr._net_y_mm()))

    def test_paints_when_not_computable(self):
        self.assertFalse(self.scr._computed)
        img = QImage(1100, 1700, QImage.Format_ARGB32)
        self.scr._canvas.resize(1100, 1700)
        self.scr._canvas.render(img)                       # لا استثناء + TOTAL/NET مرسومان

    # ---------- توافق خلفيّ (§39) ----------
    def test_legacy_draft_without_zone_maps_to_zones(self):
        legacy = {
            "header": {"id_nom": "X"},
            "rows": [
                {"kind": "iep", "cells": {"taux": "0.05"}},
                {"kind": "prime", "cells": {"soumis": "IRG seul",
                                            "gain": "1000"}},
                {"kind": "prime", "cells": {"soumis": "CNAS + IRG",
                                            "gain": "1000"}},
                {"kind": "avance", "cells": {"montant": "500"}},
                {"kind": "autre", "cells": {"sens": "Gain",
                                            "classe": "Net (ni CNAS ni IRG)",
                                            "montant": "300"}},
            ],
        }
        self.scr.apply_draft(legacy)
        z = {(r.kind, r.val("soumis") or r.val("classe")): r.zone
             for r in self.scr._rows if r.role == "optional"}
        self.assertEqual(z[("iep", "")], "A")
        self.assertEqual(z[("prime", "IRG seul")], "B")
        self.assertEqual(z[("prime", "CNAS + IRG")], "A")
        self.assertEqual(z[("avance", "")], "C")
        self.assertEqual(z[("autre", "Net (ni CNAS ni IRG)")], "C")

    def test_draft_roundtrip_preserves_explicit_zone(self):
        self.scr._add_row("prime")
        self._last("prime").segment = "B3"
        st = self.scr.draft_state()
        self.assertEqual([r for r in st["rows"] if r["kind"] == "prime"][0]["zone"],
                         "B")
        other = BulletinTemplateScreen(conn=None)
        other.apply_draft(st)
        self.assertEqual([r for r in other._rows if r.kind == "prime"][0].zone, "B")
        other.deleteLater()


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class BulletinTemplateFreeRowR2(unittest.TestCase):
    """UX Redesign R2 — السطر الحرّ نوع الإضافة الافتراضيّ + قاعدة
    GAIN/RETENUE + N/BASE·TAUX عرض فقط + بلا رمادي."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="om_r2_")
        os.environ[paths._LOCAL_STATE_ENV_OVERRIDE] = self._tmp
        mod.confirm = lambda *_a, **_k: True
        self.scr = BulletinTemplateScreen(conn=None)
        w = self.scr._widgets
        w["mois"].setText("OCTOBRE"); w["annee"].setText("2026")
        [r for r in self.scr._rows if r.kind == "salaire"][0].set_val("gain",
                                                                      "45000")
        self.scr._recompute()

    def tearDown(self):
        self.scr.deleteLater()
        os.environ.pop(paths._LOCAL_STATE_ENV_OVERRIDE, None)

    def _free(self, zone, **cells):
        r = self.scr._insert_free_row(zone)
        for c, v in cells.items():
            r.set_val(c, v)
        self.scr._recompute()
        return r

    # ---------- بنية السطر الحرّ ----------
    def test_free_row_six_plain_cells_no_combobox(self):
        from PySide6.QtWidgets import QComboBox
        r = self.scr._insert_free_row("A")
        self.assertEqual(set(r.widgets), {"code", "libelle", "nbase", "taux",
                                          "gain", "retenue"})
        self.assertFalse(any(isinstance(w, QComboBox)
                             for w in r.widgets.values()))

    def test_insert_free_row_zone_and_position(self):
        rb = self._free("B", libelle="PRIME NON COT", gain="1000")
        rows = [x.kind for x in self.scr._visible_body_rows()]
        self.assertEqual(rb.zone, "B")
        self.assertLess(rows.index("transport"), rows.index("free"))
        self.assertLess(rows.index("free"), rows.index("irg"))

    # ---------- التصنيف من المنطقة (§11) ----------
    def test_free_gain_zone_a_cnas_irg(self):
        r = self._free("A", gain="1000")
        v = r.entry()["values"]
        self.assertEqual((v["cotisable"], v["imposable"], v["est_retenue"]),
                         ("نعم", "نعم", "لا"))

    def test_free_gain_zone_b_irg_only(self):
        v = self._free("B", gain="1000").entry()["values"]
        self.assertEqual((v["cotisable"], v["imposable"]), ("لا", "نعم"))

    def test_free_gain_zone_c_neither(self):
        v = self._free("C", gain="1000").entry()["values"]
        self.assertEqual((v["cotisable"], v["imposable"]), ("لا", "لا"))

    def test_free_gain_zone_a_raises_cnas_base(self):
        base0 = self.scr._calc_result.base_cnas
        self._free("A", gain="5000")
        self.assertGreater(self.scr._calc_result.base_cnas, base0)

    # ---------- GAIN / RETENUE (§10) ----------
    def test_free_retenue_positive_subtracts(self):
        net0 = self.scr._calc_result.net_a_payer
        v = self._free("C", retenue="2000").entry()["values"]
        self.assertEqual(v["est_retenue"], "نعم")
        self.assertLess(self.scr._calc_result.net_a_payer, net0)

    def test_free_gain_and_retenue_mutually_exclusive(self):
        r = self.scr._insert_free_row("C")            # E.3: RETENUE حرّة = Zone C
        r.set_val("gain", "1000")
        self.scr._on_row_edit(r.cell_key("gain"))
        r.set_val("retenue", "300")
        self.scr._on_row_edit(r.cell_key("retenue"))
        self.assertEqual(r.val("gain"), "")            # الأحدث يفوز
        self.assertEqual(r.val("retenue"), "300")

    def test_free_retenue_rejects_negative_sign(self):
        r = self.scr._insert_free_row("C")
        r.set_val("retenue", "-500")
        self.scr._on_row_edit(r.cell_key("retenue"))
        self.assertEqual(r.val("retenue"), "500")

    # ---------- N/BASE · TAUX عرض فقط (§9) ----------
    def test_free_nbase_taux_do_not_autocalculate(self):
        net0 = self.scr._calc_result.net_a_payer
        r = self._free("A", nbase="10", taux="100")     # بلا gain/retenue
        self.assertIsNone(r.entry())                    # لا NBASE×TAUX ضمنيّ
        self.assertEqual(self.scr._calc_result.net_a_payer, net0)

    # ---------- بلا رمادي (§29) ----------
    def test_choice_cell_styled_as_yellow_not_gray(self):
        self.scr._add_row("prime")
        r = [x for x in self.scr._rows if x.kind == "prime"][-1]
        ss = r.widgets["soumis"].styleSheet()
        self.assertIn("QComboBox", ss)
        self.assertIn("border-radius:0", ss)          # مسطّح، لا حافة نافرة
        self.assertTrue(theme.SURFACE.lstrip("#") in ss.replace("#", "")
                        or theme.FIELD_EMPTY.lstrip("#") in ss.replace("#", ""))

    # ---------- خريطة y → (شريحة، فهرس) للإدراج الدقيق (§1/§3) ----------
    def test_gutter_target_segments(self):
        rows = self.scr._visible_body_rows()
        i = {r.kind: k for k, r in enumerate(rows)}
        # حدٌّ فوق الأجر القاعديّ ⇒ لا ＋ (§3A)
        self.assertIsNone(self.scr._gutter_target(T.BODY_TOP - 1.0))
        # بين الأجر و CNAS ⇒ شريحة A
        self.assertEqual(self.scr._gutter_target(
            T.BODY_TOP + i["cnas"] * T.ROW_H - 0.1)[0], "A")
        # بين CNAS و PANIER ⇒ B1
        self.assertEqual(self.scr._gutter_target(
            T.BODY_TOP + i["panier"] * T.ROW_H - 0.1)[0], "B1")
        # بين PANIER و TRANSPORT ⇒ B2
        self.assertEqual(self.scr._gutter_target(
            T.BODY_TOP + i["transport"] * T.ROW_H - 0.1)[0], "B2")
        # بين TRANSPORT و IRG ⇒ B3
        self.assertEqual(self.scr._gutter_target(
            T.BODY_TOP + i["irg"] * T.ROW_H - 0.1)[0], "B3")
        # تحت IRG (وفي الأسطر الفارغة) ⇒ C
        self.assertEqual(self.scr._gutter_target(
            T.BODY_TOP + (i["irg"] + 3) * T.ROW_H)[0], "C")

    # ---------- أزرار ＋/－ على الهامش (§6/§7/§28/§33) ----------
    def _canvas_pt(self, mm_x, row_boundary):
        from PySide6.QtCore import QPoint
        v = self.scr._view()
        ys = 0.0   # Phase E.1
        return QPoint(int(v.x(mm_x)),
                      int(v.y(ys + T.BODY_TOP + row_boundary * T.ROW_H)))

    def test_gutter_plus_shows_in_left_margin(self):
        self.scr._gutter_mouse_move(self._canvas_pt(-5.0, 1))
        self.assertFalse(self.scr._btn_plus.isHidden())
        self.assertIsNotNone(self.scr._plus_target)
        self.assertIn(self.scr._plus_target[0], ("A", "B1", "B2", "B3", "C"))

    def test_gutter_hidden_outside_margin(self):
        self.scr._gutter_mouse_move(self._canvas_pt(-5.0, 1))
        self.scr._gutter_mouse_move(self._canvas_pt(40.0, 1))   # وسط الجدول
        self.assertTrue(self.scr._btn_plus.isHidden())
        self.assertTrue(self.scr._btn_minus.isHidden())

    def test_gutter_minus_only_on_optional_row(self):
        #  §E.5: － في الهامش الأيمن (خارج الجدول)، على الصفوف الاختيارية فقط.
        right = T.CONTENT_W + 5.0
        rows = self.scr._visible_body_rows()
        i_sal = [k for k, r in enumerate(rows) if r.kind == "salaire"][0]
        self.scr._gutter_mouse_move(self._canvas_pt(right, i_sal + 0.5))
        self.assertTrue(self.scr._btn_minus.isHidden())       # ثابت — لا －
        fr = self.scr._insert_free_row("A")
        i_free = self.scr._visible_body_rows().index(fr)
        self.scr._gutter_mouse_move(self._canvas_pt(right, i_free + 0.5))
        self.assertFalse(self.scr._btn_minus.isHidden())
        self.assertIs(self.scr._minus_row, fr)
        # ＋ ما زال في الهامش الأيسر، منفصلاً
        self.scr._gutter_mouse_move(self._canvas_pt(-5.0, i_free))
        self.assertFalse(self.scr._btn_plus.isHidden())
        self.assertTrue(self.scr._btn_minus.isHidden())

    def test_gutter_plus_click_inserts_in_hovered_zone(self):
        self.scr._gutter_mouse_move(self._canvas_pt(-5.0, 1))
        self.scr._plus_target = ("C", 0)
        self.scr._btn_plus.click()
        fr = [r for r in self.scr._rows if r.kind == "free"]
        self.assertTrue(fr and fr[-1].zone == "C")

    def test_gutter_hidden_when_locked(self):
        self.scr._locked = True
        self.scr._gutter_mouse_move(self._canvas_pt(-5.0, 1))
        self.assertTrue(self.scr._btn_plus.isHidden())


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class BulletinTemplateSmartLibelleR3(unittest.TestCase):
    """UX Redesign R3 — LIBELLÉ ذكيّ + تحويل حرّ↔ذكيّ + CODE auto/manual."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="om_r3_")
        os.environ[paths._LOCAL_STATE_ENV_OVERRIDE] = self._tmp
        mod.confirm = lambda *_a, **_k: True
        self.scr = BulletinTemplateScreen(conn=None)
        self.scr._widgets["mois"].setText("OCTOBRE")
        self.scr._widgets["annee"].setText("2026")
        [r for r in self.scr._rows if r.kind == "salaire"][0].set_val("gain",
                                                                      "45000")
        self.scr._recompute()

    def tearDown(self):
        self.scr.deleteLater()
        os.environ.pop(paths._LOCAL_STATE_ENV_OVERRIDE, None)

    def _commit_libelle(self, r, text):
        w = r.widgets["libelle"]
        w.setText(text)
        w.committed.emit(text)
        return [x for x in self.scr._rows if x.rid == r.rid][0]

    # ---------- الحقل الذكيّ ----------
    def test_free_libelle_is_smart_field_with_zone_suggestions(self):
        r = self.scr._insert_free_row("A")
        self.assertIsInstance(r.widgets["libelle"], mod._SmartLibelle)
        sugg = r.widgets["libelle"]._completer.model().stringList()
        self.assertIn("Absence", sugg)
        self.assertIn("IEP / Ancienneté", sugg)

    def test_suggestions_filtered_by_zone(self):
        rc = self.scr._insert_free_row("C")
        sugg = rc.widgets["libelle"]._completer.model().stringList()
        self.assertIn("Avance / Retenue", sugg)
        self.assertNotIn("Absence", sugg)

    # ---------- تحويل حرّ → ذكيّ (§14/§16) ----------
    def test_free_to_smart_on_exact_match(self):
        r = self.scr._insert_free_row("A")
        seg, order = r.segment, r.order
        nr = self._commit_libelle(r, "Absence")
        self.assertEqual(nr.kind, "absence")
        self.assertEqual(nr.zone, "A")
        self.assertEqual((nr.segment, nr.order), (seg, order))   # نفس الموضع (§18)

    def test_alias_match_converts(self):
        r = self.scr._insert_free_row("A")
        self.assertEqual(self._commit_libelle(r, "heures supp").kind, "hs")

    def test_partial_text_stays_free(self):
        r = self.scr._insert_free_row("A")
        nr = self._commit_libelle(r, "Prime spéciale")
        self.assertEqual(nr.kind, "free")

    def test_no_silent_relocation_across_zones(self):
        #  نوع Zone A مكتوبٌ في سطر Zone C ⇒ لا تحويل، لا نقل (§19).
        r = self.scr._insert_free_row("C")
        nr = self._commit_libelle(r, "Absence")
        self.assertEqual((nr.kind, nr.zone), ("free", "C"))

    # ---------- تبديل النوع في المكان (§18) ----------
    def test_smart_type_switch_same_row(self):
        r = self.scr._insert_free_row("A")
        r2 = self._commit_libelle(r, "Absence")
        r2.set_val("qty", "3")
        seg, order = r2.segment, r2.order
        r3 = self._commit_libelle(r2, "Retard")
        self.assertEqual(r3.kind, "retard")
        self.assertEqual((r3.segment, r3.order), (seg, order))
        self.assertEqual(r3.val("qty"), "")           # قيمة غير متوافقة لا تُنقَل

    def test_smart_to_free_on_nonmatch(self):
        r = self.scr._insert_free_row("A")
        r2 = self._commit_libelle(r, "Absence")
        r3 = self._commit_libelle(r2, "Indemnité maison")
        self.assertEqual(r3.kind, "free")
        self.assertEqual(r3.zone, "A")
        self.assertEqual(r3.val("libelle"), "Indemnité maison")

    # ---------- CODE auto / manual (§20) ----------
    def test_code_auto_on_conversion(self):
        r = self.scr._insert_free_row("A")
        self.assertEqual(self._commit_libelle(r, "IEP").val("code"), "IEP")

    def test_code_manual_preserved_across_switch(self):
        r = self.scr._insert_free_row("A")
        r.widgets["code"].setText("Z9")
        r.widgets["code"].textEdited.emit("Z9")        # يعلّم _code_manual
        r2 = self._commit_libelle(r, "Absence")
        self.assertTrue(r2._code_manual)
        self.assertEqual(r2.val("code"), "Z9")

    def test_draft_roundtrip_preserves_code_manual(self):
        r = self.scr._insert_free_row("A")
        r.widgets["code"].setText("Z9")
        r.widgets["code"].textEdited.emit("Z9")
        st = self.scr.draft_state()
        other = BulletinTemplateScreen(conn=None)
        other.apply_draft(st)
        fr = [x for x in other._rows if x.kind == "free"][0]
        self.assertTrue(fr._code_manual)
        other.deleteLater()

    # ---------- IEP فريدة (§24) ----------
    def test_iep_unique_second_conversion_blocked(self):
        a = self.scr._insert_free_row("A")
        self._commit_libelle(a, "IEP")
        b = self.scr._insert_free_row("A")
        nb = self._commit_libelle(b, "IEP")
        self.assertEqual(nb.kind, "free")             # لا IEP ثانية

    def test_iep_hidden_from_other_suggestions_when_present(self):
        a = self.scr._insert_free_row("A")
        self._commit_libelle(a, "IEP")
        b = self.scr._insert_free_row("A")
        sugg = b.widgets["libelle"]._completer.model().stringList()
        self.assertNotIn("IEP / Ancienneté", sugg)


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class BulletinTemplateR4(unittest.TestCase):
    """UX Redesign R4 — تحقّق السطر الحرّ + Smart Next + حرّاس القفل +
    اتّساق المُصيِّر."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="om_r4_")
        os.environ[paths._LOCAL_STATE_ENV_OVERRIDE] = self._tmp
        os.environ[paths._DATA_DIR_ENV_OVERRIDE] = self._tmp
        open(os.path.join(self._tmp, "office_system.db"), "a").close()
        database.init_db()
        mod.confirm = lambda *_a, **_k: True
        self.scr = BulletinTemplateScreen(conn=None)
        self._fill_ident()

    def tearDown(self):
        self.scr.deleteLater()
        for k in (paths._LOCAL_STATE_ENV_OVERRIDE, paths._DATA_DIR_ENV_OVERRIDE):
            os.environ.pop(k, None)

    def _fill_ident(self):
        w = self.scr._widgets
        for k, v in {"emp_raison_sociale": "SARL X", "emp_adresse": "12 RUE",
                     "emp_cnas": "16 412 078 56", "mois": "OCTOBRE",
                     "annee": "2026", "id_nom": "BENALI", "id_prenom": "Karim",
                     "id_lieu_naissance": "ALGER",
                     "id_fonction": "COMPTABLE"}.items():
            w[k].setText(v)
        w["id_date_naissance"].set_iso("1990-05-10")
        w["id_date_embauche"].set_iso("2016-06-14")
        [r for r in self.scr._rows if r.kind == "salaire"][0].set_val("gain",
                                                                      "45000")
        self.scr._recompute()

    # ---------- تحقّق السطر الحرّ (§37) ----------
    def test_empty_free_row_ignored(self):
        self.scr._insert_free_row("A")
        self.scr._recompute()
        self.assertTrue(self.scr.validate().ready_for_final)

    def test_free_row_libelle_only_is_incomplete(self):
        r = self.scr._insert_free_row("A")
        r.set_val("libelle", "Prime")
        self.scr._recompute()
        v = self.scr.validate()
        self.assertFalse(v.ready_for_final)
        self.assertTrue(v.incomplete_rows)

    def test_free_row_both_gain_and_retenue_invalid(self):
        #  مسوّدة قديمة تحمل الحقلين معاً (يمنعهما الإدخال الحيّ) — نتجاوز
        #  الفرض الحيّ بكتم المفتاحين.
        r = self.scr._insert_free_row("A")
        self.scr._suspend |= {r.cell_key("gain"), r.cell_key("retenue")}
        r.set_val("gain", "1000")
        r.set_val("retenue", "200")
        self.scr._suspend = set()
        self.scr._recompute()
        v = self.scr.validate()
        self.assertTrue(any(p.kind == "invalid" for p in v.invalid_fields))

    # ---------- Smart Next (§27) ----------
    def test_smart_next_carries_free_prime_drops_free_retenue(self):
        pr = self.scr._insert_free_row("A")
        pr.set_val("libelle", "Prime fidélité")
        pr.set_val("gain", "6000")
        av = self.scr._insert_free_row("C")
        av.set_val("libelle", "Avance perso")
        av.set_val("retenue", "3000")
        self.scr._recompute()
        self.scr._on_save()
        self.scr.create_next_period_work()
        kinds = [(r.kind, r.val("libelle")) for r in self.scr._rows
                 if r.kind == "free"]
        self.assertIn(("free", "Prime fidélité"), kinds)
        self.assertNotIn(("free", "Avance perso"), kinds)
        self.assertEqual(self.scr._widgets["mois"].text(), "NOVEMBRE")

    # ---------- حرّاس القفل (§28/§29) ----------
    def test_lock_keeps_combobox_enabled_but_inert(self):
        from PySide6.QtWidgets import QComboBox
        self.scr._add_row("prime")
        self.scr._recompute()
        self.scr._set_locked(True)
        combos = [w for w in self.scr._widgets.values()
                  if isinstance(w, QComboBox)]
        self.assertTrue(combos)
        for c in combos:
            self.assertTrue(c.isEnabled())          # لا رمادي (§29)
        self.assertFalse(self.scr._add_row("prime"))  # البنية محروسة
        # سهم LIBELLÉ الذكيّ معطَّل في القفل
        for w in self.scr._widgets.values():
            if isinstance(w, mod._SmartLibelle):
                self.assertFalse(w._arrow.isEnabled())

    def test_unlock_reenables_smart_arrow(self):
        self.scr._add_row("iep")
        self.scr._set_locked(True)
        self.scr._set_locked(False)
        for w in self.scr._widgets.values():
            if isinstance(w, mod._SmartLibelle):
                self.assertTrue(w._arrow.isEnabled())

    # ---------- اتّساق المُصيِّر (§36) ----------
    def test_free_row_reaches_renderer_input(self):
        r = self.scr._insert_free_row("A")
        r.set_val("libelle", "PRIME SPECIALE")
        r.set_val("gain", "7000")
        self.scr._recompute()
        pin = self.scr._build_input()
        self.assertTrue(any(p.libelle == "PRIME SPECIALE" and p.montant == 7000
                            for p in pin.primes))


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class BulletinTemplatePhaseE(unittest.TestCase):
    """Phase E — توحيد بصريّ/هندسيّ: زوم · لا رمادي · خطوط · ＋/－ · NET ·
    اتّساق الشاشة مع المُصيِّر."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="om_e_")
        os.environ[paths._LOCAL_STATE_ENV_OVERRIDE] = self._tmp
        mod.confirm = lambda *_a, **_k: True
        self.scr = BulletinTemplateScreen(conn=None)
        self.scr._scroll.viewport().resize(950, 1250)
        w = self.scr._widgets
        w["mois"].setText("OCTOBRE"); w["annee"].setText("2026")
        [r for r in self.scr._rows if r.kind == "salaire"][0].set_val("gain",
                                                                      "45000")
        self.scr._recompute()

    def tearDown(self):
        self.scr.deleteLater()
        os.environ.pop(paths._LOCAL_STATE_ENV_OVERRIDE, None)

    def _conv(self, zone, libelle, **cells):
        r = self.scr._insert_free_row(zone)
        r.widgets["libelle"].setText(libelle)
        r.widgets["libelle"].committed.emit(libelle)
        nr = [x for x in self.scr._rows if x.rid == r.rid][0]
        for c, v in cells.items():
            nr.set_val(c, v)
        self.scr._recompute()
        return nr

    # ---------- §2 زوم: لا شيء يخرج من الجدول ----------
    def test_no_widget_escapes_table_at_any_zoom(self):
        self._conv("A", "HS", qty="10", coef="100%")
        self._conv("A", "Absence", qty="2", mode="Absence (jours)")
        self._conv("A", "Prime x", gain="6000")
        self._conv("C", "Avance", montant="5000")
        for zoom in (45, 100, 180, 200, 260):
            self.scr._set_zoom(zoom)
            self.scr._relayout()
            v = self.scr._view()
            ys = 0.0   # Phase E.1
            ty0 = v.y(ys + T.BODY_TOP)
            ty1 = v.y(ys + T.BODY_TOP + self.scr._n_body_drawn() * T.ROW_H)
            for row in self.scr._visible_body_rows():
                for cell, wdg in row.widgets.items():
                    g = wdg.geometry()
                    f0, f1, _ = T._colf(row.column(cell))
                    cx0 = v.x(f0 * T.CONTENT_W)
                    cx1 = v.x(f1 * T.CONTENT_W)
                    self.assertGreaterEqual(g.left(), cx0 - 3,
                                            f"{zoom}% {row.kind}.{cell} x")
                    self.assertLessEqual(g.right(), cx1 + 3,
                                         f"{zoom}% {row.kind}.{cell} x")
                    self.assertGreaterEqual(g.top(), ty0 - 3,
                                            f"{zoom}% {row.kind}.{cell} y")
                    self.assertLessEqual(g.bottom(), ty1 + 3,
                                         f"{zoom}% {row.kind}.{cell} y")

    # ---------- §3 خلايا الجدول صفراء منذ الفتح ----------
    def test_table_cells_yellow_from_the_start(self):
        sr = [r for r in self.scr._rows if r.kind == "salaire"][0]
        ss = self.scr._widgets[sr.cell_key("gain")].styleSheet()
        self.assertIn(theme.FIELD_EMPTY.lstrip("#"), ss.replace("#", ""))
        fr = self.scr._insert_free_row("A")            # سطر جديد
        for cell in ("code", "libelle", "nbase", "taux", "gain", "retenue"):
            ss = self.scr._widgets[fr.cell_key(cell)].styleSheet()
            self.assertIn(theme.FIELD_EMPTY.lstrip("#"),
                          ss.replace("#", ""), cell)

    def test_table_cell_bg_is_always_yellow_never_white(self):
        #  §3: خلفية خلية الجدول FIELD_EMPTY في كلّ الحالات (فارغة/مملوءة)
        #  — لا SURFACE الأبيض كما في الحقول العلوية.
        fr = self.scr._insert_free_row("A")
        fr.set_val("gain", "1234")
        self.scr._style_field(fr.cell_key("gain"))
        ss = self.scr._widgets[fr.cell_key("gain")].styleSheet()
        self.assertIn("background:" + theme.FIELD_EMPTY, ss)
        self.assertNotIn("background:" + theme.SURFACE, ss)

    # ---------- §4 نظام الخطوط ----------
    def test_typography_tokens_defined(self):
        for k in ("header_company", "header_title", "block_labels",
                  "table_header", "table_body", "block_values",
                  "computed_value", "total_row", "net_row"):
            self.assertIn(k, mod._TXT)

    # ---------- §5 ＋ يسار · － يمين ----------
    def test_plus_left_minus_right(self):
        fr = self.scr._insert_free_row("A")
        v = self.scr._view()
        ys = 0.0   # Phase E.1
        i = self.scr._visible_body_rows().index(fr)
        yb = int(v.y(ys + T.BODY_TOP + (i + 0.5) * T.ROW_H))
        # ＋ في الهامش الأيسر
        self.scr._gutter_mouse_move(QPoint(int(v.x(-5.0)), yb))
        self.assertFalse(self.scr._btn_plus.isHidden())
        self.assertLess(self.scr._btn_plus.geometry().right(), int(v.x(0)))
        # － في الهامش الأيمن
        self.scr._gutter_mouse_move(QPoint(int(v.x(T.CONTENT_W + 5)), yb))
        self.assertFalse(self.scr._btn_minus.isHidden())
        self.assertGreater(self.scr._btn_minus.geometry().left(),
                           int(v.x(T.CONTENT_W)))

    # ---------- §6 NET شريط أسود ----------
    def test_net_row_is_black_band(self):
        from PySide6.QtGui import QImage
        self.scr._set_zoom(100)
        v = self.scr._view()
        w = int(v.x0 + v.sheet_w + 60)
        h = int(v.y0 + v.sheet_h + 60)
        self.scr._canvas.resize(w, h)
        self.scr._relayout()
        img = QImage(w, h, QImage.Format_ARGB32)
        img.fill(0xFFFFFFFF)
        self.scr._canvas.render(img)
        ys = 0.0   # Phase E.1
        y_net = int(v.y(ys + self.scr._net_y_mm() + T.ROW_H / 2))
        y_tot = int(v.y(ys + self.scr._total_y_mm() + T.ROW_H / 2))

        def band_mean(y):
            xs = range(int(v.x(2)), int(v.x(T.CONTENT_W * 0.45)), 3)
            vals = [sum((img.pixelColor(x, y).red(),
                         img.pixelColor(x, y).green(),
                         img.pixelColor(x, y).blue())) / 3 for x in xs]
            return sum(vals) / len(vals)

        self.assertLess(band_mean(y_net), 60)      # NET شريط أسود
        self.assertGreater(band_mean(y_tot), 200)  # TOTAL صفٌّ فاتح

    # ---------- §8 اتّساق ترتيب المُصيِّر مع مناطق الشاشة ----------
    def test_renderer_row_order_follows_screen_zones(self):
        from programme.payroll import lignes
        from programme.payroll.config_loader import load_params
        import ui.hr.paie.template_simple as TT
        cfg = load_params(date(2026, 10, 1))
        entries = [
            {"type": "salaire_base", "values": {"montant": "45000"}},
            {"type": "iep", "values": {"taux": "0.05"}},                  # Z1
            {"type": "libre", "values": {"libelle": "AVANCE", "montant": "3000",
                                         "est_retenue": "نعم",
                                         "cotisable": "لا", "imposable": "لا"}},  # Z4
        ]
        view = lignes.compute_bulletin(entries, cfg)
        rows = TT._bulletin_rows_from_view(view, {}, jours=30)
        libs = [r["libelle"] for r in rows]
        self.assertLess(libs.index("IND. EXPÉRIENCE PROF."),
                        libs.index("RETENUE SÉCU. SOCIALE"))
        self.assertLess(libs.index("RETENUE SÉCU. SOCIALE"), libs.index("PANIER"))
        self.assertLess(libs.index("PANIER"), libs.index("RETENUE IRG"))
        self.assertLess(libs.index("RETENUE IRG"), libs.index("AVANCE"))

    def test_renderer_pads_to_min_rows(self):
        import ui.hr.paie.template_simple as TT
        self.assertGreaterEqual(len(TT._pad_rows([{"code": "x"}])),
                                TT._RENDER_MIN_BODY_ROWS)

    # ---------- §12 قفل نظيف ----------
    def test_locked_combo_not_gray(self):
        from PySide6.QtWidgets import QComboBox
        self.scr._add_row("hs")
        self.scr._set_locked(True)
        for w in self.scr._widgets.values():
            if isinstance(w, QComboBox):
                self.assertTrue(w.isEnabled())
                self.assertIn(theme.FIELD_EMPTY.lstrip("#"),
                              w.styleSheet().replace("#", ""))


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class BulletinTemplateE1(unittest.TestCase):
    """Phase E.1 — هندسة وثيقة ثابتة بالمليمتر + عقد screen↔PDF."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="om_e1_")
        os.environ[paths._LOCAL_STATE_ENV_OVERRIDE] = self._tmp
        os.environ[paths._DATA_DIR_ENV_OVERRIDE] = self._tmp
        open(os.path.join(self._tmp, "office_system.db"), "a").close()
        database.init_db()
        mod.confirm = lambda *_a, **_k: True
        self.scr = BulletinTemplateScreen(conn=None)
        self.scr._scroll.viewport().resize(950, 1250)
        w = self.scr._widgets
        w["mois"].setText("OCTOBRE"); w["annee"].setText("2026")
        [r for r in self.scr._rows if r.kind == "salaire"][0].set_val("gain",
                                                                      "45000")
        self.scr._recompute()

    def tearDown(self):
        self.scr.deleteLater()
        for k in (paths._LOCAL_STATE_ENV_OVERRIDE, paths._DATA_DIR_ENV_OVERRIDE):
            os.environ.pop(k, None)

    def _conv(self, zone, lib, **cells):
        r = self.scr._insert_free_row(zone)
        r.widgets["libelle"].setText(lib)
        r.widgets["libelle"].committed.emit(lib)
        nr = [x for x in self.scr._rows if x.rid == r.rid][0]
        for c, v in cells.items():
            nr.set_val(c, v)
        self.scr._recompute()
        return nr

    # ---------- §13 هندسة الوثيقة لا تعتمد الزوم ----------
    def test_document_mm_invariant_across_zoom(self):
        from PySide6.QtGui import QFontMetricsF
        self._conv("A", "Heures supplémentaires", qty="5", coef="50%")
        self._conv("C", "Avance", montant="1000")
        self.scr._recompute()
        ref = None
        for zoom in (45, 100, 180, 200, 260):
            self.scr._set_zoom(zoom)
            self.scr._relayout()
            v = self.scr._view()
            rows = self.scr._visible_body_rows()
            i_cnas = [k for k, r in enumerate(rows) if r.kind == "cnas"][0]
            i_irg = [k for k, r in enumerate(rows) if r.kind == "irg"][0]
            hs = [r for r in self.scr._rows if r.kind == "hs"][0]
            wy = self.scr._widgets[hs.cell_key("qty")].y()
            wy_mm = (wy - v.y0) / v.scale                # px → mm (round-trip)
            wleft = self.scr._widgets[hs.cell_key("qty")].x()
            wleft_mm = (wleft - v.x0) / v.scale - T.MARGIN_L
            # حقل هوية حقيقيّ (سطر الميلاد) → mm عبر ascent الخطّ
            dn = self.scr._widgets["id_date_naissance"]
            fm = QFontMetricsF(dn._edit.font() if hasattr(dn, "_edit")
                               else dn.font())
            ident1_mm = (dn.y() + fm.ascent() + v.px(1.2) - v.y0) / v.scale
            got = {
                "ident_row1": round(self.scr._ident_row_y(1), 2),
                "ident_row4": round(self.scr._ident_row_y(4), 2),
                "table_head_y": round(T.TABLE_HEAD_Y, 2),
                "first_body_y": round(T.BODY_TOP, 2),
                "cnas_row_y": round(T.BODY_TOP + i_cnas * T.ROW_H, 2),
                "irg_row_y": round(T.BODY_TOP + i_irg * T.ROW_H, 2),
                "total_y": round(self.scr._total_y_mm(), 2),
                "net_y": round(self.scr._net_y_mm(), 2),
                "hs_cell_top_mm": round(wy_mm, 1),
                "hs_cell_left_mm": round(wleft_mm, 1),
                "ident_dn_baseline_mm": round(ident1_mm, 1),
            }
            if ref is None:
                ref = got
            else:
                for k, val in got.items():
                    self.assertAlmostEqual(
                        val, ref[k], delta=0.6,
                        msg=f"{k} @ {zoom}% = {val}, ref {ref[k]}")

    # ---------- §14 عقد الهندسة المشترك screen ↔ PDF ----------
    def test_screen_pdf_share_one_layout_spec(self):
        import ui.hr.paie.layout_spec as LS
        self.assertEqual(T.MARGIN_L, LS.MARGIN_L_MM)
        self.assertEqual(T.MARGIN_R, LS.MARGIN_R_MM)
        self.assertEqual(T.CONTENT_W, LS.CONTENT_W_MM)
        self.assertEqual(T.ROW_H, LS.ROW_H_MM)
        self.assertEqual(T.BODY_TOP, LS.BODY_TOP_MM)
        self.assertEqual(T.TABLE_HEAD_Y, LS.TABLE_HEAD_Y_MM)
        self.assertEqual(T.IDENT_Y, LS.IDENT_Y_MM)
        self.assertEqual(T.IDENT_H, LS.IDENT_H_MM)
        self.assertEqual(T.BAND_TITLE_Y, LS.BAND_TITLE_Y_MM)
        self.assertEqual(T.BAND_TITLE_H, LS.BAND_TITLE_H_MM)
        self.assertIs(T.COLS, LS.COLS)
        # نفس رموز الخطوط للاثنين
        self.assertIs(mod._TXT, LS.TEXT)
        for tok in LS.TEXT:
            name, pt = LS.pdf_font(tok)
            self.assertTrue(name.startswith("Helvetica"))
            self.assertGreater(pt, 4)

    def test_pdf_row_count_equals_screen_n_body_drawn(self):
        from programme.payroll import lignes
        self._conv("A", "Heures supplémentaires", qty="8", coef="100%")
        self._conv("A", "Prime x", gain="3000")
        self._conv("C", "Avance", montant="2000")
        self.scr._recompute()
        view = self.scr._bulletin_view
        rows = T._bulletin_rows_from_view(view, self.scr._employee_data(),
                                          jours=30)
        self.assertEqual(len(rows), self.scr._n_body_drawn())
        # وأصلها الأيسر: الترويسة والجدول من نفس x المطلق (§10)
        import ui.hr.paie.layout_spec as LS
        self.assertEqual(LS.MAIN_LEFT_MM, 0.0)
        self.assertEqual(LS.ADHERENT_LABEL_X_MM, 0.0)
        self.assertEqual(LS.RAISON_BASELINE_MM, LS.RAISON_BASELINE_MM)

    def test_generated_pdf_opens_and_has_one_page(self):
        import pymupdf
        w = self.scr._widgets
        for k, val in {"emp_raison_sociale": "SARL X", "emp_adresse": "12 RUE",
                       "emp_cnas": "16 412 078 56", "id_nom": "BENALI",
                       "id_prenom": "Karim", "id_lieu_naissance": "ALGER",
                       "id_fonction": "COMPTABLE"}.items():
            w[k].setText(val)
        w["id_date_naissance"].set_iso("1990-05-10")
        w["id_date_embauche"].set_iso("2016-06-14")
        self._conv("A", "Prime", gain="5000")
        self.scr._recompute()
        self.assertTrue(self.scr._on_finalize.__doc__ is not None)
        self.scr._on_finalize()
        pdf = self.scr._final_pdf
        self.assertTrue(pdf and os.path.exists(pdf))
        d = pymupdf.open(pdf)
        self.assertEqual(d.page_count, 1)
        d.close()


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class BulletinTemplateE2(unittest.TestCase):
    """Phase E.2 — إعادة تموضع كلّ عناصر الوثيقة عند تغيّر عرض مساحة العمل
    (إخفاء/إظهار الشريط الجانبيّ · تحريك الفاصل)."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        from PySide6.QtWidgets import QMainWindow
        self._tmp = tempfile.mkdtemp(prefix="om_e2_")
        os.environ[paths._LOCAL_STATE_ENV_OVERRIDE] = self._tmp
        os.environ[paths._DATA_DIR_ENV_OVERRIDE] = self._tmp
        open(os.path.join(self._tmp, "office_system.db"), "a").close()
        database.init_db()
        mod.confirm = lambda *_a, **_k: True
        self._win = QMainWindow()
        self.scr = BulletinTemplateScreen(conn=None)
        self._win.setCentralWidget(self.scr)
        self._win.resize(1120, 900)
        self._win.show()
        self.app.processEvents()
        w = self.scr._widgets
        w["mois"].setText("OCTOBRE"); w["annee"].setText("2026")
        [r for r in self.scr._rows if r.kind == "salaire"][0].set_val("gain",
                                                                      "45000")
        for lib in ("Prime de risque", "Absence"):
            fr = self.scr._insert_free_row("A")
            fr.widgets["libelle"].setText(lib)
            fr.widgets["libelle"].committed.emit(lib)
        [r for r in self.scr._rows if r.kind == "absence"][0].set_val(
            "qty", "1")
        self.scr._recompute()
        self.app.processEvents()

    def tearDown(self):
        self._win.close()
        self._win.deleteLater()
        self.scr.deleteLater()
        for k in (paths._LOCAL_STATE_ENV_OVERRIDE, paths._DATA_DIR_ENV_OVERRIDE):
            os.environ.pop(k, None)

    def _sidebar(self):
        return self.scr._split.widget(1)

    def _hide_sidebar(self):
        self._sidebar().setVisible(False)
        self.scr._split.setSizes([self.scr._split.width(), 0])
        self.app.processEvents()

    def _show_sidebar(self):
        self._sidebar().setVisible(True)
        self.scr._split.setSizes([self.scr.TARGET_W + 80, 240])
        self.app.processEvents()

    def _assert_all_within_bounds(self, tag):
        v = self.scr._view()
        tbl_l, tbl_r = v.x(0), v.x(T.CONTENT_W)
        page_l, page_r = v.x0, v.x0 + v.sheet_w
        for row in self.scr._visible_body_rows():
            for cell, wdg in row.widgets.items():
                g = wdg.geometry()
                f0, f1, _ = T._colf(row.column(cell))
                cx0, cx1 = v.x(f0 * T.CONTENT_W), v.x(f1 * T.CONTENT_W)
                self.assertGreaterEqual(g.left(), cx0 - 4,
                                        f"{tag}: {row.kind}.{cell} left of col")
                self.assertLessEqual(g.right(), cx1 + 4,
                                     f"{tag}: {row.kind}.{cell} right of col")
                self.assertGreaterEqual(g.left(), tbl_l - 4,
                                        f"{tag}: {row.kind}.{cell} < table left")
                self.assertLessEqual(g.right(), tbl_r + 4,
                                     f"{tag}: {row.kind}.{cell} > table right")
                self.assertGreaterEqual(g.left(), page_l - 4,
                                        f"{tag}: {row.kind}.{cell} in gray")
                self.assertLessEqual(g.right(), page_r + 4,
                                     f"{tag}: {row.kind}.{cell} past page")
        for s in self.scr._header_slots:
            g = self.scr._widgets[s.key].geometry()
            self.assertGreaterEqual(g.right(), page_l,
                                    f"{tag}: header {s.key} in gray")
            self.assertLessEqual(g.left(), page_r,
                                 f"{tag}: header {s.key} past page")

    def _assert_gutter_tracks_row(self, tag):
        from PySide6.QtCore import QPoint
        v = self.scr._view()
        rows = self.scr._visible_body_rows()
        fr = [r for r in self.scr._rows if r.kind == "free"][0]
        i = rows.index(fr)
        y = int(v.y(T.BODY_TOP + (i + 0.5) * T.ROW_H))
        self.scr._gutter_mouse_move(QPoint(int(v.x(-5.0)), y))
        self.assertFalse(self.scr._btn_plus.isHidden(), tag)
        self.assertLess(self.scr._btn_plus.geometry().right(), int(v.x(0)),
                        f"{tag}: + not in left gutter")
        self.scr._gutter_mouse_move(QPoint(int(v.x(T.CONTENT_W + 5)), y))
        self.assertIs(self.scr._minus_row, fr, f"{tag}: - wrong row")
        self.assertGreater(self.scr._btn_minus.geometry().left(),
                           int(v.x(T.CONTENT_W)), f"{tag}: - not in right gutter")

    def _run_cycle(self, zoom):
        self.scr._set_zoom(zoom)
        self.app.processEvents()
        self._assert_all_within_bounds(f"z{zoom} A/visible")
        self._assert_gutter_tracks_row(f"z{zoom} A/visible")
        self._hide_sidebar()
        self._assert_all_within_bounds(f"z{zoom} B/hidden")
        self._assert_gutter_tracks_row(f"z{zoom} B/hidden")
        self._show_sidebar()
        self._assert_all_within_bounds(f"z{zoom} C/shown-again")
        self._assert_gutter_tracks_row(f"z{zoom} C/shown-again")

    def test_relayout_on_sidebar_toggle_100(self):
        self._run_cycle(100)

    def test_relayout_on_sidebar_toggle_200(self):
        self._run_cycle(200)

    def test_viewport_resize_triggers_relayout(self):
        #  تصغير/تكبير منفذ العرض مباشرةً (بلا resizeEvent للشاشة) يعيد
        #  التموضع — الخطاف على حدث Resize لمنفذ عرض منطقة التمرير.
        seen = {"n": 0}
        orig = self.scr._on_workspace_geometry_changed

        def spy():
            seen["n"] += 1
            return orig()
        self.scr._on_workspace_geometry_changed = spy
        self._win.resize(1400, 900)
        self.app.processEvents()
        self.assertGreater(seen["n"], 0)
        self._assert_all_within_bounds("after window widen")

    def test_relayout_reentrancy_guard(self):
        #  استدعاءٌ متداخل لا ينفجر ولا يعيد الدخول.
        self.scr._in_relayout = True
        try:
            self.scr._relayout()          # يجب أن يعود بلا عمل
        finally:
            self.scr._in_relayout = False
        self.scr._relayout()
        self._assert_all_within_bounds("after guard test")

    def test_conversion_leaves_no_orphan_widgets(self):
        #  السبب الجذريّ: التحويل حرّ→ذكيّ كان يخلّف widgetات على اللوحة
        #  ليست ضمن أيّ صفّ ⇒ تظهر في المنطقة الرمادية بعد إعادة التموضع.
        from PySide6.QtWidgets import QLineEdit
        for lib in ("Heures supplémentaires", "Absence", "Retard"):
            fr = self.scr._insert_free_row("A")
            fr.widgets["libelle"].setText(lib)
            fr.widgets["libelle"].committed.emit(lib)
        self.scr._recompute()
        self.app.processEvents()
        owned = {id(w) for r in self.scr._rows for w in r.widgets.values()}
        owned |= {id(self.scr._widgets[s.key]) for s in self.scr._header_slots}
        for w in self.scr._canvas.findChildren(QLineEdit):
            if w.parent() is not self.scr._canvas:      # sous-widget d'un champ
                continue
            self.assertIn(id(w), owned,
                          f"widget يتيم على اللوحة: {type(w).__name__} "
                          f"{w.text()!r} @ {w.x()}")


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class BulletinTemplateE3Insert(unittest.TestCase):
    """E.3 — الإدراج الدقيق (segment + order) + ترتيب الحفظ/الاستعادة +
    حارس IEP الفريد + ترحيل قديم."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="om_e3i_")
        os.environ[paths._LOCAL_STATE_ENV_OVERRIDE] = self._tmp
        os.environ[paths._DATA_DIR_ENV_OVERRIDE] = self._tmp
        open(os.path.join(self._tmp, "office_system.db"), "a").close()
        database.init_db()
        mod.confirm = lambda *_a, **_k: True
        self.scr = BulletinTemplateScreen(conn=None)
        self.scr._widgets["mois"].setText("OCTOBRE")
        self.scr._widgets["annee"].setText("2026")
        [r for r in self.scr._rows if r.kind == "salaire"][0].set_val("gain",
                                                                      "45000")
        self.scr._recompute()

    def tearDown(self):
        self.scr.deleteLater()
        for k in (paths._LOCAL_STATE_ENV_OVERRIDE, paths._DATA_DIR_ENV_OVERRIDE):
            os.environ.pop(k, None)

    def _kinds(self):
        return [r.kind for r in self.scr._visible_body_rows()]

    def _seglabels(self, seg):
        return [r.val("libelle") for r in self.scr._segment_rows(seg)]

    # ---------- الحدود (§3) ----------
    def test_no_plus_before_salaire(self):
        self.assertIsNone(self.scr._gutter_target(T.BODY_TOP - 2.0))
        self.assertIsNone(self.scr._gutter_target(T.BODY_TOP + 0.1))  # b==0

    def test_exact_segments_b1_b2_b3(self):
        rows = self.scr._visible_body_rows()
        i = {r.kind: k for k, r in enumerate(rows)}
        #  الحدّ **أسفل** المرتكز مباشرةً (‎-0.15mm‎ فوق سطر ما بعده).
        for below, seg in (("panier", "B1"), ("transport", "B2"),
                           ("irg", "B3")):
            y = T.BODY_TOP + i[below] * T.ROW_H - 0.15
            self.assertEqual(self.scr._gutter_target(y)[0], seg)

    # ---------- الإدراج الدقيق بين صفوف (§1) ----------
    def test_exact_insert_between_optional_rows(self):
        a1 = self.scr._insert_row_at("free", "A", 0); a1.set_val("libelle", "A1")
        a3 = self.scr._insert_row_at("free", "A", 1); a3.set_val("libelle", "A3")
        # ＋ بين A1 و A3 ⇒ index 1
        self.scr._insert_row_at("free", "A", 1)
        self.scr._rows[-1] if False else None
        mid = [r for r in self.scr._segment_rows("A")][1]
        mid.set_val("libelle", "A2")
        self.assertEqual(self._seglabels("A"), ["A1", "A2", "A3"])

    def test_insert_after_deletion_keeps_exact_order(self):
        for lbl in ("A1", "A2", "A3"):
            r = self.scr._insert_row_at("free", "A", len(
                self.scr._segment_rows("A")))
            r.set_val("libelle", lbl)
        a2 = self.scr._segment_rows("A")[1]
        self.scr._remove_row(a2)
        self.assertEqual(self._seglabels("A"), ["A1", "A3"])
        self.scr._insert_row_at("free", "A", 1).set_val("libelle", "NEW")
        self.assertEqual(self._seglabels("A"), ["A1", "NEW", "A3"])

    def test_b_segments_are_all_zone_b(self):
        for seg in ("B1", "B2", "B3"):
            r = self.scr._insert_row_at("free", seg, 0)
            self.assertEqual(r.zone, "B")
        rows = self._kinds()
        self.assertLess(rows.index("cnas"), rows.index("free"))
        self.assertLess(rows.index("free"), rows.index("irg"))

    # ---------- حفظ/استعادة الترتيب الدقيق (§5/§26) ----------
    def test_save_reload_exact_visual_order(self):
        seq = [("A", "A1"), ("A", "A2"), ("B1", "B1x"), ("B2", "B2x"),
               ("B3", "B3x"), ("C", "C1"), ("C", "C2")]
        for seg, lbl in seq:
            r = self.scr._insert_row_at("free", seg,
                                        len(self.scr._segment_rows(seg)))
            r.set_val("libelle", lbl)
        before = [(r.kind, r.val("libelle")) for r in
                  self.scr._visible_body_rows()]
        st = self.scr.draft_state()
        other = BulletinTemplateScreen(conn=None)
        other.apply_draft(st)
        after = [(r.kind, r.val("libelle")) for r in
                 other._visible_body_rows()]
        self.assertEqual(before, after)
        other.deleteLater()

    # ---------- حارس IEP الفريد على مستوى النموذج (§7/§8/§20) ----------
    def test_manual_iep_alias_cannot_create_second(self):
        a = self.scr._insert_free_row("A")
        a.widgets["libelle"].setText("IEP")
        a.widgets["libelle"].committed.emit("IEP")
        self.assertEqual([r.kind for r in self.scr._rows].count("iep"), 1)
        b = self.scr._insert_free_row("A")
        b.widgets["libelle"].setText("Ancienneté")
        b.widgets["libelle"].committed.emit("Ancienneté")
        self.assertEqual([r.kind for r in self.scr._rows].count("iep"), 1)
        self.assertEqual([r for r in self.scr._rows
                          if r.rid == b.rid][0].kind, "free")

    def test_add_row_iep_blocked_when_present(self):
        self.scr._add_row("iep")
        self.scr._add_row("iep")
        self.assertEqual([r.kind for r in self.scr._rows].count("iep"), 1)

    def test_legacy_draft_two_iep_rows_deduped(self):
        legacy = {"header": {"mois": "OCTOBRE", "annee": "2026",
                             "id_nom": "X"},
                  "rows": [
                      {"kind": "salaire", "zone": "A",
                       "cells": {"gain": "45000", "nbase": "30"}},
                      {"kind": "iep", "zone": "A",
                       "cells": {"taux": "0.10", "code": "IEP",
                                 "libelle": "IEP / Ancienneté"}},
                      {"kind": "iep", "zone": "A",
                       "cells": {"taux": "0.05", "code": "IEP",
                                 "libelle": "IEP / Ancienneté"}},
                  ]}
        self.scr.apply_draft(legacy)
        ieps = [r for r in self.scr._rows if r.kind == "iep"]
        self.assertEqual(len(ieps), 1)
        dup = [r for r in self.scr._rows if r._review == "duplicate_unique"]
        self.assertEqual(len(dup), 1)
        self.assertIn("0.05", dup[0].val("libelle"))    # §8: البيانات لم تُفقَد
        v = self.scr.validate()
        self.assertFalse(v.ready_for_final)          # مراجعة مطلوبة
        # المكرَّر لا يُحتسَب: iep واحدة فقط تُغذّي المحرّك
        n_iep_lines = sum(1 for lv in self.scr._bulletin_view.lignes
                          if lv.key == "iep")
        self.assertLessEqual(n_iep_lines, 1)

    def test_legacy_zone_b_maps_to_segment_b3(self):
        legacy = {"header": {"mois": "OCTOBRE", "annee": "2026"},
                  "rows": [
                      {"kind": "salaire", "zone": "A",
                       "cells": {"gain": "45000"}},
                      {"kind": "free", "zone": "B",
                       "cells": {"libelle": "OLD B", "gain": "1000"}},
                  ]}
        self.scr.apply_draft(legacy)
        fr = [r for r in self.scr._rows if r.kind == "free"][0]
        self.assertEqual(fr.segment, "B3")
        self.assertEqual(fr.zone, "B")


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class BulletinTemplateE3Calc(unittest.TestCase):
    """E.3 §16/§17 — تدقيق الحساب الذكيّ بالمحرّك الفعليّ + التكرار."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="om_e3c_")
        os.environ[paths._LOCAL_STATE_ENV_OVERRIDE] = self._tmp
        os.environ[paths._DATA_DIR_ENV_OVERRIDE] = self._tmp
        open(os.path.join(self._tmp, "office_system.db"), "a").close()
        database.init_db()
        mod.confirm = lambda *_a, **_k: True
        self.scr = BulletinTemplateScreen(conn=None)
        w = self.scr._widgets
        w["mois"].setText("OCTOBRE"); w["annee"].setText("2026")
        w["id_date_embauche"].set_iso("2016-06-14")
        sr = [r for r in self.scr._rows if r.kind == "salaire"][0]
        sr.set_val("gain", "45000"); sr.set_val("nbase", "30")
        self.scr._recompute()

    def tearDown(self):
        self.scr.deleteLater()
        for k in (paths._LOCAL_STATE_ENV_OVERRIDE, paths._DATA_DIR_ENV_OVERRIDE):
            os.environ.pop(k, None)

    def _add(self, kind, **cells):
        r = self.scr._add_row(kind)
        for c, v in cells.items():
            r.set_val(c, v)
        self.scr._recompute()
        return r

    def _lines(self, key):
        return [lv for lv in self.scr._bulletin_view.lignes if lv.key == key]

    def _base(self):
        r = self.scr._calc_result
        return (float(r.base_cnas), float(r.base_irg),
                float(self.scr._bulletin_view.e))

    # ---------- IEP ----------
    def test_iep_amount_and_manual_override(self):
        r = self._add("iep")
        self.assertTrue(r.val("taux"))                 # نسبة مقترَحة
        self.assertIsNotNone(r._amount)
        self.assertGreater(r._amount, 0)
        r.set_val("taux", "0.20"); r._iep_manual = True
        self.scr._recompute()
        self.assertEqual(r.val("taux"), "0.20")        # override مُحترَم
        self.assertEqual(len(self._lines("iep")), 1)

    def test_only_one_iep_contributes(self):
        self._add("iep", taux="0.10")
        self.scr._add_row("iep")                       # محجوب
        self.assertLessEqual(len(self._lines("iep")), 1)

    # ---------- HS ----------
    def test_hs_50_and_100_amounts(self):
        b0 = self.scr._calc_result.net_a_payer
        r50 = self._add("hs", qty="10", coef="50%")
        n50 = self.scr._calc_result.net_a_payer
        self.assertGreater(n50, b0)
        self.assertIsNotNone(r50._amount)
        r100 = self._add("hs", qty="10", coef="100%")
        self.assertGreater(self.scr._calc_result.net_a_payer, n50)
        self.assertGreater(r100._amount, r50._amount)  # 100% > 50% لنفس الكمّية

    def test_two_hs_rows_each_own_amount(self):
        a = self._add("hs", qty="4", coef="50%")
        b = self._add("hs", qty="9", coef="50%")
        self.assertNotEqual(a._amount, b._amount)
        tot = sum(float(lv.montant) for lv in self._lines("hs_50"))
        self.assertAlmostEqual(float(a._amount) + float(b._amount), tot, 1)

    # ---------- Absence / Retard: اقتطاع موجب + وعاء ينخفض ----------
    def test_absence_jours_positive_retenue_and_bases(self):
        c0, i0, n0 = self._base()
        r = self._add("absence", qty="3", mode="Absence (jours)")
        c1, i1, n1 = self._base()
        self.assertGreater(r._amount, 0)               # مبلغٌ موجب
        self.assertLess(c1, c0)                        # وعاء CNAS ينخفض
        self.assertLess(n1, n0)                        # الصافي ينخفض
        # يُعرَض في RETENUE لا GAIN
        pr = [p for p in mod.PZ.build(self.scr._bulletin_view).rows
              if p.key in ("abs_jours",)][0]
        self.assertTrue(pr.retenue and not pr.gain)
        self.assertFalse(pr.retenue.startswith("-"))

    def test_absence_heures_and_retard_same_shape(self):
        for kind, cells in (("absence", {"qty": "5",
                                         "mode": "Absence (heures)"}),
                            ("retard", {"qty": "4"})):
            n0 = self.scr._calc_result.net_a_payer
            r = self._add(kind, **cells)
            self.assertGreater(r._amount, 0)
            self.assertLess(self.scr._calc_result.net_a_payer, n0)

    def test_repeated_absence_retard_sum_matches_engine(self):
        self._add("absence", qty="2", mode="Absence (jours)")
        self._add("absence", qty="1", mode="Absence (jours)")
        self._add("retard", qty="3")
        self._add("retard", qty="2")
        for key, amounts in (
                ("abs_jours", [r._amount for r in self.scr._rows
                               if r.kind == "absence"]),
                ("retard", [r._amount for r in self.scr._rows
                            if r.kind == "retard"])):
            eng = sum(float(lv.montant) for lv in self._lines(key))
            self.assertAlmostEqual(sum(float(a) for a in amounts), eng, 1)

    # ---------- Avance ----------
    def test_avance_reduces_net_once_no_base_change(self):
        c0, i0, n0 = self._base()
        self._add("avance", montant="5000")
        c1, i1, n1 = self._base()
        self.assertAlmostEqual(c0, c1, 1)             # لا تمسّ وعاء CNAS
        self.assertAlmostEqual(i0, i1, 1)             # ولا IRG
        self.assertAlmostEqual(n0 - n1, 5000.0, 0)    # مرّة واحدة

    # ---------- Free Gain A/B/C ----------
    def test_free_gain_zone_effects(self):
        c0, i0, _ = self._base()
        ra = self.scr._insert_free_row("A"); ra.set_val("gain", "3000")
        self.scr._recompute()
        c1, i1, _ = self._base()
        self.assertGreater(c1, c0); self.assertGreater(i1, i0)   # A ⇒ CNAS+IRG
        self.scr._remove_row(ra)
        rb = self.scr._insert_free_row("B"); rb.set_val("gain", "3000")
        self.scr._recompute()
        c2, i2, _ = self._base()
        self.assertAlmostEqual(c2, c0, 1)            # B ⇒ لا CNAS
        self.assertGreater(i2, i0)                   # B ⇒ IRG
        self.scr._remove_row(rb)
        n_before = self.scr._calc_result.net_a_payer
        rc = self.scr._insert_free_row("C"); rc.set_val("gain", "3000")
        self.scr._recompute()
        c3, i3, _ = self._base()
        self.assertAlmostEqual(c3, c0, 1); self.assertAlmostEqual(i3, i0, 1)
        self.assertGreater(self.scr._calc_result.net_a_payer, n_before)

    def test_free_retenue_c_reduces_net_once(self):
        n0 = self.scr._calc_result.net_a_payer
        r = self.scr._insert_free_row("C"); r.set_val("retenue", "1500")
        self.scr._recompute()
        self.assertAlmostEqual(n0 - self.scr._calc_result.net_a_payer,
                               1500.0, 0)

    def test_unsupported_free_retenue_ab_not_computed(self):
        n0 = self.scr._calc_result.net_a_payer
        for zone in ("A", "B"):
            r = self.scr._insert_free_row(zone)
            r.set_val("retenue", "2000")              # عبر مسوّدة قديمة فعلياً
            self.scr._recompute()
            self.assertIsNone(r.entry())              # لا تُحتسَب
            self.assertAlmostEqual(self.scr._calc_result.net_a_payer, n0, 1)
            v = self.scr.validate()
            self.assertFalse(v.ready_for_final)       # مُبرَزة للمراجعة
            self.scr._remove_row(r)


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class BulletinTemplateE3UX(unittest.TestCase):
    """E.3 §19/§21/§22 — توسيط المحرِّر + إكمال ذكيّ + مُنتقيات خفيفة."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        import ui2.alerts as _al
        self._tmp = tempfile.mkdtemp(prefix="om_e3ux_")
        os.environ[paths._LOCAL_STATE_ENV_OVERRIDE] = self._tmp
        _isolate_db(self._tmp)
        self._al, self._al_warn = _al, _al.warn
        _al.warn = lambda *_a, **_k: None
        mod.confirm = lambda *_a, **_k: True
        self.scr = BulletinTemplateScreen(conn=None)
        self.scr._scroll.viewport().resize(950, 1250)
        self.scr._widgets["mois"].setText("OCTOBRE")
        self.scr._widgets["annee"].setText("2026")
        [r for r in self.scr._rows if r.kind == "salaire"][0].set_val("gain",
                                                                      "45000")
        self.scr._recompute()

    def tearDown(self):
        self._al.warn = self._al_warn
        self.scr.deleteLater()
        os.environ.pop(paths._LOCAL_STATE_ENV_OVERRIDE, None)

    # ---------- §22 توسيط مستطيل المحرِّر ----------
    def test_editor_rect_vertically_centered(self):
        import ui.hr.paie.layout_spec as LS
        gap = LS.EDITOR_TOP_INSET_MM
        self.assertAlmostEqual(gap, (LS.ROW_H_MM - LS.EDITOR_H_MM) / 2, 4)
        for col in ("code", "libelle", "nbase", "taux", "gain", "retenue"):
            x, y, w, h = LS.editor_rect_mm(col, 0)
            top_gap = y - LS.body_row_y(0)
            bot_gap = (LS.body_row_y(0) + LS.ROW_H_MM) - (y + h)
            self.assertAlmostEqual(top_gap, bot_gap, 3, col)

    def test_editor_centered_at_zooms(self):
        r = self.scr._insert_free_row("A")
        for zoom in (45, 100, 200, 260):
            self.scr._set_zoom(zoom)
            self.scr._relayout()
            v = self.scr._view()
            i = self.scr._visible_body_rows().index(r)
            row_top = v.y(T.BODY_TOP + i * T.ROW_H)
            row_bot = v.y(T.BODY_TOP + (i + 1) * T.ROW_H)
            g = self.scr._widgets[r.cell_key("gain")].geometry()
            self.assertAlmostEqual(g.top() - row_top,
                                   row_bot - g.bottom(), delta=3,
                                   msg=f"zoom {zoom}")

    # ---------- §19 إكمال LIBELLÉ ----------
    def test_right_arrow_completes_current_suggestion(self):
        r = self.scr._insert_free_row("A")
        w = r.widgets["libelle"]
        w.setText("Heures s")
        w._completer.setCompletionPrefix("Heures s")
        ok = w._accept_current_completion()
        self.assertTrue(ok)
        self.assertEqual(w.text(), "Heures supplémentaires")

    def test_enter_keeps_typed_text_not_highlighted(self):
        from PySide6.QtCore import Qt as _Qt
        from PySide6.QtGui import QKeyEvent
        r = self.scr._insert_free_row("A")
        w = r.widgets["libelle"]
        got = []
        w.committed.connect(lambda t: got.append(t))
        w.setText("Prime maison")                     # نصٌّ لا يطابق
        ev = QKeyEvent(QKeyEvent.KeyPress, _Qt.Key_Return, _Qt.NoModifier)
        w.keyPressEvent(ev)
        self.assertEqual(got[-1], "Prime maison")     # كما كُتب
        nr = [x for x in self.scr._rows if x.rid == r.rid][0]
        self.assertEqual(nr.kind, "free")             # بقي حرّاً

    def test_two_char_gate_hides_popup(self):
        r = self.scr._insert_free_row("A")
        w = r.widgets["libelle"]
        w._on_text_edited("H")
        self.assertTrue(w._completer.popup().isHidden())

    # ---------- §21 مُنتقيات خفيفة ----------
    def test_hs_absence_use_inline_choice_not_combobox(self):
        from PySide6.QtWidgets import QComboBox
        r = self.scr._add_row("hs")
        self.assertIsInstance(r.widgets["coef"], mod._InlineChoice)
        self.assertNotIsInstance(r.widgets["coef"], QComboBox)
        a = self.scr._add_row("absence")
        self.assertIsInstance(a.widgets["mode"], mod._InlineChoice)

    def test_inline_choice_pick_updates_and_recomputes(self):
        r = self.scr._add_row("hs")
        r.set_val("qty", "10")
        self.scr._recompute()
        r.widgets["coef"]._pick("100%")
        self.assertEqual(r.val("coef"), "100%")

    def test_inline_choice_yellow_not_gray(self):
        r = self.scr._add_row("hs")
        self.scr._style_field(r.cell_key("coef"))
        ss = r.widgets["coef"].styleSheet()
        self.assertIn("background:" + theme.FIELD_EMPTY, ss)

    def test_inline_choice_locked_blocks_menu(self):
        r = self.scr._add_row("hs")
        self.scr._set_locked(True)
        self.assertFalse(r.widgets["coef"]._arrow.isEnabled())
        r.widgets["coef"]._popup()                    # لا ينفجر، لا قائمة
        self.assertTrue(r.widgets["coef"].isReadOnly())

    # ---------- §14 RETENUE حرّة مخفيّة في Zone A/B ----------
    def test_free_retenue_hidden_zone_a_b(self):
        for zone in ("A", "B"):
            r = self.scr._insert_free_row(zone)
            self.scr._relayout()
            self.assertTrue(r.widgets["retenue"].isHidden(), zone)
        rc = self.scr._insert_free_row("C")
        self.scr._relayout()
        self.assertFalse(rc.widgets["retenue"].isHidden())

    # ---------- §27 Smart Next يحفظ الموضع الدقيق ----------
    def test_smart_next_preserves_segment_order(self):
        w = self.scr._widgets
        for k, v in {"emp_raison_sociale": "SARL", "emp_adresse": "X",
                     "emp_cnas": "16 412 078 56", "id_nom": "BENALI",
                     "id_prenom": "K", "id_lieu_naissance": "ALGER",
                     "id_fonction": "C"}.items():
            w[k].setText(v)
        w["id_date_naissance"].set_iso("1990-05-10")
        w["id_date_embauche"].set_iso("2016-06-14")
        p1 = self.scr._insert_row_at("free", "A", 0)
        p1.set_val("libelle", "PRIME A"); p1.set_val("gain", "3000")
        p2 = self.scr._insert_row_at("free", "B2", 0)
        p2.set_val("libelle", "IND B2"); p2.set_val("gain", "2000")
        self.scr._insert_row_at("absence", "A", 1)      # عرضيّ ⇒ يُحذَف
        self.scr._add_row("iep")
        self.scr._recompute()
        self.scr._on_save()
        self.scr.create_next_period_work()
        segs = {(r.val("libelle"), r.segment) for r in self.scr._rows
                if r.kind == "free"}
        self.assertIn(("PRIME A", "A"), segs)
        self.assertIn(("IND B2", "B2"), segs)          # الموضع محفوظ
        self.assertEqual([r.kind for r in self.scr._rows].count("absence"), 0)
        self.assertEqual([r.kind for r in self.scr._rows].count("iep"), 1)


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
        self._add("prime", libelle="PRIME DE RENDEMENT", gain="8000")
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
        self._add("avance", libelle="AVANCE", montant="")   # بلا مبلغ
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
        _isolate_db(self._tmp)
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
        self.scr._add_row("prime")
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
        if not self._row("prime"):
            self.scr._add_row("prime")
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

    def test_absence_retard_shown_as_positive_retenue(self):
        #  E.3 §9: المُنقِصات تُعرَض اقتطاعاً **موجباً** في RETENUE — لا −GAIN.
        self._full(absence={"qty": "2", "mode": "Absence (jours)"},
                   retard={"qty": "3"})
        for r in self._rows():
            if r["code"] in ("4000", "4010", "4020"):
                self.assertEqual(r["gain"].strip(), "", r)
                self.assertTrue(r["retenue"].strip(), r)
                self.assertFalse(r["retenue"].strip().startswith("-"), r)

    def test_columns_balance_to_displayed_net(self):
        #  E.3 §10/§29: بعد المصالحة  Σ(GAIN معروض) − Σ(RETENUE معروض) == NET.
        self._full(iep={}, hs={"qty": "10", "coef": "50%"},
                   absence={"qty": "1", "mode": "Absence (jours)"},
                   retard={"qty": "2"},
                   avance={"libelle": "AV", "montant": "5000"})
        import ui.hr.paie.presentation as PZ
        pres = PZ.build(self.scr._bulletin_view, jours=26)
        rows = self._rows()
        g = sum(_money(r["gain"]) for r in rows)
        rr = sum(_money(r["retenue"]) for r in rows)
        net = float(self.scr._bulletin_view.e)
        self.assertAlmostEqual(g - rr, net, places=1)
        self.assertAlmostEqual(g, float(pres.total_gain), places=1)
        self.assertAlmostEqual(rr, float(pres.total_retenue), places=1)
        self.assertAlmostEqual(float(pres.total_gain - pres.total_retenue),
                               net, places=1)

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
        os.environ[paths._TRAVAIL_ENV_OVERRIDE] = os.path.join(self._tmp, "travail")
        _isolate_db(self._tmp)
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
        if not any(r.kind == "prime" for r in s._rows):
            s._add_row("prime")
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
        # أزرار ＋/－ على الهامش مخفيّة في القفل (§28)
        self.assertTrue(self.scr._btn_plus.isHidden())
        self.assertTrue(self.scr._btn_minus.isHidden())
        # الزوم يبقى يعمل فوق العمل المقفول
        self.scr._set_zoom(45)
        self.assertEqual(self.scr.zoom, 45)
        # إدراج / حذف صفّ محروسان
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
        self.scr._add_row("free")                         # البنية قابلة للتعديل
        self.assertTrue(any(r.kind == "free" for r in self.scr._rows))
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


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class SaveAsC4(unittest.TestCase):
    """Phase C4 — Save As = استنساخ Work Item مستقلّ، الأصل لا يُلمَس."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="om_c4_")
        os.environ[paths._LOCAL_STATE_ENV_OVERRIDE] = self._tmp
        os.environ[paths._TRAVAIL_ENV_OVERRIDE] = os.path.join(self._tmp, "travail")
        _isolate_db(self._tmp)
        mod.confirm = lambda *_a, **_k: False
        import ui2.alerts as _al
        self._al, self._al_warn = _al, _al.warn
        _al.warn = lambda *_a, **_k: None
        self.scr = BulletinTemplateScreen(conn=None)

    def tearDown(self):
        self._al.warn = self._al_warn
        self.scr.deleteLater()
        for k in (paths._LOCAL_STATE_ENV_OVERRIDE, paths._DATA_DIR_ENV_OVERRIDE,
                  paths._TRAVAIL_ENV_OVERRIDE):
            os.environ.pop(k, None)

    def _row(self, kind):
        return [r for r in self.scr._rows if r.kind == kind][0]

    def _fill_final(self):
        w = self.scr._widgets
        for k, v in {"emp_raison_sociale": "SARL X", "emp_adresse": "12 RUE",
                     "emp_cnas": "16 412 078 56", "mois": "OCTOBRE",
                     "annee": "2026", "id_nom": "BENALI", "id_prenom": "Karim",
                     "id_lieu_naissance": "ALGER",
                     "id_fonction": "COMPTABLE"}.items():
            w[k].setText(v)
        w["id_date_naissance"].set_iso("1990-05-10")
        w["id_date_embauche"].set_iso("2016-06-14")
        self._row("salaire").set_val("gain", "45000")
        self._row("salaire").set_val("nbase", "26")
        if not any(r.kind == "prime" for r in self.scr._rows):
            self.scr._add_row("prime")
        self._row("prime").set_val("gain", "8000")
        self._row("prime").set_val("libelle", "RENDEMENT")
        self.scr._recompute()

    def _emp_name(self, wid):
        import json
        return json.loads(database.get_hr_document(wid)["full_data_json"]
                          )["employee"]["nom"] + " " + json.loads(
            database.get_hr_document(wid)["full_data_json"])["employee"]["prenom"]

    # ---- §32 A ----
    def test_saveas_from_incomplete_creates_independent_copy(self):
        self.scr._widgets["id_nom"].setText("A_NOM")
        self.scr._widgets["mois"].setText("OCTOBRE")
        self.scr._widgets["annee"].setText("2026")
        self._row("salaire").set_val("gain", "40000")
        self.scr._recompute()
        self.scr._on_save()
        wid_a = self.scr._work_id
        self.scr._widgets["id_nom"].setText("B_NOM")     # تعديل بعد حفظ A
        self.scr._on_save_as(label="B")
        wid_b = self.scr._work_id
        self.assertNotEqual(wid_a, wid_b)
        self.assertEqual(self.scr._work_state, "incomplete")
        self.assertIn("A_NOM", self._emp_name(wid_a))     # A لم يتغيّر
        self.assertIn("B_NOM", self._emp_name(wid_b))

    # ---- §32 B ----
    def test_saveas_from_locked_leaves_original_final(self):
        self._fill_final()
        self.scr._on_finalize()
        wid_a = self.scr._work_id
        pdf_a = self.scr._final_pdf
        stamp = os.path.getmtime(pdf_a), os.path.getsize(pdf_a)
        self.assertTrue(self.scr._locked)
        self.scr._on_save_as(label="COPIE")              # بلا فتح القفل
        self.assertNotEqual(self.scr._work_id, wid_a)
        self.assertEqual(self.scr._work_state, "incomplete")
        self.assertFalse(self.scr._locked)               # الشاشة تحرّر النسخة
        rowa = database.get_hr_document(wid_a)
        self.assertEqual(rowa["state"], "final")
        self.assertEqual(rowa["pdf_path"], pdf_a)
        self.assertEqual((os.path.getmtime(pdf_a), os.path.getsize(pdf_a)), stamp)

    # ---- §32 C ----
    def test_saveas_after_unlock_edit_keeps_original(self):
        self._fill_final()
        self.scr._on_finalize()
        wid_a = self.scr._work_id
        pdf_a = self.scr._final_pdf
        mod.confirm = lambda *_a, **_k: True
        self.scr._on_unlock()
        self.scr._widgets["id_prenom"].setText("Kamel")
        self.scr._on_save_as(label="B")
        wid_b = self.scr._work_id
        self.assertNotEqual(wid_a, wid_b)
        self.assertIn("Karim", self._emp_name(wid_a))     # الأصل بالقيَم القديمة
        self.assertIn("Kamel", self._emp_name(wid_b))
        self.assertEqual(database.get_hr_document(wid_a)["pdf_path"], pdf_a)
        self.assertTrue(os.path.exists(pdf_a))
        self.assertIsNone(self.scr._final_pdf)            # النسخة بلا أثر نهائيّ

    # ---- §32 D ----
    def test_refinalize_same_work_after_unlock(self):
        self._fill_final()
        self.scr._on_finalize()
        wid = self.scr._work_id
        pdf = self.scr._final_pdf
        sz0 = os.path.getsize(pdf)
        mod.confirm = lambda *_a, **_k: True
        self.scr._on_unlock()
        self.scr._widgets["id_prenom"].setText("Abdelkader-Djelloul")
        self.scr._recompute()
        mod.confirm = lambda *_a, **_k: False
        self.scr._on_finalize()
        self.assertEqual(self.scr._work_id, wid)
        self.assertEqual(self.scr._final_pdf, pdf)        # نفس الملف
        self.assertEqual(self.scr._work_state, "final")
        self.assertNotEqual(os.path.getsize(pdf), sz0)    # المحتوى تحدّث

    def test_saveas_then_finalize_copy_collision_safe(self):
        self._fill_final()
        self.scr._on_finalize()
        pdf_a = self.scr._final_pdf
        self.scr._on_save_as(label="B")
        self.scr._recompute()
        self.scr._on_finalize()                           # أصدِر النسخة
        self.assertEqual(self.scr._work_state, "final")
        self.assertNotEqual(self.scr._final_pdf, pdf_a)   # مسار مختلف (لا دهس)
        self.assertTrue(os.path.exists(pdf_a))            # ملفّ الأصل باقٍ
        self.assertTrue(os.path.exists(self.scr._final_pdf))

    def test_saveas_new_id_and_one_extra_row(self):
        self._fill_final()
        self.scr._on_save()
        before = len(database.list_hr_documents(screen_key="hr_bulletin_paie"))
        self.scr._on_save_as(label="X")
        after = len(database.list_hr_documents(screen_key="hr_bulletin_paie"))
        self.assertEqual(after, before + 1)


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class SmartNextD(unittest.TestCase):
    """Phase D — Smart Next: كشف الشهر التالي كعمل مستقلّ، الأصل لا يُلمَس."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="om_d_")
        os.environ[paths._LOCAL_STATE_ENV_OVERRIDE] = self._tmp
        os.environ[paths._TRAVAIL_ENV_OVERRIDE] = os.path.join(self._tmp, "travail")
        _isolate_db(self._tmp)
        mod.confirm = lambda *_a, **_k: False
        import ui2.alerts as _al
        self._al, self._al_warn = _al, _al.warn
        _al.warn = lambda *_a, **_k: None
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

    def _fill(self, s=None, *, extras=True, mois="OCTOBRE", annee="2026"):
        s = s or self.scr
        w = s._widgets
        for k, v in {"emp_raison_sociale": "SARL X", "emp_adresse": "12 RUE",
                     "emp_cnas": "16 412 078 56", "mois": mois, "annee": annee,
                     "id_nom": "BENALI", "id_prenom": "Karim",
                     "id_lieu_naissance": "ALGER", "id_matricule": "M-7",
                     "id_fonction": "COMPTABLE"}.items():
            w[k].setText(v)
        w["id_date_naissance"].set_iso("1990-05-10")
        w["id_date_embauche"].set_iso("2016-06-14")
        self._sr(s, "salaire").set_val("gain", "45000")
        self._sr(s, "salaire").set_val("nbase", "26")
        self._sr(s, "panier").set_val("gain", "0")
        self._sr(s, "transport").set_val("gain", "0")
        if not any(r.kind == "prime" for r in s._rows):
            s._add_row("prime")
        self._sr(s, "prime").set_val("libelle", "RENDEMENT")
        self._sr(s, "prime").set_val("gain", "8000")
        self._sr(s, "prime").set_val("soumis", "Net (ni CNAS ni IRG)")
        if extras:
            for kind, cells in (("iep", {}),
                                ("hs", {"qty": "10", "coef": "100%"}),
                                ("absence", {"qty": "2",
                                             "mode": "Absence (jours)"}),
                                ("retard", {"qty": "3"}),
                                ("avance", {"libelle": "AV", "montant": "9000"}),
                                ("autre", {"sens": "Gain", "libelle": "B",
                                           "montant": "1000"})):
                s._add_row(kind)
                for c, v in cells.items():
                    [r for r in s._rows if r.kind == kind][-1].set_val(c, v)
        s._recompute()

    @staticmethod
    def _sr(s, kind):
        return [r for r in s._rows if r.kind == kind][0]

    def _wd(self, wid):
        import json
        return json.loads(database.get_hr_document(wid)["full_data_json"])

    # ---- PERIOD ----
    def test_next_period_simple(self):
        self._fill(extras=False)
        self.assertEqual(self.scr._next_period(), ("NOVEMBRE", "2026"))

    def test_next_period_december_to_january(self):
        self._fill(extras=False, mois="DÉCEMBRE", annee="2026")
        self.assertEqual(self.scr._next_period(), ("JANVIER", "2027"))
        self.scr.create_next_period_work()
        self.assertEqual(self.scr._widgets["mois"].text(), "JANVIER")
        self.assertEqual(self.scr._widgets["annee"].text(), "2027")

    def test_invalid_period_blocks(self):
        self.scr._widgets["mois"].setText("XYZ")
        self.scr._widgets["annee"].setText("2026")
        before = len(database.list_hr_documents(screen_key="hr_bulletin_paie"))
        self.scr.create_next_period_work()
        self.assertIsNone(self.scr._next_period())
        self.assertEqual(
            len(database.list_hr_documents(screen_key="hr_bulletin_paie")),
            before)

    # ---- CARRY ----
    def test_identity_and_stable_structure_carried(self):
        self._fill()
        old_id = None
        self.scr._on_save()
        old_id = self.scr._work_id
        self.scr.create_next_period_work()
        new_id = self.scr._work_id
        self.assertNotEqual(new_id, old_id)
        wd = self._wd(new_id)
        self.assertEqual(wd["employee"]["nom"], "BENALI")
        self.assertEqual(wd["employee"]["prenom"], "Karim")
        self.assertEqual(wd["employee"]["matricule"], "M-7")
        self.assertEqual(wd["employer"]["raison_sociale"], "SARL X")
        self.assertEqual(wd["period"], {"mois": "NOVEMBRE", "annee": "2026"})
        kinds = [r["kind"] for r in wd["rows"]]
        self.assertIn("salaire", kinds)
        self.assertIn("panier", kinds)
        self.assertIn("transport", kinds)
        self.assertIn("prime", kinds)
        prime = [r for r in wd["rows"] if r["kind"] == "prime"][0]
        self.assertEqual(prime["cells"].get("gain"), "8000")
        self.assertEqual(prime["cells"].get("soumis"), "Net (ni CNAS ni IRG)")

    def test_situation_familiale_empty_stays_empty(self):
        self._fill(extras=False)
        self.scr.create_next_period_work()
        self.assertEqual(
            self.scr._widgets["id_situation_familiale"].text(), "")
        self.assertEqual(self._wd(self.scr._work_id)["employee"]
                         ["situation_familiale"], "")

    def test_panier_transport_zero_carried(self):
        self._fill(extras=False)
        self.scr.create_next_period_work()
        self.assertEqual(self._sr(self.scr, "panier").val("gain"), "0")
        self.assertEqual(self._sr(self.scr, "transport").val("gain"), "0")

    # ---- DROP ----
    def test_monthly_rows_dropped(self):
        self._fill()
        self.scr.create_next_period_work()
        kinds = [r.kind for r in self.scr._rows]
        for gone in ("absence", "retard", "hs", "avance", "autre"):
            self.assertNotIn(gone, kinds, gone)
        # لا widgets ميتة لصفوف محذوفة
        self.assertFalse(any(k.startswith("r") and "absence" in k
                             for k in self.scr._widgets))
        self.assertEqual(len(self.scr._nav_order),
                         len([k for k in self.scr._nav_order]))

    # ---- IEP ----
    def test_iep_absent_stays_absent(self):
        self._fill(extras=False)
        self.scr.create_next_period_work()
        self.assertFalse(any(r.kind == "iep" for r in self.scr._rows))

    def test_iep_present_recomputed_no_stale(self):
        self._fill()                                  # فيه IEP
        old_amt = self._row("iep")._amount
        self._row("iep").set_val("taux", "0.99")      # override يدويّ متطرّف
        self.scr._recompute()
        self.scr.create_next_period_work()
        ie = [r for r in self.scr._rows if r.kind == "iep"]
        self.assertTrue(ie)
        ie = ie[-1]
        self.assertFalse(ie._iep_manual)              # override لم يُنقَل
        self.assertNotEqual(ie.val("taux"), "0.99")   # اقتراح جديد
        self.assertTrue(ie.val("taux"))               # نسبة مُقترَحة موضوعة
        self.assertIsNotNone(ie._amount)              # مبلغ محسوب جديد
        wd = self._wd(self.scr._work_id)
        iep_row = [r for r in wd["rows"] if r["kind"] == "iep"][0]
        self.assertFalse(iep_row.get("iep_manual"))

    # ---- COMPUTED ----
    def test_engine_recomputed_for_new_period(self):
        self._fill(extras=False)
        self.scr.create_next_period_work()
        self.assertTrue(self.scr._computed)
        self.assertIsNotNone(self.scr._bulletin_view)
        cfg = load_params(date(2026, 11, 1))
        exp = calc.compute(calc.PaieInput(
            mois="NOVEMBRE", annee="2026", jours=26.0, salaire_base=45000.0,
            panier=0.0, transport=0.0,
            primes=[calc.Prime(code="LIBRE", libelle="RENDEMENT",
                               montant=8000.0, soumis_cotisation=False,
                               imposable=False)]), cfg)
        self.assertEqual(self.scr._bulletin_view.e, exp.net_a_payer)

    # ---- LIFECYCLE ----
    def test_new_work_independent_original_untouched(self):
        self._fill()
        self.scr._on_save()
        old_id = self.scr._work_id
        old_row = database.get_hr_document(old_id)
        self.scr.create_next_period_work()
        self.assertNotEqual(self.scr._work_id, old_id)
        self.assertEqual(self.scr._work_state, "incomplete")
        self.assertFalse(self.scr._locked)
        self.assertFalse(self.scr._has_final_artifacts)
        self.assertIsNone(self.scr._final_docx)
        self.assertIsNone(self.scr._final_pdf)
        self.assertEqual(database.get_hr_document(old_id)["full_data_json"],
                         old_row["full_data_json"])   # الأصل لم يتغيّر
        self.assertEqual(self._wd(self.scr._work_id)["source_work_id"], old_id)

    def test_smart_next_from_locked_original(self):
        self._fill(extras=False)
        self.scr._on_finalize()
        old_id, old_pdf = self.scr._work_id, self.scr._final_pdf
        stamp = os.path.getmtime(old_pdf), os.path.getsize(old_pdf)
        self.assertTrue(self.scr._locked)
        self.scr.create_next_period_work()            # بلا فتح القفل
        self.assertNotEqual(self.scr._work_id, old_id)
        self.assertFalse(self.scr._locked)            # النسخة قابلة للتحرير
        row_old = database.get_hr_document(old_id)
        self.assertEqual(row_old["state"], "final")
        self.assertEqual((os.path.getmtime(old_pdf),
                          os.path.getsize(old_pdf)), stamp)

    def test_smart_next_from_dirty_saves_original_first(self):
        self._fill(extras=False)
        self.scr._on_save()
        oid = self.scr._work_id
        self.scr._widgets["id_prenom"].setText("Kamel")   # dirty
        self.assertTrue(self.scr.has_unsaved_changes())
        self.scr.create_next_period_work()
        self.assertIn("Kamel", database.get_hr_document(oid)["employee_name"])
        self.assertNotEqual(self.scr._work_id, oid)

    # ---- DUPLICATE ----
    def test_duplicate_next_period_not_silently_overwritten(self):
        self._fill(extras=False)
        self.scr._on_save()
        self.scr.create_next_period_work()            # ⇒ NOVEMBRE 2026
        nov_id_1 = self.scr._work_id
        # عُد إلى الأصل واطلب الشهر التالي ثانيةً
        self.scr.load_work(database.get_hr_document(
            [r for r in database.list_hr_documents(screen_key="hr_bulletin_paie")
             if self._wd(r["id"]).get("period", {}).get("mois") == "OCTOBRE"][0]
            ["id"]))
        n_before = len(database.list_hr_documents(screen_key="hr_bulletin_paie"))
        self.scr.create_next_period_work()            # confirm=False ⇒ نسخة جديدة
        self.assertNotEqual(self.scr._work_id, nov_id_1)
        self.assertEqual(
            len(database.list_hr_documents(screen_key="hr_bulletin_paie")),
            n_before + 1)
        # النوفمبر الأوّل ما زال موجوداً كما هو
        self.assertIsNotNone(database.get_hr_document(nov_id_1))

    def test_duplicate_confirm_opens_existing(self):
        self._fill(extras=False)
        self.scr._on_save()
        self.scr.create_next_period_work()
        nov_id = self.scr._work_id
        oct_id = [r["id"] for r in database.list_hr_documents(
            screen_key="hr_bulletin_paie")
            if self._wd(r["id"]).get("period", {}).get("mois") == "OCTOBRE"][0]
        self.scr.load_work(database.get_hr_document(oct_id))
        mod.confirm = lambda *_a, **_k: True          # «افتح الموجود»
        self.scr.create_next_period_work()
        self.assertEqual(self.scr._work_id, nov_id)

    # ---- END TO END (§30) ----
    def test_end_to_end_finalized_then_smart_next(self):
        self._fill()                                  # كلّ الأنواع
        self.scr._on_finalize()
        old_id = self.scr._work_id
        self.assertEqual(self.scr._work_state, "final")
        self.scr.create_next_period_work()
        # carry
        kinds = [r.kind for r in self.scr._rows]
        for keep in ("salaire", "prime", "iep", "panier", "transport"):
            self.assertIn(keep, kinds, keep)
        # drop
        for gone in ("absence", "retard", "hs", "avance", "autre"):
            self.assertNotIn(gone, kinds, gone)
        # recompute + independence + no artifacts
        self.assertTrue(self.scr._computed)
        self.assertNotEqual(self.scr._work_id, old_id)
        self.assertFalse(self.scr._locked)
        self.assertFalse(self.scr._has_final_artifacts)
        self.assertEqual(database.get_hr_document(old_id)["state"], "final")


if __name__ == "__main__":
    unittest.main()
