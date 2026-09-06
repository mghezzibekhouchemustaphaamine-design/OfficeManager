"""الاختبارات الذهبية — تطبيق حرفي لجداول القسم 5 من
docs/specs/SPEC_PAIE_DZ.md. الأرقام محسوبة يدوياً / منقولة من كشوف
مختومة، ومطابقة للسلم الرسمي.

مغطّى الآن:
  - §5.1  T1→T8  — دالة IRG المرجعية.
  - §5.5  R1→R4  — كشوف شركة خاصة (تختبر دالة IRG وحدها).

بـ@unittest.expectedFailure (مكافئ المكتبة القياسية لـ@pytest.mark.xfail —
المشروع لا يعتمد pytest) حتى اكتمال calc.py (التسلسل [1]→[13] §3):
  - §5.5  الاختبار المركّب R1 كاملاً.
  - §5.5  اختبار التنسيب R4 (تنسيب السلة والنقل §1.2.3).

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
#  §5.5 — اختبارات مركّبة (التسلسل [1]→[13]). expectedFailure حتى اكتمال
#  calc.py: تستدعي calc.compute_sequence (غير موجودة بعد) فتفشل الآن،
#  وعند بناء التسلسل الكامل تنجح → unittest يبلّغ "نجاح غير متوقَّع"
#  فنزيل المُزخرِف.
# ======================================================================

# اختبار مركّب (R1 كاملاً) — §5.5
R1_COMPOSITE_INPUT = {
    "salaire_base":        Decimal("27472.53"),
    "hs_50_heures":        Decimal("15.80"),
    "hs_100_heures":       Decimal("8.00"),
    "prime_forfaitaire":   Decimal("5583.52"),   # منحة مقطوعة (regime_irg = BAREME)
    "transport":           Decimal("2500.00"),
    "panier":              Decimal("2500.00"),
    "avance":              Decimal("15000.00"),
}
R1_COMPOSITE_ATTENDU = {
    "hs_50":            Decimal("3756.41"),
    "hs_100":           Decimal("2535.97"),
    "A_salaire_poste":  Decimal("39348.44"),
    "B_cnas":           Decimal("3541.36"),
    "C_brut_imposable": Decimal("40807.08"),
    "D_irg":            Decimal("3316.00"),
    "E_net":            Decimal("22491.07"),
}

# اختبار التنسيب (R4) — §5.5 + §1.2.3
R4_PRORATA_INPUT = {
    "heures_absence_irreguliere": Decimal("64"),
    "heures_absence_justifiee":   Decimal("8"),
    "heures_retard":              Decimal("11.38"),
    # heures_presence = 173.33 − 64 − 8 = 101.33  (التأخّر لا يُخصم:
    # retard_reduit_heures_presence = false)
    "panier_mensuel":            Decimal("2500.00"),
    "transport_mensuel":         Decimal("5000.00"),
}
R4_PRORATA_ATTENDU = {
    "heures_presence": Decimal("101.33"),
    "panier":          Decimal("1461.52"),   # 2500 × 101.33 / 173.33
    "transport":       Decimal("2769.28"),   # 5000 ×  96    / 173.33  (كشف مستقلّ)
    "C_brut_imposable": Decimal("18169.97"),
    "D_irg":           Decimal("0.00"),
    "E_net":           Decimal("18169.96"),
}


class TestSequenceComposite(unittest.TestCase):
    """§5.5 — التسلسل الكامل [1]→[13]. معلَّق (expectedFailure) حتى
    اكتمال calc.py."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = load_params(_DATE_KESF)

    @unittest.expectedFailure
    def test_r1_composite_full_sequence(self):
        """R1 كاملاً (§5.5) — قاعدي 27 472,53 + س.إضافية 50%/100% +
        منحة مقطوعة + نقل + سلة + تسبيق → [C]=40 807,08، [D]=3 316,00،
        [E]=22 491,07. يختبر أيضاً قاعدة عدم التقريب الوسيط (§5.4):
        س.إضافية 50% = 3 756,41 لا تخرج إلا بالأجر الساعي غير المقرّب."""
        res = calc.compute_sequence(self.cfg, R1_COMPOSITE_INPUT)   # noqa: (غير موجودة بعد)
        self.assertEqual(res["hs_50"], R1_COMPOSITE_ATTENDU["hs_50"])
        self.assertEqual(res["hs_100"], R1_COMPOSITE_ATTENDU["hs_100"])
        self.assertEqual(res["A_salaire_poste"], R1_COMPOSITE_ATTENDU["A_salaire_poste"])
        self.assertEqual(res["B_cnas"], R1_COMPOSITE_ATTENDU["B_cnas"])
        self.assertEqual(res["C_brut_imposable"], R1_COMPOSITE_ATTENDU["C_brut_imposable"])
        self.assertEqual(res["D_irg"], R1_COMPOSITE_ATTENDU["D_irg"])
        self.assertEqual(res["E_net"], R1_COMPOSITE_ATTENDU["E_net"])

    @unittest.expectedFailure
    def test_r4_prorata_panier_transport(self):
        """اختبار التنسيب R4 (§5.5 + §1.2.3) — ساعات حضور 101,33 →
        السلة والنقل تُنسَّبان بـ heures_presence / heures_mois،
        [C]=18 169,97، IRG=0، الصافي=18 169,96."""
        res = calc.compute_sequence(self.cfg, R4_PRORATA_INPUT)     # noqa: (غير موجودة بعد)
        self.assertEqual(res["heures_presence"], R4_PRORATA_ATTENDU["heures_presence"])
        self.assertEqual(res["panier"], R4_PRORATA_ATTENDU["panier"])
        self.assertEqual(res["C_brut_imposable"], R4_PRORATA_ATTENDU["C_brut_imposable"])
        self.assertEqual(res["D_irg"], R4_PRORATA_ATTENDU["D_irg"])
        self.assertEqual(res["E_net"], R4_PRORATA_ATTENDU["E_net"])


def _rapport():
    """تقرير جدول مقروء (تشغيل مباشر كملف) — دالة IRG فقط (§5.1 + §5.5)."""
    cfg = load_params(_DATE_KESF)
    largeur = 82
    ok = 0
    total = 0
    for titre, table in (("§5.1 — دالة IRG المرجعية", IRG_GOLDEN),
                         ("§5.5 — كشوف شركة خاصة", IRG_REFERENCE_PRIVE)):
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
    print(f"  النتيجة: {ok}/{total} نجح")
    print("=" * largeur)
    print("  (الاختباران المركّبان §5.5 معلَّقان expectedFailure حتى اكتمال calc.py —")
    print("   يظهران في: python -m unittest programme.payroll.tests.test_golden)")
    return ok == total


if __name__ == "__main__":
    sys.exit(0 if _rapport() else 1)
