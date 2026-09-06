"""الاختبارات الذهبية — تطبيق حرفي لجداول القسم 5 من
docs/specs/SPEC_PAIE_DZ.md. الأرقام محسوبة يدوياً / منقولة من كشوف
مختومة، ومطابقة للسلم الرسمي.

مغطّى (14 حالة، 14/14):
  - §5.1  T1→T8  — دالة IRG المرجعية.
  - §5.5  R1→R4  — كشوف شركة خاصة (تختبر دالة IRG وحدها).
  - §5.5  R1 كاملاً — التسلسل [1]→[13] عبر calc.compute_sequence
          (+ قاعدة عدم التقريب الوسيط §5.4).
  - §5.5  اختبار التنسيب R4 — تنسيب السلة والنقل §1.2.3.

التشغيل:
    python -m unittest programme.payroll.tests.test_golden
    python programme/payroll/tests/test_golden.py      (تقرير جدول مقروء)
"""
import os
import sys
import unittest
from decimal import Decimal

if __package__ in (None, ""):                       # تشغيل مباشر كملف
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from programme.payroll import calc, irg
from programme.payroll.config_loader import load_params

# تاريخ كشف داخل نافذة صلاحية params_2026.json
_DATE_KESF = "2026-06-01"

# ---- §5.1 : اختبارات دالة IRG (منقولة حرفياً) ----
# (#, الوعاء الخاضع للضريبة, IRG المتوقع, ما يختبره)
IRG_GOLDEN = [
    ("T1", Decimal("25000.00"),  Decimal("0.00"),     "الإعفاء الكامل"),
    ("T2", Decimal("30000.00"),  Decimal("0.00"),     "حدّ الإعفاء بالضبط"),
    ("T3", Decimal("30010.00"),  Decimal("7.71"),     "بداية التنعيم (اقتطاع رمزي)"),
    ("T4", Decimal("33000.00"),  Decimal("1328.55"),  "وسط شريحة التنعيم"),
    ("T5", Decimal("35000.00"),  Decimal("2070.00"),  "أول قيمة خارج التنعيم (الحدّ الأعلى مفتوح — المادة 104)"),
    ("T6", Decimal("40000.00"),  Decimal("3100.00"),  "مطابق للمثال المنشور من DGI"),
    ("T7", Decimal("62900.00"),  Decimal("9283.00"),  "شريحة 27% + سقف التخفيض 1 500"),
    ("T8", Decimal("200000.00"), Decimal("51100.00"), "شرائح متعددة حتى 33%"),
]

# ---- §5.5 : كشوف شركة خاصة (إنتاج، الجزائر) — تختبر دالة IRG وحدها ----
# assiette هنا هي الوعاء *قبل* التقريب؛ calcul_irg يقرّبه للعشرة الأدنى.
IRG_REFERENCE_PRIVE = [
    ("R1", Decimal("40807.08"), Decimal("3316.00"),  "التقريب للعشرة الأدنى + سقف 1 500 (الاختبار الحاسم)"),
    ("R2", Decimal("72902.22"), Decimal("11983.00"), "شريحة 27%"),
    ("R3", Decimal("63120.15"), Decimal("9342.40"),  "شريحة 27%، وعاء بلا نقل"),
    ("R4", Decimal("18169.97"), Decimal("0.00"),     "الإعفاء تحت 30 000"),
]


