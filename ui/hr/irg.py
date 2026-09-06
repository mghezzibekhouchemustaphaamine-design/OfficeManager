"""حساب الضريبة على الدخل الإجمالي (IRG) على الأجور — الجزائر.

نقل حرفي لخوارزمية حاسبة المديرية العامة للضرائب الرسمية (IRG 2022).
المصدر: irg_f.java — الشيفرة المصدرية للحاسبة الرسمية المحمّلة من
mfdgi.gov.dz. طوبِقت شريحةً شريحةً مع السلّم المنشور على
mfdgi.gov.dz/fr/particuliers/irg-traitements-et-salaires.

الهدف (فلسفة البرنامج): إلغاء حلقة «حاسبة خارجية ← إكسل ← وورد»،
فيصير كشف الراتب يحسب IRG داخلياً مباشرة.

الآلية:
  1) سنْونة الأجر الخاضع الشهري (× 12)
  2) ضريبة تصاعدية عبر جدول سنوي: (حد أعلى، نسبة الشريحة %، ضريبة تراكمية عند الحد)
  3) قسمة الناتج على 12 (رجوع للشهري)
  4) تخفيض 40٪ محصور في [1000 ، 1500] دج
  5) تنعيم الشريحة الدنيا:
        أجر خاضع ≤ 30 000            → IRG = 0
        30 000 < خاضع ≤ 35 000       → IRG = RET × (137/51) − (27925/8)   [عادي]
        30 000 < خاضع ≤ 42 500       → IRG = RET × (93/61)  − (81213/41)  [معاق/متقاعد]

القِيَم في IRGConfig (الجدول + حدود التخفيض + عتبات التنعيم) قابلة
للتعديل من الإعدادات — تتغيّر مع كل قانون مالية فلا تُكتب بصلابة.
"""
from dataclasses import dataclass, field
from typing import List, Tuple

# الجدول السنوي الرسمي 2022: (حد أعلى سنوي دج، نسبة الشريحة ٪، ضريبة تراكمية عند الحد)
# مطابق لـ TAB07 في irg_f.java ولِلسلّم المنشور من DGI:
#   0–240 000: 0٪ · 240 001–480 000: 23٪ · 480 001–960 000: 27٪
#   960 001–1 920 000: 30٪ · 1 920 001–3 840 000: 33٪ · > 3 840 000: 35٪
OFFICIAL_TABLE_2022: List[Tuple[float, float, float]] = [
    (0.0,          0.0,  0.0),
    (240_000.0,    0.0,  0.0),
    (480_000.0,    23.0, 55_200.0),
    (960_000.0,    27.0, 184_800.0),
    (1_920_000.0,  30.0, 472_800.0),
    (3_840_000.0,  33.0, 1_106_400.0),
    (9_999_999.0,  35.0, 3_262_399.65),
]


@dataclass
class IRGConfig:
    # الجدول السنوي: (حد أعلى، نسبة ٪، ضريبة تراكمية عند الحد)
    annual_table: List[Tuple[float, float, float]] = field(
        default_factory=lambda: list(OFFICIAL_TABLE_2022)
    )
    # التخفيض على مبلغ الضريبة (abattement)
    abatement_rate: float = 0.40
    abatement_min: float = 1_000.0
    abatement_max: float = 1_500.0
    # تنعيم الشريحة الدنيا
    exempt_ceiling: float = 30_000.0          # ≤ هذا الحد → IRG = 0
    relief_ceiling_normal: float = 35_000.0   # نطاق التنعيم — أجير عادي
    relief_ceiling_hr: float = 42_500.0       # نطاق التنعيم — معاق / متقاعد
    # معاملات الصيغة الخطية للتنعيم (من irg_f.java):  IRG = RET × a − b
    relief_a_normal: float = 137.0 / 51.0
    relief_b_normal: float = 27_925.0 / 8.0
    relief_a_hr: float = 93.0 / 61.0
    relief_b_hr: float = 81_213.0 / 41.0
    # تطبيق النِّسب العليا (33٪ / 35٪) كما ينصّ عليها السلّم المكتوب،
    # بدل تقليد هفوة ملف .exe الرسمي الذي يُبقيها عند 30٪ فوق 160 000 دج/شهر.
    # لا فرق إطلاقاً تحت 160 000 دج/شهر.
    fix_top_brackets: bool = True

    def __post_init__(self):
        self.annual_table = sorted(self.annual_table, key=lambda r: r[0])


