"""أنواع أسطر كشف الراتب — الجسر بين واجهة الإدخال والمحرّك.

منطق نطاق، لا منطق عرض (لا PySide6). المحرّك (``calc.py`` / ``irg.py``)
لا يُلمَس — يُستدعى فقط. الشاشة تستدعي هذه الوحدة **حصراً** ولا تبني
:class:`SequenceInput` بنفسها.

كل نوع سطر يعرف:
  • حقوله (ماذا يُدخِل المستخدم)،
  • كيف يطوى في :class:`programme.payroll.calc.SequenceInput` (``fold``)،
  • كم يُعرَض على السطر بعد الحساب (``resolve``)،
  • خصائصه الجبائية ومنها تُشتقّ منطقته آلياً (§2.3.2) — المستخدم لا
    يختار الموقع.

منحتا الأقدمية IEP والمردودية PRI تُمرَّران للمحرّك كـ:class:`Prime`
خاضعة للاشتراك (لا عبر مسار ``anciennete_annees`` الداخلي) حتى تبقى
النسبة **مقترَحة وقابلة للتعديل** (§1.2.4) — القيمة العددية للسطر
مطابقة تماماً لمسار المحرّك في ‎[A]/[B]/[C]/[E]‎.
"""
import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Tuple

from programme.payroll.calc import (
    HeureSupp, Prime, Retenue, SequenceInput, SequenceResult, _d, da,
    compute_sequence,
)

_ZERO = Decimal("0")


# ------------------------------------------------------------------ المناطق

def zone_of(*, sens: str, cotisable: bool, imposable: bool) -> str:
    """منطقة السطر (§2.3.2). يوافق **جدول** §2.3.2 والمحرّك:

      • ``RETENUE`` خاضعة للاشتراك (اقتطاع الغياب/التأخّر) → ``Z1``
        بإشارة سالبة، لأنها تُطرح داخل ‎[A] = ΣZ1‎.
      • ``RETENUE`` غير خاضعة (تسبيق، حكم، نقابة، تعاضدية) → ``Z4``.
      • ``GAIN`` خاضعة → ``Z1`` · معفاة وخاضعة لـIRG → ``Z2`` · معفاة
        وغير خاضعة → ``Z3`` (تحت ‎[D]‎).

    (مقتطف الكود المبسّط في §2.3.2 يُرجِع Z4 لكل ``RETENUE`` غير
    CNAS/IRG؛ الجدول والنصّ والمحرّك يخصّون اقتطاع الغياب بـZ1.)"""
    if sens == "RETENUE":
        return "Z1" if cotisable else "Z4"
    if cotisable:
        return "Z1"
    return "Z2" if imposable else "Z3"


ZONE_ORDER = {"Z1": 0, "Z2": 1, "Z3": 2, "Z4": 3}

_TRUTHY = {"1", "true", "نعم", "oui", "yes", "on"}


def _truthy(v) -> bool:
    return str(v).strip().lower() in _TRUTHY


# ------------------------------------------------------------------ الأقدمية (§1.2.4)

@dataclass
class IepSuggestion:
    taux: Optional[Decimal]          # None → لا اقتراح (بلا تاريخ دخول)
    annees: int = 0
    mois: int = 0
    depuis: str = ""                 # تاريخ الدخول كما أُدخِل
    source: str = "sans_date"        # bareme | employe | sous_minimum | sans_date
    raison: str = ""

    def texte_anciennete(self) -> str:
        if not self.depuis:
            return "حدّد تاريخ الدخول للحصول على اقتراح"
        return (f"{self.annees} سنوات و{self.mois} شهر "
                f"(منذ {self.depuis})")


def _period_end(periode: str) -> Optional[date]:
    """``"YYYY-MM"`` → آخر يوم في الشهر (الأقدمية تُحسب حتى نهاية فترة
    الدفع). يقبل ``"YYYY-MM-DD"`` كما هو."""
    parts = str(periode).split("-")
    try:
        y, m = int(parts[0]), int(parts[1])
        d = int(parts[2]) if len(parts) > 2 else calendar.monthrange(y, m)[1]
        return date(y, m, d)
    except (ValueError, IndexError):
        return None


def _annees_mois(debut: date, fin: date) -> Tuple[int, int]:
    months = (fin.year - debut.year) * 12 + (fin.month - debut.month)
    if fin.day < debut.day:
        months -= 1
    months = max(months, 0)
    return months // 12, months % 12