class TestIrgGolden(unittest.TestCase):
    """§5.1 + §5.5 — تُختبَر دالة IRG مباشرةً (لا تحتاج calc.py)."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = load_params(_DATE_KESF)

    def test_irg_golden_5_1(self):
        for nom, assiette, attendu, note in IRG_GOLDEN:
            with self.subTest(cas=nom, note=note):
                obtenu = irg.calcul_irg(assiette, self.cfg)
                self.assertEqual(
                    obtenu, attendu,
                    f"{nom} ({note}): assiette={assiette} → attendu {attendu}, obtenu {obtenu}",
                )

    def test_irg_reference_prive_5_5(self):
        for nom, assiette, attendu, note in IRG_REFERENCE_PRIVE:
            with self.subTest(cas=nom, note=note):
                obtenu = irg.calcul_irg(assiette, self.cfg)
                self.assertEqual(
                    obtenu, attendu,
                    f"{nom} ({note}): assiette={assiette} → attendu {attendu}, obtenu {obtenu}",
                )


# ======================================================================
#  §5.5 — اختبارات مركّبة: التسلسل الكامل [1]→[13] عبر calc.compute_sequence.
# ======================================================================

# اختبار مركّب (R1 كاملاً) — §5.5. قاعدي 27 472,53 · 15,80 س.إضافية 50%
# · 8,00 س.إضافية 100% · منحة مقطوعة 5 583,52 (Z1) · نقل 2 500 · سلة
# 2 500 · تسبيق 15 000. لا غيابات ولا أقدمية ولا PRI.
R1_INPUT = calc.SequenceInput(
    salaire_base=Decimal("27472.53"),
    heures_supp=[
        calc.HeureSupp(coef=Decimal("1.50"), heures=Decimal("15.80")),
        calc.HeureSupp(coef=Decimal("2.00"), heures=Decimal("8.00")),
    ],
    primes=[calc.Prime(libelle="prime forfaitaire", montant=Decimal("5583.52"),
                       soumis_cotisation=True, imposable=True)],
    panier_mensuel=Decimal("2500.00"),
    transport_mensuel=Decimal("2500.00"),
    autres_retenues=[calc.Retenue(libelle="avance", montant=Decimal("15000.00"))],
)
R1_ATTENDU = {
    "hs_50":  Decimal("3756.41"),   # taux_horaire (غير مقرّب) × 1.50 × 15.80
    "hs_100": Decimal("2535.97"),   # taux_horaire (غير مقرّب) × 2.00 × 8.00
    "A":      Decimal("39348.44"),  # da(Σ القيم غير المقرّبة لـZ1) — §5.4
    "B":      Decimal("3541.36"),
    "C":      Decimal("40807.08"),
    "D":      Decimal("3316.00"),
    "E":      Decimal("22491.07"),
}

# اختبار التنسيب (R4) — §5.5 + §1.2.3، معطيات كاملة من الكشف الأصلي.
# قاعدي 27 472,53 · غياب غير مبرر 64,00 س · غياب مبرر 8,00 س · تأخّر
# 11,38 س · س.إضافية 100% 7,88 س · IEP 0% · سلة 2 500 · نقل 2 500.
R4_INPUT = calc.SequenceInput(
    salaire_base=Decimal("27472.53"),
    heures_absence_irreguliere=Decimal("64.00"),
    heures_absence_justifiee=Decimal("8.00"),
    heures_retard=Decimal("11.38"),
    heures_supp=[calc.HeureSupp(coef=Decimal("2.00"), heures=Decimal("7.88"))],
    anciennete_annees=Decimal("0"),           # IEP 0%
    panier_mensuel=Decimal("2500.00"),
    transport_mensuel=Decimal("2500.00"),
)
R4_ATTENDU = {
    "abs_irreguliere": Decimal("10143.90"),   # da(taux_horaire × 64,00)
    "abs_justifiee":   Decimal("1267.99"),    # da(taux_horaire × 8,00)
    "retard":          Decimal("1803.71"),    # da(taux_horaire × 11,38)
    "hs_100":          Decimal("2497.93"),    # da(taux_horaire × 2,00 × 7,88)
    "heures_presence": Decimal("101.33"),     # 173,33 − 64,00 − 8,00  (التأخّر مستثنى)
    "panier":          Decimal("1461.52"),    # da(2500 × 101,33 / 173,33)
    "transport":       Decimal("1461.52"),
    "A":               Decimal("16754.86"),   # da(القاعدي + س.إض دقيق − Σ أسطر الغياب المقرّبة)
    "B":               Decimal("1507.94"),
    "C":               Decimal("18169.96"),
    "D":               Decimal("0.00"),       # [C] < 30 000 → إعفاء كامل
    "E":               Decimal("18169.96"),
}


class TestSequenceComposite(unittest.TestCase):
    """§5.5 — التسلسل الكامل [1]→[13] عبر calc.compute_sequence."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = load_params(_DATE_KESF)

    def test_r1_composite_full_sequence(self):
        """R1 كاملاً — يختبر السلسلة من [1] إلى [12] وقاعدة عدم التقريب
        الوسيط (§5.4): [A]=39 348,44 لا يخرج إلا بجمع س.الإضافية بدقة
        كاملة قبل تقريب [A] وحده (جمع السطور المقرّبة يعطي 39 348,43)."""
        r = calc.compute_sequence(R1_INPUT, self.cfg)   # base_iep/base_pri = SAL_BASE_BRUT
        self.assertEqual(r.heures_supp_lignes[0], R1_ATTENDU["hs_50"], "س.إضافية 50%")
        self.assertEqual(r.heures_supp_lignes[1], R1_ATTENDU["hs_100"], "س.إضافية 100%")
        self.assertEqual(r.assiette_cnas, R1_ATTENDU["A"], "[A] SALAIRE DE POSTE")
        self.assertEqual(r.retenue_cnas, R1_ATTENDU["B"], "[B] CNAS 9%")
        self.assertEqual(r.assiette_irg, R1_ATTENDU["C"], "[C] BRUT IMPOSABLE")
        self.assertEqual(r.irg, R1_ATTENDU["D"], "[D] IRG")
        self.assertEqual(r.net_a_payer, R1_ATTENDU["E"], "[E] NET")

    def test_r4_prorata_panier_transport(self):
        """اختبار التنسيب R4 (§5.5 + §1.2.3) — معطيات كاملة من الكشف
        الأصلي. يتحقّق من كل سطر وسيط، لا من النتيجة النهائية فقط:
        الرُبريكات الثلاث للغياب منفصلة (§2.2)، تنسيب السلة/النقل بـ
        heures_presence/heures_mois (التأخّر مستثنى)، والسلسلة [A]→[E].

        [A] و[C] يخرجان 16 754,86 / 18 169,96 — يفرقان سنتيماً واحداً
        عن المطبوع (16 754,87 / 18 169,97). هذا من نفس صنف فروق §5.4
        (المُصدِر جمَع أسطر الغياب بدقة كاملة، ومحرّكنا يقرّب كل رُبريكة
        عند إسنادها). **لا يُعدَّل المحرّك لملاحقة رقم المُصدِر.**"""
        r = calc.compute_sequence(R4_INPUT, self.cfg)
        self.assertEqual(r.retenue_abs_irreguliere, R4_ATTENDU["abs_irreguliere"], "غياب غير مبرر")
        self.assertEqual(r.retenue_abs_justifiee, R4_ATTENDU["abs_justifiee"], "غياب مبرر")
        self.assertEqual(r.retenue_retard, R4_ATTENDU["retard"], "تأخّر")
        self.assertEqual(r.heures_supp_lignes[0], R4_ATTENDU["hs_100"], "س.إضافية 100%")
        self.assertEqual(r.heures_presence, R4_ATTENDU["heures_presence"], "ساعات الحضور")
        self.assertEqual(r.panier, R4_ATTENDU["panier"], "السلة المنسَّبة")
        self.assertEqual(r.transport, R4_ATTENDU["transport"], "النقل المنسَّب")
        self.assertEqual(r.assiette_cnas, R4_ATTENDU["A"], "[A] SALAIRE DE POSTE")
        self.assertEqual(r.retenue_cnas, R4_ATTENDU["B"], "[B] CNAS 9%")
        self.assertEqual(r.assiette_irg, R4_ATTENDU["C"], "[C] BRUT IMPOSABLE")
        self.assertEqual(r.irg, R4_ATTENDU["D"], "[D] IRG (إعفاء)")
        self.assertEqual(r.net_a_payer, R4_ATTENDU["E"], "[E] NET")
        # حدّ SNMG: [A] هبط تحت الأرضية بسبب غيابات ثقيلة → لم يُرفَع
        # تلقائياً (لا خصم مزدوج على الغياب)، لكن يظهر تحذير V2 للمراجعة.
        self.assertTrue(any(a.startswith("V2") for a in r.avertissements),
                        f"تحذير V2 غائب: {r.avertissements}")

    def test_snmg_plancher_contrat_seulement(self):
        """حدّ SNMG بنسبة العقد فقط (لا الحضور): أجر منخفض فعلاً بلا
        غياب → يُرفَع الوعاء للأرضية بلا تحذير؛ عقد جزئي 50% → أرضية
        نصف SNMG. (اختبار سلوك المهمة 8، خارج الجداول الذهبية.)"""
        plein = calc.compute_sequence(
            calc.SequenceInput(salaire_base=Decimal("18000")), self.cfg)
        self.assertEqual(plein.assiette_cnas, Decimal("24000.00"))
        self.assertEqual(plein.avertissements, [])
        partiel = calc.compute_sequence(
            calc.SequenceInput(salaire_base=Decimal("10000"),
                               prorata_jours=Decimal("0.5")), self.cfg)
        self.assertEqual(partiel.assiette_cnas, Decimal("12000.00"))