DEFAULT_CONFIG = IRGConfig()


def _annual_tax(brts: float, cfg: IRGConfig) -> float:
    """ضريبة سنوية على دخل سنوي خاضع brts — منطق c_irg (irg_f.java)."""
    tab = cfg.annual_table
    # SKIP = عدد الحدود التي تجاوزها الدخل (أول i حيث brts <= tab[i][0] يوقف)
    skip = 0
    for i in range(len(tab)):
        if brts <= tab[i][0]:
            break
        skip = i + 1
    if skip == 0:
        return 0.0

    lower_bound = tab[skip - 1][0]
    cum_tax = tab[skip - 1][2]
    if cfg.fix_top_brackets:
        rate = tab[skip][1] if skip < len(tab) else tab[-1][1]
    else:  # سلوك ملف .exe الرسمي حرفياً (بهفوته في الشرائح العليا)
        rate = tab[skip - 1][1] if skip > 4 else tab[skip][1]
    return (brts - lower_bound) * rate / 100.0 + cum_tax


def _base_irg(soumis: float, cfg: IRGConfig) -> float:
    """RET في irg_f.java: ضريبة شهرية بعد التخفيض، قبل تنعيم الشريحة الدنيا."""
    brts = 12.0 * soumis
    impm = _annual_tax(brts, cfg) / 12.0
    abat = cfg.abatement_rate * impm
    abat = max(cfg.abatement_min, min(cfg.abatement_max, abat))
    return max(impm - abat, 0.0)


def compute_irg(
    salaire_imposable_mensuel: float,
    cfg: IRGConfig = DEFAULT_CONFIG,
    handicape_retraite: bool = False,
) -> float:
    """مبلغ IRG الشهري لأجر خاضع للضريبة معطى (بعد كل القواعد).

    salaire_imposable_mensuel: الأجر الشهري الخاضع (بعد اقتطاع CNAS).
    handicape_retraite: خانة «Handicapé / Retraité» في الكشف.
    """
    s = max(float(salaire_imposable_mensuel or 0.0), 0.0)
    ret = _base_irg(s, cfg)

    if handicape_retraite:
        if s <= cfg.relief_ceiling_hr:
            ret = ret * cfg.relief_a_hr - cfg.relief_b_hr
            if ret < 0:
                ret = 0.0
            if s <= cfg.exempt_ceiling:
                ret = 0.0
    else:
        if s <= cfg.relief_ceiling_normal:
            ret = ret * cfg.relief_a_normal - cfg.relief_b_normal
            if ret < 0:
                ret = 0.0
            if s <= cfg.exempt_ceiling:
                ret = 0.0

    return round(ret, 2)


if __name__ == "__main__":
    # اختبار ذاتي: يعيد إنتاج نتيجة كشف حقيقي (2023) — أساس خاضع 81 582.78 → IRG 14 374.83
    ref = compute_irg(81_582.78)
    assert abs(ref - 14_374.83) < 0.02, f"regression: got {ref}, expected 14374.83"
    print(f"[ok] IRG(81 582.78) = {ref:,.2f}  (référence 14 374.83)")

    print("\n  imposable      normal      handicapé/retraité")
    for s in (20_000, 30_000, 30_001, 32_000, 34_000, 35_000, 35_001,
              40_000, 50_000, 81_582.78, 100_000, 160_000, 200_000, 350_000):
        print(f"  {s:>10,.2f}   {compute_irg(s):>10,.2f}   {compute_irg(s, handicape_retraite=True):>10,.2f}")