def suggest_iep_taux(*, date_entree: str, periode: str, cfg: Dict,
                     employe_taux_iep=None) -> IepSuggestion:
    """يقترح نسبة الأقدمية (§1.2.4). ثلاث طبقات:

      1) ``employe.taux_iep`` إن ضُبطت → تُستعمل مباشرةً،
      2) وإلا: عدد السنوات الكاملة × ``cfg.iep.taux_par_annee``،
      3) إن كانت الأقدمية < ``cfg.iep.anciennete_minimale_annees`` → 0%.

    النسبة **مقترَحة لا مفروضة** — الشاشة تعرضها والمستخدم حرّ يعدّلها."""
    debut = _period_end(str(date_entree)) if date_entree else None
    fin = _period_end(periode)
    if debut is None or fin is None:
        return IepSuggestion(taux=None, source="sans_date", depuis="",
                             raison="حدّد تاريخ الدخول للحصول على اقتراح")

    annees, mois = _annees_mois(debut, fin)
    depuis = debut.strftime("%d-%m-%Y")
    min_an = int(_d(cfg["iep"]["anciennete_minimale_annees"]))
    par_an = _d(cfg["iep"]["taux_par_annee"])

    if annees < min_an:
        return IepSuggestion(
            taux=_ZERO, annees=annees, mois=mois, depuis=depuis,
            source="sous_minimum",
            raison=(f"الأقدمية ({annees} سنة و{mois} شهر) دون الحدّ الأدنى "
                    f"({min_an} سنة) — المقترَح 0%"))
    if employe_taux_iep not in (None, ""):
        return IepSuggestion(
            taux=_d(employe_taux_iep), annees=annees, mois=mois, depuis=depuis,
            source="employe", raison="من بطاقة العامل (employe.taux_iep)")
    return IepSuggestion(
        taux=annees * par_an, annees=annees, mois=mois, depuis=depuis,
        source="bareme",
        raison=f"{annees} سنة كاملة × {par_an} (نسبة مقترَحة — عدّلها إن لزم)")


# ------------------------------------------------------------------ السياق

@dataclass
class _Ctx:
    cfg: Dict
    convention: Dict
    base_iep_val: Decimal
    base_pri_val: Decimal


# ------------------------------------------------------------------ الأنواع

@dataclass(frozen=True)
class LineField:
    key: str
    label: str
    kind: str                       # ui2.form: amount | number | date | choice | text
    default: str = ""
    choices: Tuple[str, ...] = ()


FoldFn = Callable[[SequenceInput, Dict, "_Ctx", Dict], None]
ResolveFn = Callable[[SequenceResult, Dict, Dict], Decimal]


@dataclass(frozen=True)
class LineType:
    key: str
    libelle: str
    sens: str                       # "GAIN" | "RETENUE" | "" (سطر حرّ)
    cotisable: Optional[int]
    imposable: Optional[int]
    proratisable: bool
    group: str                      # "base" | "autres" | "libre"
    fields: Tuple[LineField, ...]
    fold: FoldFn
    resolve: ResolveFn
    code: str = ""
    system: bool = False            # الأجر القاعدي: يُضاف آلياً، لا يُحذف

    # ------- المنطقة تُشتقّ، لا تُختار -------
    def zone(self, values: Dict) -> str:
        sens = self.sens
        cot = self.cotisable
        imp = self.imposable
        if not sens:                                    # سطر حرّ
            sens = "RETENUE" if _truthy(values.get("est_retenue")) else "GAIN"
        if cot is None:
            cot = 1 if _truthy(values.get("cotisable")) else 0
        if imp is None:
            imp = 1 if _truthy(values.get("imposable")) else 0
        return zone_of(sens=sens, cotisable=bool(cot), imposable=bool(imp))


def _v(values: Dict, key: str) -> Decimal:
    return _d(values.get(key))


# ---- طيّات بسيطة -----------------------------------------------------

def _fold_salaire_base(si, v, ctx, m):
    si.salaire_base = _d(si.salaire_base) + _v(v, "montant")


def _fold_abs_jours(si, v, ctx, m):
    si.jours_absence = _d(si.jours_absence) + _v(v, "jours")


def _fold_abs_heures(si, v, ctx, m):
    si.heures_absence_irreguliere = (
        _d(si.heures_absence_irreguliere) + _v(v, "heures"))


def _fold_retard(si, v, ctx, m):
    si.heures_retard = _d(si.heures_retard) + _v(v, "heures")


def _fold_hs(coef_key, defaut):
    def _f(si, v, ctx, m):
        coef = _d(ctx.convention.get(coef_key) or defaut)
        si.heures_supp.append(HeureSupp(coef=coef, heures=_v(v, "heures")))
        m["hs"] = len(si.heures_supp) - 1
    return _f


