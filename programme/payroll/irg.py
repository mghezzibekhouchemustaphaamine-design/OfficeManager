"""دالة IRG المرجعية — نقل حرفي للقسم 4 من docs/specs/SPEC_PAIE_DZ.md.

النطاق: الحالة العادية فقط — لا معامل ``statut`` ولا فرع خاص بالمتقاعدين
أو ذوي الإعاقة.

نقاط تنبيه (من المواصفة):
  1. التخفيض (``abattement``) يُطبَّق على **الضريبة** لا على الأجر.
  2. الصيغة القديمة ``IRG1 × (8/3) − (20000/3)`` مهجورة (سلم ما قبل LF 2022).
  3. ``max(0, ...)`` إلزامي بعد التنعيم — الضريبة لا تكون سالبة أبداً.
  4. ``Decimal`` وليس ``float`` (فروقات دينار في تصريح G50).

كل رقم قانوني (حدّ الإعفاء، الشرائح، نسب التخفيض وحدوده، معاملات
التنعيم) يأتي من ``cfg`` (params_<سنة>.json) — لا شيء مكتوب هنا.
"""
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR


def arrondi_dizaine_inf(x: Decimal) -> Decimal:
    return (x / 10).to_integral_value(rounding=ROUND_FLOOR) * 10


def da(x) -> Decimal:                      # arrondi monétaire
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def bareme_mensuel(assiette: Decimal, tranches: list) -> Decimal:
    """Barème progressif PAR TRANCHES — jamais un taux unique sur le total."""
    impot = Decimal(0)
    plancher = Decimal(0)
    for t in tranches:
        plafond = Decimal(t["plafond"]) if t["plafond"] is not None else None
        if plafond is None or assiette <= plafond:
            impot += (assiette - plancher) * Decimal(str(t["taux"]))
            break
        impot += (plafond - plancher) * Decimal(str(t["taux"]))
        plancher = plafond
    return impot


def calcul_irg(assiette: Decimal, cfg: dict) -> Decimal:
    p = cfg["irg"]

    # (a) arrondi de l'assiette à la dizaine inférieure
    R = arrondi_dizaine_inf(assiette) if p["arrondi_assiette_dizaine_inferieure"] else assiette

    # (b) exonération totale
    if R <= Decimal(p["seuil_exoneration"]):
        return Decimal("0.00")

    # (c) barème progressif → IRG brut
    irg_brut = bareme_mensuel(R, p["tranches_mensuelles"])

    # (d) 1er abattement : 40% DE L'IMPÔT (pas du salaire), borné 1000–1500 DA/mois
    ab = irg_brut * Decimal(str(p["abattement"]["taux"]))
    ab = min(max(ab, Decimal(p["abattement"]["min_mensuel"])),
             Decimal(p["abattement"]["max_mensuel"]))
    irg1 = irg_brut - ab

    # (e) 2e abattement (lissage) — bornes STRICTES des deux côtés.
    #     Art. 104 CIDTA : « revenus SUPÉRIEURS à 30.000 et INFÉRIEURS à 35.000 ».
    #     35 000,00 exactement est HORS lissage → calcul normal.
    liss = p["lissage_standard"]
    if Decimal(liss["borne_inf"]) < R < Decimal(liss["borne_sup"]):
        irg = irg1 * Decimal(str(liss["coef_a"])) - Decimal(str(liss["coef_b"]))
        return max(Decimal("0.00"), da(irg))

    return da(irg1)
