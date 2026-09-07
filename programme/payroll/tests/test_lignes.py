"""اختبارات طبقة النطاق ``programme.payroll.lignes`` (أنواع أسطر الكشف).

المحرّك (``calc.py`` / ``irg.py``) غير مُلموس — نتحقّق فقط أنّ التحويل
إلى :class:`SequenceInput` والاشتقاق الجبائي (المنطقة، §2.3.2) والاقتراح
(§1.2.4) صحيحة.
"""
import unittest
from decimal import Decimal

from programme.payroll import config_loader, lignes

CFG = config_loader.load_params("2026-09-01")
D = Decimal


def _view(entries, convention=None):
    return lignes.compute_bulletin(entries, CFG, convention or {"confirme": 1})


class TestAbsenceMechanics(unittest.TestCase):
    def test_retard_ne_reduit_pas_les_heures_de_presence(self):
        """§1.2.3 (مؤكَّد من كشف حقيقي): ساعات التأخّر لا تُطرح من ساعات
        الحضور. غياب 64+8 س + تأخّر 11,38 س → حضور 101,33 لا 89,95."""
        v = _view([
            {"type": "salaire_base", "values": {"montant": "27472.53"}},
            {"type": "abs_heures", "values": {"heures": "64"}},
            {"type": "abs_heures", "values": {"heures": "8"}},
            {"type": "retard", "values": {"heures": "11.38"}},
        ])
        self.assertEqual(v.result.heures_presence, D("101.33"))
        self.assertNotEqual(v.result.heures_presence, D("89.95"))

    def test_panier_prorata_sur_presence_hors_retard(self):
        """نفس المدخلات: سلة 2 500 → 2 500 × 101,33 ÷ 173,33 = 1 461,52
        (مؤكَّد بالسنتيم، §1.2.3)."""
        v = _view([
            {"type": "salaire_base", "values": {"montant": "27472.53"}},
            {"type": "abs_heures", "values": {"heures": "72"}},
            {"type": "retard", "values": {"heures": "11.38"}},
            {"type": "panier", "values": {"montant_mensuel": "2500"}},
        ])
        panier = next(l for l in v.lignes if l.key == "panier")
        self.assertEqual(panier.montant, D("1461.52"))

    def test_jours_et_heures_denominateurs_distincts(self):
        """أيام الغياب ÷ 30 والساعات ÷ 173,33 — لا تحويل بينهما."""
        base = "30000"
        vj = _view([
            {"type": "salaire_base", "values": {"montant": base}},
            {"type": "abs_jours", "values": {"jours": "1"}},
        ])
        vh = _view([
            {"type": "salaire_base", "values": {"montant": base}},
            {"type": "abs_heures", "values": {"heures": "1"}},
        ])
        ligne_jour = next(l for l in vj.lignes if l.key == "abs_jours").montant
        ligne_heure = next(l for l in vh.lignes if l.key == "abs_heures").montant
        self.assertEqual(ligne_jour, D("1000.00"))            # 30000 / 30
        self.assertEqual(ligne_heure, D("173.08"))            # 30000 / 173.33
        self.assertNotEqual(ligne_jour, ligne_heure * 8)      # لا 8 س ليوم