def _fold_iep(si, v, ctx, m):
    montant_exact = ctx.base_iep_val * _v(v, "taux")
    si.primes.append(Prime(code="IEP", libelle="منحة الأقدمية",
                           montant=montant_exact,
                           soumis_cotisation=True, imposable=True))
    m["montant"] = da(montant_exact)


def _fold_pri(si, v, ctx, m):
    montant_exact = ctx.base_pri_val * _v(v, "taux")
    si.primes.append(Prime(code="PRI", libelle="منحة المردودية",
                           montant=montant_exact,
                           soumis_cotisation=True, imposable=True))
    m["montant"] = da(montant_exact)


def _fold_transport(si, v, ctx, m):
    si.transport_mensuel = _d(si.transport_mensuel) + _v(v, "montant_mensuel")


def _fold_alloc_fam(si, v, ctx, m):
    si.alloc_familiales = _d(si.alloc_familiales) + _v(v, "montant")


def _fold_prime(code, libelle, cot, imp):
    def _f(si, v, ctx, m):
        si.primes.append(Prime(code=code, libelle=libelle,
                               montant=_v(v, "montant"),
                               soumis_cotisation=bool(cot),
                               imposable=bool(imp)))
    return _f


def _fold_retenue(code, libelle):
    def _f(si, v, ctx, m):
        si.autres_retenues.append(Retenue(code=code, libelle=libelle,
                                          montant=_v(v, "montant")))
    return _f


def _fold_libre(si, v, ctx, m):
    montant = _v(v, "montant")
    if _truthy(v.get("est_retenue")):
        si.autres_retenues.append(Retenue(code="LIBRE",
                                          libelle=v.get("libelle", "سطر حرّ"),
                                          montant=montant))
    else:
        si.primes.append(Prime(
            code="LIBRE", libelle=v.get("libelle", "سطر حرّ"), montant=montant,
            soumis_cotisation=_truthy(v.get("cotisable")),
            imposable=_truthy(v.get("imposable"))))


# ---- حلول العرض ----------------------------------------------------

def _r_input(key):
    return lambda res, v, m: _v(v, key)


def _r_input_round(key):
    return lambda res, v, m: da(_v(v, key))


def _r_meta(res, v, m):
    return m.get("montant", _ZERO)


def _r_hs(res, v, m):
    i = m.get("hs")
    lignes = res.heures_supp_lignes
    return lignes[i] if i is not None and 0 <= i < len(lignes) else _ZERO


