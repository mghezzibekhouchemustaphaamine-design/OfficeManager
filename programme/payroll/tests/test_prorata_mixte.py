"""اختبارات ``PRORATA_MIXTE`` (Phase E.4 §3) — وضعٌ اتفاقيّ رابعٌ صريح
لتنسيب السلة/النقل يجمع كسر غياب الأيام وكسر غياب الساعات معاً (نسبةً،
لا حالةً تراكميّة)، بينما يبقى سلوك ``AUCUN``/``PRORATA_JOURS``/
``PRORATA_HEURES`` القديم بلا أيّ تغيير (§2/§4 من مواصفة E.4). مرجع
§1.2.3-bis من ``docs/specs/SPEC_PAIE_DZ.md``.

التشغيل:
    python -m unittest programme.payroll.tests.test_prorata_mixte
"""
import unittest
from decimal import Decimal

from programme.payroll import calc
from programme.payroll.config_loader import load_params

_DATE_KESF = "2026-06-01"


def _si(**kw):
    base = dict(salaire_base=Decimal("27472.53"),
               panier_mensuel=Decimal("2500.00"),
               transport_mensuel=Decimal("2500.00"))
    base.update(kw)
    return calc.SequenceInput(**base)


class TestProrataLegacyUnchanged(unittest.TestCase):
    """A.1-A.3 — الأوضاع الثلاثة القديمة بلا أيّ تغيير سلوكيّ."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = load_params(_DATE_KESF)

    def test_prorata_heures_legacy_unchanged(self):
        si = _si(heures_absence_irreguliere=Decimal("64.00"),
                 heures_absence_justifiee=Decimal("8.00"),
                 heures_retard=Decimal("11.38"))
        r = calc.compute_sequence(si, self.cfg,
                                  prorata_panier_transport="PRORATA_HEURES")
        self.assertEqual(r.heures_presence, Decimal("101.33"))
        self.assertEqual(r.panier, Decimal("1461.52"))
        self.assertEqual(r.transport, Decimal("1461.52"))

    def test_prorata_jours_legacy_unchanged(self):
        si = _si(jours_absence=Decimal("3"))
        cfg = self.cfg
        r = calc.compute_sequence(si, cfg,
                                  prorata_panier_transport="PRORATA_JOURS")
        jours_mois = Decimal(str(cfg["jours_mois"]))
        attendu = calc.da(Decimal("2500.00")
                          * (jours_mois - Decimal("3")) / jours_mois)
        self.assertEqual(r.panier, attendu)

    def test_aucun_legacy_unchanged(self):
        si = _si(heures_absence_irreguliere=Decimal("64.00"))
        r = calc.compute_sequence(si, self.cfg,
                                  prorata_panier_transport="AUCUN")
        self.assertEqual(r.panier, Decimal("2500.00"))
        self.assertEqual(r.transport, Decimal("2500.00"))

    def test_default_mode_is_still_prorata_heures(self):
        #  §2: calc.py لا يتغيّر افتراضياً — الوضع الجديد صريحٌ لا ضمنيّ.
        import inspect
        sig = inspect.signature(calc.compute_sequence)
        self.assertEqual(sig.parameters["prorata_panier_transport"].default,
                         "PRORATA_HEURES")


class TestProrataMixte(unittest.TestCase):
    """A.4-A.13 — الوضع الجديد."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = load_params(_DATE_KESF)
        cls.heures_mois = Decimal(str(cls.cfg["heures_mois"]))
        cls.jours_mois = Decimal(str(cls.cfg["jours_mois"]))

    def _mixte(self, si):
        return calc.compute_sequence(si, self.cfg,
                                     prorata_panier_transport="PRORATA_MIXTE")

    def test_hours_only_matches_real_slip(self):
        #  A.4 + §20: نفس حالة R4 الذهبية — تأخّر مستثنًى افتراضياً.
        si = _si(heures_absence_irreguliere=Decimal("64.00"),
                 heures_absence_justifiee=Decimal("8.00"),
                 heures_retard=Decimal("11.38"))
        r = self._mixte(si)
        self.assertEqual(r.heures_presence, Decimal("101.33"))
        self.assertEqual(r.panier, Decimal("1461.52"))
        self.assertEqual(r.transport, Decimal("1461.52"))

    def test_second_real_slip_pattern(self):
        #  §20: نمط ملاحظ ثانٍ — غياب 77,33 س → حضور 96,00 س.
        si = _si(heures_absence_irreguliere=Decimal("77.33"),
                 panier_mensuel=Decimal("5000.00"),
                 transport_mensuel=Decimal("5000.00"))
        r = self._mixte(si)
        self.assertEqual(r.heures_presence, Decimal("96.00"))
        self.assertEqual(r.panier, Decimal("2769.28"))

    def test_days_only(self):
        #  A.5: غياب أيامٍ فقط.
        si = _si(jours_absence=Decimal("2"))
        r = self._mixte(si)
        attendu = calc.da(Decimal("2500.00")
                          * (self.jours_mois - Decimal("2")) / self.jours_mois)
        self.assertEqual(r.panier, attendu)

    def test_mixed_days_and_hours(self):
        #  A.6: أيامٌ وساعات معاً — الكسران يُجمَعان.
        si = _si(jours_absence=Decimal("1"),
                 heures_absence_irreguliere=Decimal("20.00"))
        r = self._mixte(si)
        fraction_j = Decimal("1") / self.jours_mois
        fraction_h = Decimal("20.00") / self.heures_mois
        facteur = Decimal("1") - fraction_j - fraction_h
        attendu = calc.da(Decimal("2500.00") * facteur)
        self.assertEqual(r.panier, attendu)
        self.assertEqual(r.transport, attendu)

    def test_retard_excluded_by_default(self):
        #  A.7: تأخّرٌ وحده — لا يُنقِص الاستحقاق افتراضياً.
        si = _si(heures_retard=Decimal("20.00"))
        r = self._mixte(si)
        self.assertEqual(r.panier, Decimal("2500.00"))
        self.assertEqual(r.heures_presence, self.heures_mois)

    def test_explicit_retard_flag_still_supported(self):
        #  A.8: العلم الاتفاقيّ الصريح (موجودٌ أصلاً في calc.py) يُدرج
        #  التأخّر — يبقى مدعوماً لهذا الوضع أيضاً.
        si = _si(heures_retard=Decimal("20.00"))
        r = calc.compute_sequence(
            si, self.cfg, prorata_panier_transport="PRORATA_MIXTE",
            retard_reduit_heures_presence=True)
        fraction_h = Decimal("20.00") / self.heures_mois
        attendu = calc.da(Decimal("2500.00") * (Decimal("1") - fraction_h))
        self.assertEqual(r.panier, attendu)
        self.assertLess(r.panier, Decimal("2500.00"))

    def test_factor_clamps_at_zero_never_negative_allowance(self):
        #  A.9: غيابٌ أكبر من الشهر كلّه — لا صافي سالب للسلة/النقل.
        si = _si(jours_absence=self.jours_mois * 2)
        r = self._mixte(si)
        self.assertEqual(r.panier, Decimal("0.00"))
        self.assertEqual(r.transport, Decimal("0.00"))
        self.assertGreaterEqual(r.panier, Decimal("0"))

    def test_no_absence_factor_is_one(self):
        #  A.10
        r = self._mixte(_si())
        self.assertEqual(r.panier, Decimal("2500.00"))
        self.assertEqual(r.transport, Decimal("2500.00"))
        self.assertEqual(r.heures_presence, self.heures_mois)

    def test_panier_and_transport_use_same_factor(self):
        #  A.11
        si = _si(heures_absence_irreguliere=Decimal("30.00"),
                 transport_mensuel=Decimal("1000.00"))
        r = self._mixte(si)
        ratio_panier = r.panier / Decimal("2500.00")
        ratio_transport = r.transport / Decimal("1000.00")
        self.assertAlmostEqual(float(ratio_panier), float(ratio_transport), places=4)

    def test_day_deduction_still_uses_jours_mois(self):
        #  A.12: صيغة خصم يوم الغياب المالية بلا تغيير — jours_mois وحده.
        si = _si(jours_absence=Decimal("2"))
        r = self._mixte(si)
        self.assertEqual(r.taux_journalier, Decimal("27472.53") / self.jours_mois)
        self.assertEqual(r.retenue_jours_abs,
                         calc.da(r.taux_journalier * Decimal("2")))

    def test_hour_deduction_still_uses_heures_mois(self):
        #  A.13: صيغة خصم ساعة الغياب المالية بلا تغيير — heures_mois وحده.
        si = _si(heures_absence_irreguliere=Decimal("10.00"))
        r = self._mixte(si)
        self.assertEqual(r.taux_horaire, Decimal("27472.53") / self.heures_mois)
        self.assertEqual(r.retenue_abs_irreguliere,
                         calc.da(r.taux_horaire * Decimal("10.00")))

    def test_no_double_counting_between_deduction_and_prorata(self):
        #  خصم الغياب المالي (retenue_absence) مستقلّ عن كسر التنسيب —
        #  تغيير الوضع الاتفاقيّ لا يمسّ [A]/[E].
        si = _si(heures_absence_irreguliere=Decimal("64.00"),
                 heures_absence_justifiee=Decimal("8.00"))
        r_heures = calc.compute_sequence(
            si, self.cfg, prorata_panier_transport="PRORATA_HEURES")
        r_mixte = self._mixte(si)
        self.assertEqual(r_heures.retenue_absence, r_mixte.retenue_absence)
        self.assertEqual(r_heures.assiette_cnas, r_mixte.assiette_cnas)


if __name__ == "__main__":
    unittest.main()
