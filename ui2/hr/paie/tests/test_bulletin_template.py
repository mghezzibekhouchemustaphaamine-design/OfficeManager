"""اختبار تثبيت (characterization) لشاشة كشف الراتب المُعاد بناؤها فوق
PySide6 (``ui2/hr/paie/bulletin_template.py`` — المرحلة 3-أ).

المبدأ: المحرّك (``programme.payroll.calc``) لا يُلمَس؛ الشاشتان القديمة
والجديدة كلتاهما مُهايئٌ يبني ``calc.PaieInput`` من الحقول ويستدعي
``calc.compute``. هذا الاختبار يثبّت أن **الشاشة الجديدة موصِّل أمين**:
نفس قيَم الحقول → نفس ``calc.PaieInput`` → نفس النتيجة تماماً كاستدعاء
المحرّك مباشرةً، وأن كل خانة من ``FIELD_SLOTS`` تُرسَم بلا استثناء.

التشغيل:
    python -m unittest discover -s ui2/hr/paie/tests
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

# بيانات تجريبية ثابتة (نفس ما يُستعمل في مقارنة الصورة جنباً إلى جنب)
_DATA = {
    "emp_raison_sociale": "SARL DATA NEWS",
    "emp_adresse": "Hai Etadjhiz Sonelgaz 02 Lot05 GUE DE CONSTANTINE ALGER",
    "emp_cnas": "16 412 078 56",
    "mois": "OCTOBRE", "annee": "2026",
    "id_nom": "BENALI", "id_prenom": "Karim",
    "id_num_ss": "18 5030 5123 45", "id_situation_familiale": "M",
    "id_matricule": "MAT-2024-0087", "id_fonction": "TECHNICIEN SUPERIEUR",
    "jours": "30", "salaire_base": "45000",
    "prime0_code": "PRI", "prime0_lib": "PRIME DE RENDEMENT", "prime0_montant": "8000",
    "panier": "3000", "transport": "2500",
}


def _expected_input():
    return calc.PaieInput(
        mois="OCTOBRE", annee="2026", jours=30.0, salaire_base=45000.0,
        panier=3000.0, transport=2500.0,
        primes=[calc.Prime(code="PRI", libelle="PRIME DE RENDEMENT",
                           montant=8000.0, soumis_cotisation=True)],
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

    def _fill(self):
        for k, v in _DATA.items():
            self.scr._widgets[k].setText(v)
        self.scr._recompute()

    # -------- 1) كل خانة موجودة وتُرسَم بلا استثناء --------
    def test_all_slots_have_widgets_and_paint(self):
        import ui.hr.paie.template_simple as tpl
        for slot in tpl.FIELD_SLOTS:
            self.assertIn(slot.key, self.scr._widgets)
        self.scr._relayout()
        img = QImage(900, 1200, QImage.Format_ARGB32)
        self.scr._canvas.resize(900, 1200)
        self.scr._canvas.render(img)            # لا استثناء

    # -------- 2) المُهايئ: حقول → PaieInput → نتيجة مطابقة للمحرّك --------
    def test_mapping_is_faithful_conduit(self):
        self._fill()
        cfg = load_params(date(2026, 10, 1))
        exp = calc.compute(_expected_input(), cfg)
        got = self.scr._calc_result
        for field in ("net_a_payer", "total_gain", "total_retenue",
                      "base_cnas", "retenue_cnas", "base_irg", "retenue_irg"):
            self.assertEqual(getattr(got, field), getattr(exp, field),
                             f"{field} انحرف عن المحرّك")

    # -------- 3) خانة «منحة خاضعة» تغيّر النتيجة (منطقة المنحة) --------
    def test_prime_soumis_toggle_changes_result(self):
        self._fill()
        net_soumis = self.scr._calc_result.net_a_payer
        base_cnas_soumis = self.scr._calc_result.base_cnas
        self.scr._set_prime_soumis(0, False)
        self.assertNotEqual(self.scr._calc_result.base_cnas, base_cnas_soumis)
        # الصافي قد يتغيّر (تحوّل المنحة من Z1 إلى Z2) — على الأقل الوعاء تغيّر
        self.assertLess(self.scr._calc_result.base_cnas, base_cnas_soumis)
        _ = net_soumis

    # -------- 4) «مسح» يفرّغ الحقول ويعيد الحساب --------
    def test_clear_resets(self):
        self._fill()
        self.assertTrue(self.scr._employee_fullname())
        self.scr._on_clear()
        self.assertFalse(self.scr._employee_fullname())
        self.assertEqual(self.scr._widgets["jours"].text(), "30")

    # -------- Phase A: المحرّك عبر lignes.compute_bulletin --------
    def test_engine_view_matches_calc_result(self):
        """‏``lignes.compute_bulletin`` (البنية التحتية للأسطر) يعطي نفس
        [A]/[B]/[C]/[D]/[E] كـ ``calc.compute`` للخانات الثابتة الحالية."""
        self._fill()
        v = self.scr._bulletin_view
        r = self.scr._calc_result
        self.assertIsNotNone(v)
        self.assertEqual(v.a, r.base_cnas)
        self.assertEqual(v.b, r.retenue_cnas)
        self.assertEqual(v.c, r.base_irg)
        self.assertEqual(v.d, r.retenue_irg)
        self.assertEqual(v.e, r.net_a_payer)

    # -------- Phase A: «نتيجة غير محسوبة» ≠ «صفر حقيقي» --------
    def test_not_computable_without_base_salary(self):
        # لا أجر قاعديّ → CNAS/IRG/NET ليست 0,00 بل غير محسوبة
        self.scr._widgets["salaire_base"].setText("")
        self.scr._recompute()
        self.assertFalse(self.scr._computed)
        # panier/transport = 0 لا يجعلها «محسوبة» ولا تُعدّ ناقصة
        self.scr._widgets["panier"].setText("0")
        self.scr._widgets["transport"].setText("0")
        self.scr._recompute()
        self.assertFalse(self.scr._computed)
        # بأجر قاعديّ موجب → تصبح محسوبة
        self.scr._widgets["salaire_base"].setText("40000")
        self.scr._recompute()
        self.assertTrue(self.scr._computed)

    def test_calculated_cells_are_not_widgets(self):
        # CNAS / IRG / Totaux / Net مرسومة لا حقول ⇒ لا مفاتيح لها في
        # ``_widgets`` ⇒ ليست Tab stops ولا قابلة للتحرير.
        for k in ("cnas", "irg", "total", "net", "cnas_montant", "irg_montant"):
            self.assertNotIn(k, self.scr._widgets)

    # -------- 5) المسوّدة: ذهاب/إياب --------
    def test_draft_roundtrip(self):
        self._fill()
        state = self.scr.draft_state()
        self.assertEqual(state["id_nom"], "BENALI")
        other = BulletinTemplateScreen(conn=None)
        other.apply_draft(state)
        self.assertEqual(other._widgets["salaire_base"].text(), "45000")
        self.assertEqual(other._widgets["prime0_lib"].text(), "PRIME DE RENDEMENT")
        other.deleteLater()


if __name__ == "__main__":
    unittest.main()