LINE_TYPES: Dict[str, LineType] = {
    "salaire_base": LineType(
        "salaire_base", "الأجر القاعدي", "GAIN", 1, 1, True, "base",
        (LineField("montant", "المبلغ الشهري", "amount"),),
        _fold_salaire_base, _r_input("montant"), code="1000", system=True),

    "abs_jours": LineType(
        "abs_jours", "اقتطاع أيام غياب", "RETENUE", 1, 1, False, "base",
        (LineField("jours", "عدد الأيام", "amount"),),
        _fold_abs_jours, lambda res, v, m: res.retenue_jours_abs, code="4000"),

    "abs_heures": LineType(
        "abs_heures", "اقتطاع ساعات غياب", "RETENUE", 1, 1, False, "base",
        (LineField("heures", "عدد الساعات", "amount"),),
        _fold_abs_heures, lambda res, v, m: res.retenue_abs_irreguliere,
        code="4010"),

    "retard": LineType(
        "retard", "اقتطاع ساعات تأخّر", "RETENUE", 1, 1, False, "base",
        (LineField("heures", "عدد الساعات", "amount"),),
        _fold_retard, lambda res, v, m: res.retenue_retard, code="4020"),

    "hs_50": LineType(
        "hs_50", "ساعات إضافية 50%", "GAIN", 1, 1, False, "base",
        (LineField("heures", "عدد الساعات", "amount"),),
        _fold_hs("taux_hs_jour", "1.5"), _r_hs, code="1010"),

    "hs_100": LineType(
        "hs_100", "ساعات إضافية 100%", "GAIN", 1, 1, False, "base",
        (LineField("heures", "عدد الساعات", "amount"),),
        _fold_hs("taux_hs_nuit", "2.0"), _r_hs, code="1010"),

    "iep": LineType(
        "iep", "منحة الأقدمية IEP", "GAIN", 1, 1, True, "base",
        (LineField("taux", "النسبة (مثلاً 0.09)", "amount"),),
        _fold_iep, _r_meta, code="1020"),

    "pri": LineType(
        "pri", "منحة المردودية PRI", "GAIN", 1, 1, True, "base",
        (LineField("taux", "النسبة (مثلاً 0.15)", "amount"),),
        _fold_pri, _r_meta, code="1030"),

    "panier": LineType(
        "panier", "منحة السلة", "GAIN", 0, 1, True, "base",
        (LineField("montant_mensuel", "المبلغ الشهري", "amount"),),
        lambda si, v, ctx, m: setattr(
            si, "panier_mensuel", _d(si.panier_mensuel) + _v(v, "montant_mensuel")),
        lambda res, v, m: res.panier, code="2000"),

    "transport": LineType(
        "transport", "منحة النقل", "GAIN", 0, 1, True, "base",
        (LineField("montant_mensuel", "المبلغ الشهري", "amount"),),
        _fold_transport, lambda res, v, m: res.transport, code="2010"),

    "avance": LineType(
        "avance", "تسبيق على الراتب", "RETENUE", 0, 0, False, "base",
        (LineField("montant", "المبلغ", "amount"),),
        _fold_retenue("AVANCE", "تسبيق على الراتب"),
        _r_input_round("montant"), code="5010"),

    # ---------------- أخرى ----------------
    "nuit": LineType(
        "nuit", "منحة ليلية", "GAIN", 1, 1, True, "autres",
        (LineField("montant", "المبلغ", "amount"),),
        _fold_prime("NUIT", "منحة ليلية", 1, 1),
        _r_input_round("montant"), code="1070"),

    "zone": LineType(
        "zone", "منحة المنطقة", "GAIN", 0, 0, True, "autres",
        (LineField("montant", "المبلغ", "amount"),),
        _fold_prime("ZONE", "منحة المنطقة", 0, 0),
        _r_input_round("montant"), code="3000"),

    "interim": LineType(
        "interim", "منحة إنابة / معلّم تمهين", "GAIN", 1, 1, True, "autres",
        (LineField("montant", "المبلغ", "amount"),),
        _fold_prime("INTERIM", "منحة إنابة", 1, 1),
        _r_input_round("montant"), code="1080"),

    "mutuelle": LineType(
        "mutuelle", "اقتطاع تعاضدية", "RETENUE", 0, 0, False, "autres",
        (LineField("montant", "المبلغ", "amount"),),
        _fold_retenue("MUT", "اقتطاع تعاضدية"),
        _r_input_round("montant"), code="5000"),

    "opposition": LineType(
        "opposition", "اقتطاع بحكم قضائي", "RETENUE", 0, 0, False, "autres",
        (LineField("montant", "المبلغ", "amount"),),
        _fold_retenue("OPP", "اقتطاع بحكم قضائي"),
        _r_input_round("montant"), code="5020"),

    "syndicat": LineType(
        "syndicat", "الاشتراك النقابي", "RETENUE", 0, 0, False, "autres",
        (LineField("montant", "المبلغ", "amount"),),
        _fold_retenue("SYND", "الاشتراك النقابي"),
        _r_input_round("montant"), code="5030"),

    "conge_paye": LineType(
        "conge_paye", "تعويض عطلة (تصفية)", "GAIN", 1, 1, False, "autres",
        (LineField("montant", "المبلغ", "amount"),),
        _fold_prime("CP", "تعويض عطلة", 1, 1),
        _r_input_round("montant"), code="1060"),

    "alloc_fam": LineType(
        "alloc_fam", "المنح العائلية", "GAIN", 0, 0, False, "autres",
        (LineField("montant", "المبلغ", "amount"),),
        _fold_alloc_fam, _r_input("montant"), code="3010"),
}

# النوع الحرّ يُسجَّل في وحدةٍ لاحقة (كوميت مستقل) — انظر register_free_line().


def register_free_line() -> None:
    """يسجّل نوع «سطر حرّ» (كوميت مستقل). تسمية ومبلغ حرّان + ``cotisable``
    و``imposable`` إلزاميان بلا افتراض (V7)."""
    LINE_TYPES["libre"] = LineType(
        "libre", "سطر حرّ", "", None, None, False, "libre",
        (
            LineField("libelle", "التسمية", "text"),
            LineField("montant", "المبلغ", "amount"),
            LineField("est_retenue", "اقتطاع؟", "choice",
                      choices=("لا", "نعم")),
            LineField("cotisable", "خاضع للاشتراك؟ (إلزامي)", "choice",
                      choices=("—", "نعم", "لا")),
            LineField("imposable", "خاضع للضريبة؟ (إلزامي)", "choice",
                      choices=("—", "نعم", "لا")),
        ),
        _fold_libre, _r_input_round("montant"), code="LIBRE")