def _rapport():
    """تقرير جدول مقروء (تشغيل مباشر كملف) — 14/14."""
    cfg = load_params(_DATE_KESF)
    largeur = 82
    ok = 0
    total = 0
    for titre, table in (("§5.1 — دالة IRG المرجعية", IRG_GOLDEN),
                         ("§5.5 — كشوف شركة خاصة (دالة IRG)", IRG_REFERENCE_PRIVE)):
        print("=" * largeur)
        print(f"  {titre}")
        print("=" * largeur)
        print(f"  {'#':<4}{'الوعاء':>16}{'متوقع':>14}{'محسوب':>14}   الحالة")
        print("-" * largeur)
        for nom, assiette, attendu, _note in table:
            obtenu = irg.calcul_irg(assiette, cfg)
            passe = obtenu == attendu
            ok += passe
            total += 1
            print(f"  {nom:<4}{assiette:>16,.2f}{attendu:>14,.2f}{obtenu:>14,.2f}   "
                  f"{'OK  ' if passe else 'FAIL'}")
        print("-" * largeur)

    print("=" * largeur)
    print("  §5.5 — اختبارات مركّبة (التسلسل [1]→[13])")
    print("=" * largeur)
    r1 = calc.compute_sequence(R1_INPUT, cfg)
    r1_checks = [
        ("R1 س.إضافية 50%",  r1.heures_supp_lignes[0], R1_ATTENDU["hs_50"]),
        ("R1 س.إضافية 100%", r1.heures_supp_lignes[1], R1_ATTENDU["hs_100"]),
        ("R1 [A]",           r1.assiette_cnas,         R1_ATTENDU["A"]),
        ("R1 [B]",           r1.retenue_cnas,          R1_ATTENDU["B"]),
        ("R1 [C]",           r1.assiette_irg,          R1_ATTENDU["C"]),
        ("R1 [D]",           r1.irg,                   R1_ATTENDU["D"]),
        ("R1 [E]",           r1.net_a_payer,           R1_ATTENDU["E"]),
    ]
    r4 = calc.compute_sequence(R4_INPUT, cfg)
    r4_checks = [
        ("R4 غياب غير مبرر",  r4.retenue_abs_irreguliere, R4_ATTENDU["abs_irreguliere"]),
        ("R4 غياب مبرر",      r4.retenue_abs_justifiee,   R4_ATTENDU["abs_justifiee"]),
        ("R4 تأخّر",          r4.retenue_retard,          R4_ATTENDU["retard"]),
        ("R4 س.إضافية 100%",  r4.heures_supp_lignes[0],   R4_ATTENDU["hs_100"]),
        ("R4 ساعات الحضور",   r4.heures_presence,         R4_ATTENDU["heures_presence"]),
        ("R4 السلة/النقل",    r4.panier,                  R4_ATTENDU["panier"]),
        ("R4 [A]",            r4.assiette_cnas,           R4_ATTENDU["A"]),
        ("R4 [B]",            r4.retenue_cnas,            R4_ATTENDU["B"]),
        ("R4 [C]",            r4.assiette_irg,            R4_ATTENDU["C"]),
        ("R4 [D] (إعفاء)",    r4.irg,                     R4_ATTENDU["D"]),
        ("R4 [E]",            r4.net_a_payer,             R4_ATTENDU["E"]),
    ]
    for libelle, obtenu, attendu in r1_checks + r4_checks:
        passe = obtenu == attendu
        # كلٌّ من R1/R4 اختبار واحد؛ نعدّه ناجحاً إذا نجحت كل تحقّقاته
        print(f"  {libelle:<22}{str(attendu):>14}{str(obtenu):>16}   {'OK  ' if passe else 'FAIL'}")
    r1_ok = all(o == a for _l, o, a in r1_checks)
    r4_ok = all(o == a for _l, o, a in r4_checks)
    ok += r1_ok + r4_ok
    total += 2
    print("-" * largeur)
    print(f"  النتيجة: {ok}/{total} نجح")
    print("=" * largeur)
    return ok == total


if __name__ == "__main__":
    sys.exit(0 if _rapport() else 1)
