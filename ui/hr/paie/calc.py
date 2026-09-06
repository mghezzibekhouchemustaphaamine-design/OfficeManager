"""سلسلة حساب كشف الراتب — موحّدة لكل الموديلات.

تتبع قاعدة نموذج المكتب المرجعي (كشف CNAS القصير) حرفياً:

    salaire de poste = القاعدي + المنح الخاضعة للاشتراك        (= أساس CNAS)
    retenue CNAS     = أساس CNAS × 9٪
    base IRG         = أساس CNAS − retenue CNAS               (panier/transport خارجها)
    retenue IRG      = ui.hr.irg.compute_irg(base IRG, …)
    total gains      = salaire de poste + منح غير خاضعة + panier + transport
    total retenues   = CNAS + IRG + اقتطاعات أخرى
    net à payer      = total gains − total retenues

هل تدخل panier/transport أساس IRG؟ لا، في هذا النموذج (كما في المرجع
المختار). قابل للقلب لاحقاً عبر PaieInput.panier_transport_in_irg.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from ui.hr import irg
from ui.hr.constants import TAUX_CNAS


@dataclass
class Prime:
    code: str = ""
    libelle: str = ""
    montant: float = 0.0
    soumis_cotisation: bool = True


@dataclass
class Retenue:
    code: str = ""
    libelle: str = ""
    montant: float = 0.0


@dataclass
class PaieInput:
    mois: str = ""
    annee: str = ""
    jours: float = 30.0
    salaire_base: float = 0.0
    panier: float = 0.0
    transport: float = 0.0
    handicape_retraite: bool = False
    primes: List[Prime] = field(default_factory=list)
    autres_retenues: List[Retenue] = field(default_factory=list)
    # قلب سلوك أساس IRG (بعض المكاتب تُدخل panier/transport فيه)
    panier_transport_in_irg: bool = False


@dataclass
class PaieResult:
    salaire_poste: float = 0.0
    base_cnas: float = 0.0
    retenue_cnas: float = 0.0
    base_irg: float = 0.0
    retenue_irg: float = 0.0
    primes_soumises: float = 0.0
    primes_non_soumises: float = 0.0
    autres_retenues_total: float = 0.0
    panier: float = 0.0
    transport: float = 0.0
    total_gain: float = 0.0
    total_retenue: float = 0.0
    net_a_payer: float = 0.0


def _r2(x: float) -> float:
    return round(float(x) + 0.0, 2)


def _pos(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return v if v > 0 else 0.0


def compute(data: PaieInput, irg_cfg: Optional[irg.IRGConfig] = None) -> PaieResult:
    cfg = irg_cfg or irg.DEFAULT_CONFIG

    base = _pos(data.salaire_base)
    primes_soumises = sum(_pos(p.montant) for p in data.primes if p.soumis_cotisation)
    primes_non_soumises = sum(_pos(p.montant) for p in data.primes if not p.soumis_cotisation)
    panier = _pos(data.panier)
    transport = _pos(data.transport)

    salaire_poste = base + primes_soumises                 # أساس CNAS
    retenue_cnas = _r2(salaire_poste * TAUX_CNAS)

    base_irg = salaire_poste - retenue_cnas
    if data.panier_transport_in_irg:
        base_irg += panier + transport
    base_irg = _r2(base_irg)
    retenue_irg = irg.compute_irg(base_irg, cfg, data.handicape_retraite)

    autres = sum(_pos(r.montant) for r in data.autres_retenues)

    total_gain = _r2(salaire_poste + primes_non_soumises + panier + transport)
    total_retenue = _r2(retenue_cnas + retenue_irg + autres)

    return PaieResult(
        salaire_poste=_r2(salaire_poste),
        base_cnas=_r2(salaire_poste),
        retenue_cnas=retenue_cnas,
        base_irg=base_irg,
        retenue_irg=retenue_irg,
        primes_soumises=_r2(primes_soumises),
        primes_non_soumises=_r2(primes_non_soumises),
        autres_retenues_total=_r2(autres),
        panier=_r2(panier),
        transport=_r2(transport),
        total_gain=total_gain,
        total_retenue=total_retenue,
        net_a_payer=_r2(total_gain - total_retenue),
    )


def fmt_montant(x: float) -> str:
    """تنسيق فرنسي: فاصلة عشرية، فراغ لآلاف — «49 505,71»."""
    try:
        s = f"{float(x):,.2f}"
    except (TypeError, ValueError):
        return ""
    return s.replace(",", " ").replace(".", ",")
