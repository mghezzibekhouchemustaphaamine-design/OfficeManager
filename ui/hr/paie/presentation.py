"""طبقة العرض المشتركة لكشف الراتب (Phase E.3 §10/§11).

تحوّل :class:`programme.payroll.lignes.BulletinView` إلى **صفوفٍ معروضة
ومجاميع معروضة موحّدة** يستهلكها الرسمُ على الشاشة والمُصيِّر PDF والمُصيِّر
DOCX معاً — لا تكرار لمنطق «Gain سالب».

بلا Qt/Tk/ReportLab. تعتمد فقط :func:`programme.payroll.calc.fmt_montant`
(مُنسِّق العرض الموحَّد) و :data:`ui.hr.constants.PAIE_DEFAULT_CODES`.

**المبدأ (§9/§30):** المحرّك يطرح Absence/Retard داخل Z1
(‏``total_gains``) عمداً — لا يُغيَّر. هنا تُعرَض **اقتطاعاً موجباً** في
عمود RETENUE، وتُصالَح المجاميع::

    base_reducers_total   = Σ (مبالغ Absence/Retard المعروضة موجبةً)
    display_total_gain     = engine.total_gains    + base_reducers_total
    display_total_retenue  = engine.total_retenues + base_reducers_total
    display_net            = engine.net_a_payer              (بلا تغيير)

العقد:  ``display_total_gain − display_total_retenue == display_net``.

أرقام المحرّك (وعاء CNAS · اقتطاع CNAS · وعاء IRG · IRG · الصافي) لا تتغيّر.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from programme.payroll.calc import fmt_montant
from ui.hr.constants import PAIE_DEFAULT_CODES

#  أنواع Z1 المُنقِصة — تُعرَض اقتطاعاً موجباً (§9).
BASE_REDUCERS = ("abs_jours", "abs_heures", "retard")

#  أدنى أسطر تحت IRG (فراغٌ ثابت — SCREEN = PDF).
MIN_ZONE_C_ROWS = 5

_FR_LIBELLE = {
    "salaire_base": "SALAIRE DE BASE",
    "iep": "IND. EXPÉRIENCE PROF.", "pri": "PRIME DE RENDEMENT",
    "hs_50": "HEURES SUPP. 50 %", "hs_100": "HEURES SUPP. 100 %",
    "abs_jours": "ABSENCE (JOURS)", "abs_heures": "ABSENCE (HEURES)",
    "retard": "RETARD", "panier": "PANIER", "transport": "(R+) TRANSPORT",
    "avance": "AVANCE / ACOMPTE", "syndicat": "COTISATION SYNDICALE",
    "nuit": "PRIME DE NUIT", "conge_paye": "CONGÉ PAYÉ",
    "alloc_fam": "ALLOCATIONS FAMILIALES", "libre": "",
}

_ZONE_OF = {"Z1": "A", "Z2": "B", "Z3": "C", "Z4": "C"}


@dataclass
class PRow:
    """صفٌّ معروض واحد بأعمدة الجدول الستّة."""
    code: str = ""
    libelle: str = ""
    nbase: str = ""
    taux: str = ""
    gain: str = ""
    retenue: str = ""
    key: str = ""            # مفتاح المحرّك (تشخيص)
    zone: str = ""           # A|B|C — فارغٌ للثابت/الفراغ
    kind: str = "line"       # "line" | "system" | "blank"

    def as_cols(self):
        return {"code": self.code, "libelle": self.libelle,
                "nbase": self.nbase, "taux": self.taux,
                "gain": self.gain, "retenue": self.retenue}


@dataclass
class Presented:
    rows: list = field(default_factory=list)
    total_gain: Decimal = Decimal(0)
    total_retenue: Decimal = Decimal(0)
    net: Decimal = Decimal(0)
    base_reducers_total: Decimal = Decimal(0)

    @property
    def total_gain_str(self):
        return fmt_montant(self.total_gain)

    @property
    def total_retenue_str(self):
        return fmt_montant(self.total_retenue)

    @property
    def net_str(self):
        return fmt_montant(self.net)


def _lib(lv):
    return (_FR_LIBELLE.get(lv.key)
            or (lv.libelle or "").strip().upper() or lv.key.upper())


def _dec(x):
    return x if isinstance(x, Decimal) else Decimal(str(x or 0))


def build(view, *, jours=None, pad_zone_c=True):
    """‏``BulletinView`` → :class:`Presented` بترتيب شرائح الشاشة:
    SALAIRE → [A = Z1] → CNAS → PANIER → TRANSPORT → [B = Z2] → IRG →
    [C = Z3+Z4] (+ فراغٌ حتى ``MIN_ZONE_C_ROWS``)."""
    c = PAIE_DEFAULT_CODES
    res = view.result
    by_zone = {"Z1": [], "Z2": [], "Z3": [], "Z4": []}
    salaire, pt = None, {}
    for lv in view.lignes:
        if lv.key == "salaire_base":
            salaire = lv
            continue
        if lv.key in ("panier", "transport"):
            pt[lv.key] = lv
            continue
        by_zone.get(lv.zone, by_zone["Z3"]).append(lv)

    reducers_total = Decimal(0)

    def prow(lv):
        nonlocal reducers_total
        row = PRow(code=(lv.code or "").strip(), libelle=_lib(lv),
                   nbase=(fmt_montant(jours)
                          if lv.key == "salaire_base" and jours is not None
                          else ""),
                   key=lv.key, zone=_ZONE_OF.get(lv.zone, "C"))
        if lv.key in BASE_REDUCERS:
            amt = abs(_dec(lv.montant))
            reducers_total += amt
            row.retenue = fmt_montant(amt)          # §9: موجبٌ في RETENUE
        elif lv.sens == "RETENUE":
            row.retenue = fmt_montant(_dec(lv.montant))
        else:
            row.gain = fmt_montant(_dec(lv.montant))
        return row

    rows = []
    if salaire is not None:
        rows.append(prow(salaire))
    rows += [prow(lv) for lv in by_zone["Z1"]]                  # Zone A
    rows.append(PRow(code=c["cnas"], libelle="RETENUE SÉCU. SOCIALE",
                     nbase=fmt_montant(res.assiette_cnas), taux="9,00",
                     retenue=fmt_montant(res.retenue_cnas), kind="system"))
    for key, lab in (("panier", "PANIER"), ("transport", "(R+) TRANSPORT")):
        if key in pt:
            rows.append(prow(pt[key]))
        else:
            rows.append(PRow(code=c[key], libelle=lab, gain=fmt_montant(0)))
    rows += [prow(lv) for lv in by_zone["Z2"]]                  # Zone B
    rows.append(PRow(code=c["irg"], libelle="RETENUE IRG",
                     nbase=fmt_montant(res.assiette_irg),
                     retenue=fmt_montant(res.irg), kind="system"))
    zc = [prow(lv) for lv in by_zone["Z3"] + by_zone["Z4"]]     # Zone C
    if pad_zone_c:
        zc += [PRow(kind="blank")
               for _ in range(max(0, MIN_ZONE_C_ROWS - len(zc)))]
    rows += zc

    dg = _dec(res.total_gains) + reducers_total
    dr = _dec(res.total_retenues) + reducers_total
    return Presented(rows=rows, total_gain=dg, total_retenue=dr,
                     net=_dec(view.e), base_reducers_total=reducers_total)
