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

    def test_taux_employe_precede_le_minimum(self):
        """ترتيب الطبقات: بطاقة العامل تعلو على الحدّ الأدنى — عامل
        بـtaux_iep=0.0708 وأقدمية 8 أشهر → 0.0708 لا 0."""
        s = lignes.suggest_iep_taux(
            date_entree="2025-01-01", periode="2025-09", cfg=CFG,
            employe_taux_iep="0.0708")
        self.assertEqual(s.taux, D("0.0708"))
        self.assertEqual(s.source, "employe")
        self.assertEqual((s.annees, s.mois), (0, 8))

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
    def test_alloc_familiales_et_libre_neutre_en_z3(self):
        """المنح العائلية وسطر حرّ غير خاضع لا للاشتراك ولا للضريبة →
        Z3 (تحت [D])، لا Z2."""
        v = _view([
            {"type": "salaire_base", "values": {"montant": "40000"}},
            {"type": "alloc_fam", "values": {"montant": "600"}},
            {"type": "libre", "values": {
                "libelle": "منحة معفاة", "montant": "1500",
                "est_retenue": "لا", "cotisable": "لا", "imposable": "لا"}},
        ])
        zmap = {l.key: l.zone for l in v.lignes}
        self.assertEqual(zmap["alloc_fam"], "Z3")
        self.assertEqual(zmap["libre"], "Z3")
        self.assertNotIn("Z2", (zmap["alloc_fam"], zmap["libre"]))

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
            {"type": "alloc_fam", "values": {"montant": "1000"}},
        ])
        zones = [l.zone for l in v.lignes]
        self.assertEqual(zones, sorted(zones, key=lignes.ZONE_ORDER.get))


class TestCatalogueClassification(unittest.TestCase):
    """تصنيف السلة/النقل يُقرأ من كتالوج الزبون النشط، لا من ثابت في
    LINE_TYPES — رُصد كشفان حقيقيان (SNAX / DATA NEWS) بنفس المنحتين
    بتصنيفين ضريبيين متعارضين."""

    _ENTRIES = [
        {"type": "salaire_base", "values": {"montant": "40000"}},
        {"type": "panier", "values": {"montant_mensuel": "3000"}},
    ]

    def test_meme_panier_deux_catalogues_zones_differentes_sans_fuite(self):
        # زبون A (SNAX): السلة خاضعة للضريبة → Z2 (المسار الافتراضي)
        va = lignes.compute_bulletin(
            self._ENTRIES, CFG, {"confirme": 1},
            catalogue={"2000": {"cotisable": False, "imposable": True}})
        pa = next(l for l in va.lignes if l.key == "panier")
        self.assertEqual(pa.zone, "Z2")
        self.assertEqual((pa.cotisable, pa.imposable), (0, 1))

        # زبون B (DATA NEWS): نفس السلة غير خاضعة للضريبة → Z3، خارج [C]
        vb = lignes.compute_bulletin(
            self._ENTRIES, CFG, {"confirme": 1},
            catalogue={"2000": {"cotisable": False, "imposable": False}})
        pb = next(l for l in vb.lignes if l.key == "panier")
        self.assertEqual(pb.zone, "Z3")
        self.assertEqual((pb.cotisable, pb.imposable), (0, 0))

        # لا تسرّب بين التشغيلتين: نفس الإدخال، نتيجتان مستقلّتان مختلفتان
        self.assertLess(vb.c, va.c)                     # السلة خارج وعاء IRG عند B
        self.assertEqual(va.a, vb.a)                    # [A] لا يتأثّر (كلاهما غير cotisable)

    def test_panier_cotisable_via_catalogue_entre_dans_A(self):
        v = lignes.compute_bulletin(
            self._ENTRIES, CFG, {"confirme": 1},
            catalogue={"2000": {"cotisable": True, "imposable": True}})
        p = next(l for l in v.lignes if l.key == "panier")
        self.assertEqual(p.zone, "Z1")
        base = lignes.compute_bulletin(self._ENTRIES, CFG, {"confirme": 1},
                                       catalogue={})   # افتراضي Z2
        self.assertGreater(v.a, base.a)                 # السلة صارت داخل [A]

    def test_code_sans_ligne_catalogue_defaut_plus_avertissement_une_fois(self):
        entries = [
            {"type": "salaire_base", "values": {"montant": "40000"}},
            {"type": "avance", "values": {"montant": "1000"}},
            {"type": "avance", "values": {"montant": "500"}},   # نوع قابل للتكرار
        ]
        # كتالوج فيه رموز أخرى لكن ليس "5010" (التسبيق)
        v = lignes.compute_bulletin(
            entries, CFG, {"confirme": 1},
            catalogue={"1000": {"cotisable": True, "imposable": True}})
        av = next(l for l in v.lignes if l.key == "avance")
        self.assertEqual(av.zone, "Z4")                 # الثابت مستعمَل كافتراضي
        warns = [w for w in v.avertissements
                 if "تصنيفاً افتراضياً" in w and "5010" in w]
        self.assertEqual(len(warns), 1)                 # مرّة واحدة رغم سطرَي تسبيق

    def test_catalogue_none_identique_au_constant(self):
        v_none = lignes.compute_bulletin(self._ENTRIES, CFG, {"confirme": 1})
        v_match = lignes.compute_bulletin(
            self._ENTRIES, CFG, {"confirme": 1},
            catalogue={"1000": {"cotisable": True, "imposable": True},
                       "2000": {"cotisable": False, "imposable": True}})
        self.assertEqual([(l.key, l.zone, l.montant) for l in v_none.lignes],
                         [(l.key, l.zone, l.montant) for l in v_match.lignes])
        self.assertEqual((v_none.a, v_none.c, v_none.e),
                         (v_match.a, v_match.c, v_match.e))
        self.assertEqual(v_match.avertissements, [])    # كل الرموز مطابقة