class TestIepSuggestion(unittest.TestCase):
    def test_bareme_s9_ans(self):
        s = lignes.suggest_iep_taux(
            date_entree="2016-06-14", periode="2025-07", cfg=CFG)
        self.assertEqual((s.annees, s.mois), (9, 1))
        self.assertEqual(s.taux, D("0.09"))                   # 9 × 0,01
        self.assertEqual(s.source, "bareme")
        self.assertIn("منذ 14-06-2016", s.texte_anciennete())

    def test_taux_employe_prioritaire(self):
        s = lignes.suggest_iep_taux(
            date_entree="2016-06-14", periode="2025-07", cfg=CFG,
            employe_taux_iep="0.0708")
        self.assertEqual(s.taux, D("0.0708"))
        self.assertEqual(s.source, "employe")

    def test_sous_minimum_donne_zero_avec_raison(self):
        s = lignes.suggest_iep_taux(
            date_entree="2025-01-01", periode="2025-06", cfg=CFG)
        self.assertEqual(s.taux, D("0"))
        self.assertEqual(s.source, "sous_minimum")
        self.assertIn("الحدّ الأدنى", s.raison)

    def test_sans_date_pas_de_suggestion(self):
        s = lignes.suggest_iep_taux(date_entree="", periode="2025-07", cfg=CFG)
        self.assertIsNone(s.taux)
        self.assertEqual(s.source, "sans_date")
        self.assertIn("حدّد تاريخ الدخول", s.texte_anciennete())

    def test_iep_ligne_utilise_le_taux_comme_prime_z1(self):
        """سطر IEP بنسبة 0,09 على قاعدي 40 000 → 3 600، في Z1."""
        v = _view([
            {"type": "salaire_base", "values": {"montant": "40000"}},
            {"type": "iep", "values": {"taux": "0.09"}},
        ])
        iep = next(l for l in v.lignes if l.key == "iep")
        self.assertEqual(iep.montant, D("3600.00"))
        self.assertEqual(iep.zone, "Z1")


class TestZones(unittest.TestCase):
    def test_zone_et_alloc_familiales_en_z3(self):
        """منحة المنطقة والمنح العائلية → Z3 (تحت [D])، لا Z2."""
        v = _view([
            {"type": "salaire_base", "values": {"montant": "40000"}},
            {"type": "zone", "values": {"montant": "1500"}},
            {"type": "alloc_fam", "values": {"montant": "600"}},
        ])
        zmap = {l.key: l.zone for l in v.lignes}
        self.assertEqual(zmap["zone"], "Z3")
        self.assertEqual(zmap["alloc_fam"], "Z3")
        self.assertNotIn("Z2", (zmap["zone"], zmap["alloc_fam"]))

    def test_zones_des_types_courants(self):
        v = _view([
            {"type": "salaire_base", "values": {"montant": "40000"}},
            {"type": "abs_heures", "values": {"heures": "4"}},
            {"type": "retard", "values": {"heures": "2"}},
            {"type": "panier", "values": {"montant_mensuel": "2000"}},
            {"type": "transport", "values": {"montant_mensuel": "1500"}},
            {"type": "avance", "values": {"montant": "5000"}},
            {"type": "syndicat", "values": {"montant": "200"}},
        ])
        zmap = {l.key: l.zone for l in v.lignes}
        self.assertEqual(zmap["salaire_base"], "Z1")
        self.assertEqual(zmap["abs_heures"], "Z1")            # اقتطاع cotisable
        self.assertEqual(zmap["retard"], "Z1")
        self.assertEqual(zmap["panier"], "Z2")
        self.assertEqual(zmap["transport"], "Z2")
        self.assertEqual(zmap["avance"], "Z4")
        self.assertEqual(zmap["syndicat"], "Z4")

    def test_ordre_zones_z1_puis_z2_z3_z4(self):
        v = _view([
            {"type": "salaire_base", "values": {"montant": "40000"}},
            {"type": "syndicat", "values": {"montant": "200"}},
            {"type": "panier", "values": {"montant_mensuel": "2000"}},
            {"type": "zone", "values": {"montant": "1000"}},
        ])
        zones = [l.zone for l in v.lignes]
        self.assertEqual(zones, sorted(zones, key=lignes.ZONE_ORDER.get))


class TestHeuresSupp(unittest.TestCase):
    def test_hs_50_et_100_lignes_distinctes(self):
        v = _view([
            {"type": "salaire_base", "values": {"montant": "173330"}},  # taux_h = 1000
            {"type": "hs_50", "values": {"heures": "10"}},
            {"type": "hs_100", "values": {"heures": "5"}},
        ])
        hs = {l.key: l.montant for l in v.lignes}
        self.assertEqual(hs["hs_50"], D("15000.00"))          # 1000 × 1,5 × 10
        self.assertEqual(hs["hs_100"], D("10000.00"))         # 1000 × 2,0 × 5


if __name__ == "__main__":
    unittest.main(verbosity=2)
