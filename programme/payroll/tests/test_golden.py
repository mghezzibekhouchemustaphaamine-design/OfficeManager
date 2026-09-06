"""الاختبارات الذهبية — تطبيق حرفي لجداول القسم 5 من
docs/specs/SPEC_PAIE_DZ.md. الأرقام محسوبة يدوياً ومطابقة للسلم الرسمي.

المرحلة 1: T1→T8 (دالة IRG). الكشف الكامل (5.2) يُضاف في المرحلة 2 مع
calcul.py.

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

from programme.payroll import irg
from programme.payroll.config_loader import load_params

# تاريخ كشف داخل نافذة صلاحية params_2026.json
_DATE_KESF = "2026-06-01"

# ---- القسم 5.1 : اختبارات دالة IRG (منقولة حرفياً) ----
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


class TestIrgGolden(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_params(_DATE_KESF)

    def test_irg_golden(self):
        for nom, assiette, attendu, note in IRG_GOLDEN:
            with self.subTest(cas=nom, note=note):
                obtenu = irg.calcul_irg(assiette, self.cfg)
                self.assertEqual(
                    obtenu, attendu,
                    f"{nom} ({note}): assiette={assiette} → attendu {attendu}, obtenu {obtenu}",
                )


def _rapport():
    """تقرير جدول مقروء (تشغيل مباشر كملف)."""
    cfg = load_params(_DATE_KESF)
    largeur = 74
    print("=" * largeur)
    print("  اختبارات IRG الذهبية — القسم 5.1")
    print("=" * largeur)
    print(f"  {'#':<4}{'الوعاء':>14}{'متوقع':>14}{'محسوب':>14}   الحالة")
    print("-" * largeur)
    ok = 0
    for nom, assiette, attendu, _note in IRG_GOLDEN:
        obtenu = irg.calcul_irg(assiette, cfg)
        passe = obtenu == attendu
        ok += passe
        marque = "OK  " if passe else "FAIL"
        print(f"  {nom:<4}{assiette:>14,.2f}{attendu:>14,.2f}{obtenu:>14,.2f}   {marque}")
    print("-" * largeur)
    print(f"  النتيجة: {ok}/{len(IRG_GOLDEN)} نجح")
    print("=" * largeur)
    return ok == len(IRG_GOLDEN)


if __name__ == "__main__":
    sys.exit(0 if _rapport() else 1)