class TestFreeLine(unittest.TestCase):
    def test_v7_rejette_sans_classification(self):
        with self.assertRaises(lignes.FreeLineError):
            lignes.validate_free_line({"libelle": "x", "montant": "100"})
        with self.assertRaises(lignes.FreeLineError):      # imposable ناقص
            lignes.validate_free_line({"cotisable": "نعم", "imposable": "—"})
        self.assertFalse(lignes.free_line_classified({"cotisable": "نعم"}))
        # مصنَّف صراحةً → لا استثناء
        lignes.validate_free_line({"cotisable": "نعم", "imposable": "لا"})
        self.assertTrue(lignes.free_line_classified(
            {"cotisable": "نعم", "imposable": "لا"}))

    def test_saut_vers_les_quatre_zones(self):
        libre = lignes.LINE_TYPES["libre"]
        self.assertEqual(libre.zone(
            {"est_retenue": "لا", "cotisable": "نعم", "imposable": "نعم"}), "Z1")
        self.assertEqual(libre.zone(
            {"est_retenue": "لا", "cotisable": "لا", "imposable": "نعم"}), "Z2")
        self.assertEqual(libre.zone(
            {"est_retenue": "لا", "cotisable": "لا", "imposable": "لا"}), "Z3")
        self.assertEqual(libre.zone(
            {"est_retenue": "نعم", "cotisable": "لا", "imposable": "لا"}), "Z4")

    def test_compute_bulletin_ignore_ligne_non_classee(self):
        base = {"type": "salaire_base", "values": {"montant": "40000"}}
        # غير مصنَّف → لا يظهر في الأسطر ولا يؤثّر
        v0 = _view([base, {"type": "libre",
                           "values": {"libelle": "غامض", "montant": "5000"}}])
        self.assertNotIn("libre", [l.key for l in v0.lignes])
        # مصنَّف Z2 → يظهر بمبلغه في منطقته
        v1 = _view([base, {"type": "libre", "values": {
            "libelle": "منحة خاصة", "montant": "5000",
            "est_retenue": "لا", "cotisable": "لا", "imposable": "نعم"}}])
        libre = next(l for l in v1.lignes if l.key == "libre")
        self.assertEqual(libre.zone, "Z2")
        self.assertEqual(libre.montant, D("5000.00"))
        self.assertEqual(libre.libelle, "منحة خاصة")
        self.assertEqual(libre.sens, "GAIN")

    def test_libre_retenue_va_en_z4(self):
        v = _view([
            {"type": "salaire_base", "values": {"montant": "40000"}},
            {"type": "libre", "values": {
                "libelle": "اقتطاع خاص", "montant": "1200",
                "est_retenue": "نعم", "cotisable": "لا", "imposable": "لا"}},
        ])
        libre = next(l for l in v.lignes if l.key == "libre")
        self.assertEqual(libre.zone, "Z4")
        self.assertEqual(libre.sens, "RETENUE")


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


