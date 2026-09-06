"""سلسلة حساب كشف الراتب (نموذج كشف CNAS القصير) — نواة حساب صافية.

    salaire de poste = القاعدي + المنح الخاضعة للاشتراك        (= أساس CNAS)
    retenue CNAS     = أساس CNAS × taux_salarie   (من params، لا رقم في الكود)
    base IRG         = أساس CNAS − retenue CNAS   (panier/transport خارجها افتراضياً)
    retenue IRG      = programme.payroll.irg.calcul_irg(base IRG, params)
    total gains      = salaire de poste + منح غير خاضعة + panier + transport
    total retenues   = CNAS + IRG + اقتطاعات أخرى
    net à payer      = total gains − total retenues

كل المبالغ تُحسب بـ Decimal (ممنوع float في حساب المال). كل رقم قانوني
(نسبة CNAS، سلّم IRG…) يأتي من ملف المعاملات المؤرَّخ — راجع
programme.payroll.config_loader.

النطاق: العامل الأجير في الحالة العادية فقط (docs/specs/SPEC_PAIE_DZ.md)
— لا منطق متقاعد / معاق.
"""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import List

from programme.payroll.irg import calcul_irg, da

_ZERO = Decimal("0")


def _d(value) -> Decimal:
    """أي إدخال (نص/عدد) → Decimal. فارغ أو غير صالح → 0. يقبل الفاصلة
    العشرية الفرنسية والفراغ كفاصل آلاف."""
    if isinstance(value, Decimal):
        return value
    s = str(value if value is not None else "").strip()
    s = s.replace(" ", "").replace(" ", "").replace("\xa0", "").replace(",", ".")
    if not s:
        return _ZERO
    try:
        return Decimal(s)
    except InvalidOperation:
        return _ZERO


def _pos(value) -> Decimal:
    v = _d(value)
    return v if v > _ZERO else _ZERO


@dataclass
class Prime:
    code: str = ""
    libelle: str = ""
    montant: Decimal = _ZERO
    soumis_cotisation: bool = True


@dataclass
class Retenue:
    code: str = ""
    libelle: str = ""
    montant: Decimal = _ZERO


@dataclass
class PaieInput:
    mois: str = ""
    annee: str = ""
    jours: Decimal = Decimal("30")
    salaire_base: Decimal = _ZERO
    panier: Decimal = _ZERO
    transport: Decimal = _ZERO
    primes: List[Prime] = field(default_factory=list)
    autres_retenues: List[Retenue] = field(default_factory=list)
    # بعض المكاتب تُدخل panier/transport في أساس IRG — قابل للقلب.
    panier_transport_in_irg: bool = False


@dataclass
class PaieResult:
    salaire_poste: Decimal = _ZERO
    base_cnas: Decimal = _ZERO
    retenue_cnas: Decimal = _ZERO
    base_irg: Decimal = _ZERO
    retenue_irg: Decimal = _ZERO
    primes_soumises: Decimal = _ZERO
    primes_non_soumises: Decimal = _ZERO
    autres_retenues_total: Decimal = _ZERO
    panier: Decimal = _ZERO
    transport: Decimal = _ZERO
    total_gain: Decimal = _ZERO
    total_retenue: Decimal = _ZERO
    net_a_payer: Decimal = _ZERO


def compute(data: PaieInput, cfg: dict) -> PaieResult:
    """يحسب الكشف من ``data`` وملف المعاملات ``cfg`` (كما ترجعه
    ``config_loader.load_params``). ``cfg`` إلزامي — لا افتراضات مخبّأة."""
    taux_cnas = _d(cfg["cnas"]["taux_salarie"])

    base = _pos(data.salaire_base)
    primes_soumises = sum((_pos(p.montant) for p in data.primes if p.soumis_cotisation), _ZERO)
    primes_non_soumises = sum((_pos(p.montant) for p in data.primes if not p.soumis_cotisation), _ZERO)
    panier = _pos(data.panier)
    transport = _pos(data.transport)

    salaire_poste = base + primes_soumises                 # أساس CNAS
    retenue_cnas = da(salaire_poste * taux_cnas)

    base_irg = salaire_poste - retenue_cnas
    if data.panier_transport_in_irg:
        base_irg += panier + transport
    base_irg = da(base_irg)
    retenue_irg = calcul_irg(base_irg, cfg)

    autres = sum((_pos(r.montant) for r in data.autres_retenues), _ZERO)

    total_gain = da(salaire_poste + primes_non_soumises + panier + transport)
    total_retenue = da(retenue_cnas + retenue_irg + autres)

    return PaieResult(
        salaire_poste=da(salaire_poste),
        base_cnas=da(salaire_poste),
        retenue_cnas=retenue_cnas,
        base_irg=base_irg,
        retenue_irg=retenue_irg,
        primes_soumises=da(primes_soumises),
        primes_non_soumises=da(primes_non_soumises),
        autres_retenues_total=da(autres),
        panier=da(panier),
        transport=da(transport),
        total_gain=total_gain,
        total_retenue=total_retenue,
        net_a_payer=da(total_gain - total_retenue),
    )


def fmt_montant(x) -> str:
    """تنسيق فرنسي: فاصلة عشرية، فراغ لآلاف — «49 505,71»."""
    try:
        s = f"{_d(x):,.2f}"
    except (ValueError, InvalidOperation):
        return ""
    return s.replace(",", " ").replace(".", ",")