class FreeLineError(ValueError):
    """سطر حرّ بلا تصنيف صريح (V7)."""


def validate_free_line(values: Dict) -> None:
    """يرفع :class:`FreeLineError` إن لم يُصنَّف السطر الحرّ صراحةً."""
    for k, label in (("cotisable", "خاضع للاشتراك"),
                     ("imposable", "خاضع للضريبة")):
        raw = str(values.get(k, "")).strip()
        if raw in ("", "—"):
            raise FreeLineError(
                f"السطر الحرّ: حدِّد «{label}؟» صراحةً — لا قيمة افتراضية "
                f"(V7 / SPEC §2.1).")


# ------------------------------------------------------------------ النتيجة

@dataclass
class LineView:
    key: str
    libelle: str
    zone: str
    sens: str
    montant: Decimal
    code: str = ""


@dataclass
class BulletinView:
    lignes: List[LineView] = field(default_factory=list)
    a: Decimal = _ZERO
    b: Decimal = _ZERO
    c: Decimal = _ZERO
    d: Decimal = _ZERO
    e: Decimal = _ZERO
    avertissements: List[str] = field(default_factory=list)
    result: Optional[SequenceResult] = None


def _convention_kwargs(convention: Dict) -> Dict:
    out: Dict = {}
    for k in ("base_iep", "base_pri", "prorata_panier_transport"):
        if convention.get(k):
            out[k] = convention[k]
    if convention.get("retard_reduit_heures_presence") is not None:
        out["retard_reduit_heures_presence"] = bool(
            convention["retard_reduit_heures_presence"])
    return out


_RATE_PRIMES = ("iep", "pri")


def compute_bulletin(entries: List[Dict], cfg: Dict,
                     convention: Optional[Dict] = None) -> BulletinView:
    """``entries`` = ``[{"type": <clé>, "values": {...}}, …]``.

    يطوي كل الأسطر في :class:`SequenceInput` واحد، يستدعي المحرّك، ثم
    يبني عرضاً مُصنَّفاً بالمناطق + ‎[A]…[E]‎ + التحذيرات.

    تمريرتان فقط عندما تكون قاعدة IEP/PRI = ``SAL_BASE_APRES_ABSENCES``
    (نحتاج ``retenue_absence`` أولاً)؛ وإلا تمريرة واحدة."""
    convention = convention or {}
    parsed: List[Tuple[LineType, Dict]] = [
        (LINE_TYPES[e["type"]], e.get("values", {}))
        for e in entries if e.get("type") in LINE_TYPES
    ]
    kw = _convention_kwargs(convention)
    sb_total = sum((_v(v, "montant") for lt, v in parsed
                    if lt.key == "salaire_base"), _ZERO)

    base_iep_mode = convention.get("base_iep") or "SAL_BASE_BRUT"
    base_pri_mode = convention.get("base_pri") or "SAL_BASE_BRUT"
    has_rate = any(lt.key in _RATE_PRIMES for lt, _ in parsed)
    needs_ra = has_rate and "SAL_BASE_APRES_ABSENCES" in (
        base_iep_mode, base_pri_mode)

    def build(include_rate: bool, ctx: _Ctx):
        si = SequenceInput()
        metas: List[Dict] = []
        for lt, v in parsed:
            m: Dict = {}
            metas.append(m)
            if lt.key in _RATE_PRIMES and not include_rate:
                continue
            lt.fold(si, v, ctx, m)
        return si, metas

    ctx0 = _Ctx(cfg, convention, sb_total, sb_total)
    ra = _ZERO
    if needs_ra:
        si0, _ = build(False, ctx0)
        ra = compute_sequence(si0, cfg, **kw).retenue_absence

    ctx = _Ctx(
        cfg, convention,
        sb_total if base_iep_mode == "SAL_BASE_BRUT" else sb_total - ra,
        sb_total if base_pri_mode == "SAL_BASE_BRUT" else sb_total - ra,
    )
    si, metas = build(True, ctx)
    res = compute_sequence(si, cfg, **kw)

    views: List[LineView] = []
    for (lt, v), m in zip(parsed, metas):
        views.append(LineView(
            key=lt.key, libelle=lt.libelle, zone=lt.zone(v), sens=lt.sens,
            montant=lt.resolve(res, v, m), code=lt.code))
    views.sort(key=lambda x: ZONE_ORDER.get(x.zone, 9))

    return BulletinView(
        lignes=views, a=res.assiette_cnas, b=res.retenue_cnas,
        c=res.assiette_irg, d=res.irg, e=res.net_a_payer,
        avertissements=list(res.avertissements), result=res)