class TestFieldReview(unittest.TestCase):
    """المراجعة الميدانية لشاشة الكشف — إصلاحات #3 · #4 · #5 · #6."""

    def test_ligne_absence_montre_sa_part_pas_le_total(self):
        """#3 — كل سطر غياب يعرض حصّته هو، ومجموع أسطر Z1 المعروضة =
        [A] بالضبط في وجود عدّة أسطر غياب مختلفة."""
        v = _view([
            {"type": "salaire_base", "values": {"montant": "30000"}},
            {"type": "abs_jours", "values": {"jours": "2"}},
            {"type": "abs_heures", "values": {"heures": "16"}},
            {"type": "retard", "values": {"heures": "5"}},
        ])
        lmap = {l.key: l for l in v.lignes}
        # حصّة السطر = معدّل المحرّك (دقّة كاملة) × كمّية السطر ثم da
        th = v.result.taux_horaire
        tj = v.result.taux_journalier
        from programme.payroll.calc import da
        self.assertEqual(lmap["abs_jours"].montant, da(tj * D("2")))
        self.assertEqual(lmap["abs_jours"].montant, D("2000.00"))    # 30000/30 × 2
        self.assertEqual(lmap["abs_heures"].montant, da(th * D("16")))
        self.assertEqual(lmap["retard"].montant, da(th * D("5")))
        self.assertNotEqual(lmap["abs_heures"].montant, lmap["retard"].montant)
        # المجموع المعروض لـZ1 = [A] بالضبط
        z1 = sum((l.montant if l.sens == "GAIN" else -l.montant)
                 for l in v.lignes if l.zone == "Z1")
        self.assertEqual(z1, v.a)

    def test_ligne_sans_valeur_ignoree(self):
        """#4 — سطر بحقل القيمة فارغاً لا يُحتسَب ولا يظهر (لا 0,00 صامت)."""
        base = {"type": "salaire_base", "values": {"montant": "40000"}}
        for vals in ({}, {"montant": ""}, {"montant": "   "}):
            v = _view([base, {"type": "nuit", "values": vals}])
            self.assertNotIn("nuit", [l.key for l in v.lignes], vals)
        # بقيمة → يظهر
        v = _view([base, {"type": "nuit", "values": {"montant": "1200"}}])
        self.assertIn("nuit", [l.key for l in v.lignes])

    def test_types_uniques_et_repetables(self):
        """#5 — كل الأنواع فريدة عدا التسبيق والسطر الحرّ."""
        repetables = {"avance", "libre"}
        for key, lt in lignes.LINE_TYPES.items():
            self.assertEqual(lt.unique, key not in repetables, key)

    def test_types_supprimes_absents(self):
        """#6 — أُزيلت من السجلّ نهائياً (يغطّيها السطر الحرّ)."""
        for key in ("zone", "interim", "mutuelle", "opposition"):
            self.assertNotIn(key, lignes.LINE_TYPES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
